#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

function readStdin() {
  return new Promise((resolve, reject) => {
    let body = '';
    process.stdin.setEncoding('utf8');
    process.stdin.on('data', (chunk) => { body += chunk; });
    process.stdin.on('end', () => resolve(body));
    process.stdin.on('error', reject);
  });
}

function findOpenCliPackageDir() {
  const candidates = [
    process.env.OPENCLI_PACKAGE_DIR,
    path.resolve(__dirname, '../../../opencli'),
    path.resolve(process.cwd(), '../opencli'),
  ].filter(Boolean);

  for (const dir of candidates) {
    const runtime = path.join(dir, 'dist/src/runtime.js');
    const browserIndex = path.join(dir, 'dist/src/browser/index.js');
    if (fs.existsSync(runtime) && fs.existsSync(browserIndex)) return dir;
  }
  throw new Error(
    'Built OpenCLI package not found. Set OPENCLI_PACKAGE_DIR to an OpenCLI checkout and run `npm run build` there.',
  );
}

async function loadOpenCli() {
  const dir = findOpenCliPackageDir();
  const runtime = await import(pathToFileURL(path.join(dir, 'dist/src/runtime.js')).href);
  const browser = await import(pathToFileURL(path.join(dir, 'dist/src/browser/index.js')).href);
  const extract = await import(pathToFileURL(path.join(dir, 'dist/src/browser/extract.js')).href);
  return { dir, runtime, browser, extract };
}

function cleanText(text) {
  return String(text ?? '').replace(/\r\n/g, '\n').replace(/[ \t]+\n/g, '\n').trim();
}

function limitInt(value, fallback, min, max) {
  const n = Number(value);
  if (!Number.isFinite(n)) return fallback;
  return Math.max(min, Math.min(max, Math.trunc(n)));
}

async function withPage(args, fn) {
  const { runtime } = await loadOpenCli();
  const BrowserFactory = runtime.getBrowserFactory?.();
  if (!BrowserFactory) throw new Error('OpenCLI runtime.getBrowserFactory is unavailable.');
  return runtime.browserSession(BrowserFactory, fn, {
    session: String(args.session || 'rdtii-ingest'),
    windowMode: args.windowMode === 'foreground' ? 'foreground' : 'background',
    siteSession: args.siteSession === 'ephemeral' ? 'ephemeral' : 'persistent',
    surface: 'adapter',
  });
}

async function fetchUrl(args) {
  const url = String(args.url || '').trim();
  if (!/^https?:\/\//i.test(url)) {
    return { type: 'error', message: `Invalid URL: ${url}` };
  }
  const timeoutMs = limitInt(args.timeoutMs, 60000, 5000, 180000);
  const selector = typeof args.selector === 'string' && args.selector.trim()
    ? args.selector.trim()
    : null;
  const chunkSize = limitInt(args.chunkSize, 200000, 1000, 300000);
  const settleMs = limitInt(args.settleMs, 5000, 0, 30000);

  return withPage(args, async (page) => {
    await page.goto(url, { settleMs });
    await page.wait?.(Math.min(3, Math.max(1, timeoutMs / 1000 / 10))).catch(() => {});

    const contentType = await page.evaluate('document.contentType || ""').catch(() => '');
    if (String(contentType).toLowerCase().includes('pdf')) {
      return {
        type: 'error',
        message: 'OpenCLI text bridge reached a PDF document; use the Playwright/HTTP download path for files.',
      };
    }

    const { extract } = await loadOpenCli();
    const raw = await page.evaluate(extract.buildExtractHtmlJs(selector));
    if (!raw || raw.ok !== true || !raw.html) {
      return {
        type: 'error',
        message: raw?.invalidSelector
          ? `Invalid selector: ${raw.reason || selector}`
          : raw?.notFound
            ? `Selector not found: ${selector || 'main/article/body'}`
            : 'OpenCLI could not extract page HTML.',
      };
    }
    const rendered = extract.runExtractFromHtml({
      html: raw.html,
      url: raw.url || url,
      title: raw.title || '',
      selector,
      start: 0,
      chunkSize,
    });
    const text = cleanText(rendered.content);
    return {
      type: text ? 'text' : 'error',
      url: rendered.url || url,
      text,
      message: text ? undefined : 'OpenCLI extracted empty text.',
      metadata: {
        source: 'opencli',
        title: rendered.title,
        selector: rendered.selector,
        total_chars: rendered.total_chars,
      },
    };
  });
}

async function searchGovLaw(args) {
  const query = String(args.query || '').trim();
  if (!query) return { results: [] };
  const limit = limitInt(args.limit, 10, 1, 20);
  const encodedQuery = JSON.stringify(query);

  return withPage(args, async (page) => {
    await page.goto('https://flk.npc.gov.cn/index.html', { settleMs: 4000 });
    await page.wait?.(4).catch(() => {});
    const routerResult = await page.evaluate(`
      (async () => {
        try {
          const app = document.querySelector('#app');
          const router = app?.__vue_app__?.config?.globalProperties?.$router;
          if (!router) return { ok: false, message: 'flk.npc.gov.cn Vue router was not available.' };
          await router.push({ path: '/search', query: { searchWord: ${encodedQuery} } });
          return { ok: true };
        } catch (error) {
          return { ok: false, message: error?.message || String(error) };
        }
      })()
    `);
    if (!routerResult?.ok) {
      return { results: [], message: routerResult?.message || 'flk.npc.gov.cn search navigation failed.' };
    }
    await page.wait?.(5).catch(() => {});
    const data = await page.evaluate(`
      (async () => {
        const normalize = v => (v || '').replace(/\\s+/g, ' ').trim();
        for (let i = 0; i < 40; i++) {
          if (document.querySelectorAll('.result-item').length > 0) break;
          await new Promise(r => setTimeout(r, 500));
        }
        const results = [];
        for (const el of document.querySelectorAll('.result-item')) {
          const title = normalize(el.querySelector('.title-content')?.textContent);
          if (!title) continue;
          const href = el.querySelector('a[href]')?.href || '';
          const status = normalize(el.querySelector('[class*="status"]')?.textContent);
          const publish_date = normalize(el.querySelector('.publish-time')?.textContent).replace(/^公布日期[：:]\\s*/, '');
          const type = normalize(el.querySelector('.type')?.textContent);
          const department = normalize(el.querySelector('.department')?.textContent);
          results.push({ rank: results.length + 1, title, url: href, status, publish_date, type, department });
          if (results.length >= ${limit}) break;
        }
        return results;
      })()
    `);
    return { results: Array.isArray(data) ? data : [] };
  });
}

async function health() {
  const { dir } = await loadOpenCli();
  return { ok: true, packageDir: dir };
}

const tools = {
  fetch_url: fetchUrl,
  search_gov_law: searchGovLaw,
  health,
};

function toolDescriptors() {
  return [
    {
      name: 'fetch_url',
      description: 'Fetch rendered legal text from a URL through OpenCLI Browser Bridge.',
      inputSchema: {
        type: 'object',
        required: ['url'],
        properties: {
          url: { type: 'string', description: 'HTTP(S) URL to render.' },
          timeoutMs: { type: 'integer', minimum: 5000, maximum: 180000 },
          settleMs: { type: 'integer', minimum: 0, maximum: 30000 },
          selector: { type: 'string', description: 'Optional CSS selector to extract.' },
          chunkSize: { type: 'integer', minimum: 1000, maximum: 300000 },
          session: { type: 'string' },
          siteSession: { type: 'string', enum: ['persistent', 'ephemeral'] },
          windowMode: { type: 'string', enum: ['background', 'foreground'] },
        },
      },
    },
    {
      name: 'search_gov_law',
      description: "Search China's National Laws and Regulations Database.",
      inputSchema: {
        type: 'object',
        required: ['query'],
        properties: {
          query: { type: 'string' },
          limit: { type: 'integer', minimum: 1, maximum: 20 },
          timeoutMs: { type: 'integer', minimum: 5000, maximum: 180000 },
          session: { type: 'string' },
          siteSession: { type: 'string', enum: ['persistent', 'ephemeral'] },
          windowMode: { type: 'string', enum: ['background', 'foreground'] },
        },
      },
    },
    {
      name: 'health',
      description: 'Check OpenCLI package availability.',
      inputSchema: {
        type: 'object',
        properties: {},
      },
    },
  ];
}

async function callTool(name, args = {}) {
  const tool = tools[name];
  if (!tool) throw new Error(`Unknown tool: ${name}`);
  return tool(args);
}

async function once() {
  const name = process.argv[3];
  const body = await readStdin();
  const args = body.trim() ? JSON.parse(body) : {};
  try {
    const result = await callTool(name, args);
    process.stdout.write(`${JSON.stringify(result)}\n`);
  } catch (error) {
    process.stdout.write(JSON.stringify({
      ok: false,
      error: error instanceof Error ? error.message : String(error),
    }) + '\n');
    process.exitCode = 1;
  }
}

function writeRpc(id, result, error) {
  const msg = error
    ? { jsonrpc: '2.0', id, error: { code: -32000, message: error.message || String(error) } }
    : { jsonrpc: '2.0', id, result };
  process.stdout.write(`${JSON.stringify(msg)}\n`);
}

async function rpcLine(line) {
  const req = JSON.parse(line);
  if (req.method === 'initialize') {
    writeRpc(req.id, {
      protocolVersion: '2024-11-05',
      serverInfo: { name: 'rdtii-opencli-browser', version: '0.1.0' },
      capabilities: { tools: {} },
    });
    return;
  }
  if (req.method === 'tools/list') {
    writeRpc(req.id, {
      tools: toolDescriptors(),
    });
    return;
  }
  if (req.method === 'tools/call') {
    try {
      const result = await callTool(req.params?.name, req.params?.arguments || {});
      writeRpc(req.id, { content: [{ type: 'text', text: JSON.stringify(result) }] });
    } catch (error) {
      writeRpc(req.id, null, error);
    }
    return;
  }
  if (req.id !== undefined) {
    writeRpc(req.id, null, new Error(`Unknown method: ${req.method}`));
  }
}

async function rpc() {
  let buffer = '';
  process.stdin.setEncoding('utf8');
  process.stdin.on('data', (chunk) => {
    buffer += chunk;
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';
    for (const line of lines) {
      if (!line.trim()) continue;
      rpcLine(line).catch((error) => writeRpc(null, null, error));
    }
  });
}

if (process.argv[2] === '--once') {
  await once();
} else {
  await rpc();
}
