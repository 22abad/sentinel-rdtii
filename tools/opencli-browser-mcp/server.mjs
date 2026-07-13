#!/usr/bin/env node
// RDTII OpenCLI Browser Bridge
//
// Exposes a small MCP-style JSON-RPC surface over stdio plus a `--once` mode used
// by the FastAPI backend (ai-service/browser_drivers/opencli.py spawns
// `node server.mjs --once <tool>` and pipes a JSON arg object on stdin).
//
// HOW IT TALKS TO OpenCLI
// -----------------------
// It drives OpenCLI through its DOCUMENTED CLI (`opencli browser <session> ...`),
// spawned via execFile — NOT by importing OpenCLI's compiled internals. The CLI
// `bin` plus its commands are the only surface the maintainer commits to, so this
// survives OpenCLI version bumps. (Earlier revisions deep-imported the unexported
// dist/src/runtime.js / browser/index.js / browser/extract.js, which are absent
// from the package `exports` map and carry no stability guarantee.)
//
// VERIFIED CLI CONTRACT  (read from @jackwener/opencli@1.8.4 dist/src — not inferred)
//   open     opencli browser <session> open <url>
//   wait     opencli browser <session> wait time <seconds>  [--timeout <ms>]
//   eval     opencli browser <session> eval '<js>'
//              cdp.js:189   Runtime.evaluate { returnByValue:true, awaitPromise:true }
//                           -> an async IIFE `(async()=>{})()` IS awaited before serialize
//              cli.js:2200  string result -> printed RAW; else JSON.stringify(result,null,2)
//              => our eval JS returns OBJECTS/ARRAYS (never a bare string) so stdout
//                 is always JSON.parse-able.
//   extract  opencli browser <session> extract [--selector <css>] [--chunk-size <n>] [--start <n>]
//              cli.js:2266  prints JSON.stringify(runExtractFromHtml({...}), null, 2)
//              envelope     browser/extract.js:116 ->
//                           { content, url, title, selector, total_chars,
//                             chunk_size, start, end, next_start_char }
//   window   set env OPENCLI_WINDOW=background|foreground (avoids arg-position ambiguity)
//   session  reuse the same <session> across calls to keep the tab/state alive
//            (daemon-backed). search_gov_law depends on this: its router-push eval and
//            its scrape eval are SEPARATE subprocesses sharing one live SPA tab — the
//            client-side route state set by the first survives into the second.
//
// AVAILABILITY GATE
//   ensureAvailable() probes the OpenCLI daemon's HTTP /status (X-OpenCLI header,
//   ~2.5s) before any browser command. No daemon (connection refused) or
//   extensionConnected!==true => returns a clean "not available" error fast, instead
//   of blocking on `open` until the caller's timeout. It is site-independent and a
//   pure TCP probe never spawns a daemon, so a machine without OpenCLI stays clean.

import fs from 'node:fs';
import path from 'node:path';
import http from 'node:http';
import { execFile } from 'node:child_process';
import { fileURLToPath } from 'node:url';

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

// Locate the opencli executable (the bin), not internal modules. Falls back to an
// `opencli` binary on PATH if no installed package directory is found.
function findOpenCliBin() {
  const candidates = [
    process.env.OPENCLI_PACKAGE_DIR,
    path.resolve(__dirname, 'node_modules/@jackwener/opencli'),
    path.resolve(process.cwd(), 'tools/opencli-browser-mcp/node_modules/@jackwener/opencli'),
    path.resolve(__dirname, '../../../opencli'),
    path.resolve(process.cwd(), '../opencli'),
  ].filter(Boolean);
  for (const dir of candidates) {
    const main = path.join(dir, 'dist/src/main.js');
    if (fs.existsSync(main)) return { cmd: process.execPath, prefix: [main], dir };
  }
  return { cmd: 'opencli', prefix: [], dir: null };
}

const OPENCLI = findOpenCliBin();

// Resolved per call (not a load-time const) so tests can repoint the probe.
function daemonPort() {
  return Number(process.env.OPENCLI_DAEMON_PORT || 19825);
}

function cleanText(text) {
  return String(text ?? '').replace(/\r\n/g, '\n').replace(/[ \t]+\n/g, '\n').trim();
}

function limitInt(value, fallback, min, max) {
  const n = Number(value);
  if (!Number.isFinite(n)) return fallback;
  return Math.max(min, Math.min(max, Math.trunc(n)));
}

// Probe the daemon's authenticated /status. Resolves the parsed JSON, or null when
// the daemon is unreachable. A bare TCP attempt never spawns a daemon.
function probeStatus(timeoutMs = 2500) {
  return new Promise((resolve) => {
    const req = http.get(
      { host: '127.0.0.1', port: daemonPort(), path: '/status', headers: { 'X-OpenCLI': '1' }, timeout: timeoutMs },
      (res) => {
        let body = '';
        res.on('data', (c) => { body += c; });
        res.on('end', () => { try { resolve(JSON.parse(body)); } catch { resolve(null); } });
      },
    );
    req.on('error', () => resolve(null));
    req.on('timeout', () => { req.destroy(); resolve(null); });
  });
}

// Probe fresh every call — never cache. Caching a FAILURE permanently breaks the
// normal long-running (RPC) ordering "bridge starts, then the daemon/extension
// connect a moment later": the first probe would pin {ok:false} forever. The probe
// is a local ~instant HTTP call, so re-checking per tool call is cheap.
async function ensureAvailable() {
  const status = await probeStatus();
  // Tolerate multi-profile setups: the top-level extensionConnected can be an
  // aggregate that misses the specific default context the bridge actually uses, so
  // also accept "any profile reports connected" rather than false-failing the call.
  const anyProfileConnected = !!(status && Array.isArray(status.profiles)
    && status.profiles.some((p) => p && p.extensionConnected === true));
  if (!status || status.ok !== true) {
    return { ok: false, reason: 'OpenCLI daemon not reachable. Run `opencli daemon restart`.' };
  }
  if (status.extensionConnected !== true && !anyProfileConnected) {
    return { ok: false, reason: 'OpenCLI daemon is up but the Chrome browser extension is not connected.' };
  }
  return { ok: true };
}

// Run `opencli browser <session> <...args>` via execFile (array argv, NO shell — so
// multi-line JS with quotes passes as one argv element with zero escaping).
// Resolves { ok, value, raw, stderr, code }: `value` is parsed JSON when possible,
// else the raw string (eval prints bare strings unquoted).
function runBrowser(session, args, { windowMode, timeoutMs = 120000 } = {}) {
  return new Promise((resolve) => {
    const env = { ...process.env };
    if (windowMode) env.OPENCLI_WINDOW = windowMode === 'foreground' ? 'foreground' : 'background';
    const argv = [...OPENCLI.prefix, 'browser', session, ...args];
    execFile(
      OPENCLI.cmd,
      argv,
      { env, timeout: timeoutMs, maxBuffer: 64 * 1024 * 1024 },
      (err, stdout, stderr) => {
        const raw = String(stdout || '').trim();
        let value;
        try { value = raw ? JSON.parse(raw) : undefined; } catch { value = raw; }
        const isErrEnvelope = value && typeof value === 'object' && value.error;
        resolve({ ok: !err && !isErrEnvelope, value, raw, stderr: String(stderr || '').trim(), code: err && err.code });
      },
    );
  });
}

function errMsg(r) {
  return (r.value && r.value.error && r.value.error.message) || r.stderr || r.raw || `exit ${r.code}`;
}

function sessionOpts(args) {
  let session = String(args.session || 'rdtii-ingest');
  if (args.siteSession === 'ephemeral') session = `${session}-eph`;
  const windowMode = args.windowMode === 'foreground' ? 'foreground' : 'background';
  return { session, windowMode };
}

// Shared overall deadline. opencli.py wraps the WHOLE subprocess in a single
// timeoutMs+10s budget, so each CLI step must draw from the REMAINING budget — not
// get the full budget independently, or the per-step timeouts sum past the caller's
// wrapper and Python kills the process mid-extract on slow pages. Returns a thunk
// producing per-step runBrowser opts with the time left (floored so a near-exhausted
// budget still lets a quick command try, while staying within the +10s margin).
function makeStepBudget(windowMode, totalMs) {
  const deadline = Date.now() + totalMs;
  return () => ({ windowMode, timeoutMs: Math.max(1500, deadline - Date.now()) });
}

async function fetchUrl(args) {
  const url = String(args.url || '').trim();
  if (!/^https?:\/\//i.test(url)) {
    return { type: 'error', message: `Invalid URL: ${url}` };
  }
  const avail = await ensureAvailable();
  if (!avail.ok) return { type: 'error', message: avail.reason };

  const { session, windowMode } = sessionOpts(args);
  const selector = typeof args.selector === 'string' && args.selector.trim() ? args.selector.trim() : null;
  const chunkSize = limitInt(args.chunkSize, 200000, 1000, 300000);
  const settleSec = Math.round(limitInt(args.settleMs, 5000, 0, 30000) / 1000);
  const timeoutMs = limitInt(args.timeoutMs, 60000, 5000, 180000);
  const step = makeStepBudget(windowMode, timeoutMs);

  const opened = await runBrowser(session, ['open', url], step());
  if (!opened.ok) {
    return { type: 'error', message: `OpenCLI open failed: ${errMsg(opened)}` };
  }

  if (settleSec > 0) {
    await runBrowser(session, ['wait', 'time', String(settleSec)], step());
  }

  // PDF guard. eval returns an OBJECT so stdout is JSON (see CLI CONTRACT above).
  const ct = await runBrowser(session, ['eval', '({ contentType: document.contentType || "" })'], step());
  if (String((ct.value && ct.value.contentType) || '').toLowerCase().includes('pdf')) {
    return {
      type: 'error',
      message: 'OpenCLI text bridge reached a PDF document; use the Playwright/HTTP download path for files.',
    };
  }

  const extractArgs = ['extract', '--chunk-size', String(chunkSize), '--start', '0'];
  if (selector) extractArgs.push('--selector', selector);
  const ex = await runBrowser(session, extractArgs, step());
  if (!ex.ok || !ex.value || typeof ex.value !== 'object') {
    return { type: 'error', message: `OpenCLI extract failed: ${errMsg(ex)}` };
  }

  const env = ex.value;
  const text = cleanText(env.content);
  return {
    type: text ? 'text' : 'error',
    url: env.url || url,
    text,
    message: text ? undefined : 'OpenCLI extracted empty text.',
    metadata: {
      source: 'opencli',
      title: env.title,
      selector: env.selector,
      total_chars: env.total_chars,
    },
  };
}

async function searchGovLaw(args) {
  const query = String(args.query || '').trim();
  if (!query) return { results: [] };
  const avail = await ensureAvailable();
  if (!avail.ok) return { results: [], message: avail.reason };

  const { session, windowMode } = sessionOpts(args);
  const timeoutMs = limitInt(args.timeoutMs, 60000, 5000, 180000);
  const step = makeStepBudget(windowMode, timeoutMs);
  const limit = limitInt(args.limit, 10, 1, 20);
  const encodedQuery = JSON.stringify(query);

  const opened = await runBrowser(session, ['open', 'https://flk.npc.gov.cn/index.html'], step());
  if (!opened.ok) {
    return { results: [], message: `OpenCLI open failed: ${errMsg(opened)}` };
  }
  await runBrowser(session, ['wait', 'time', '4'], step());

  // Drive the SPA's Vue router to the search route. Returns { ok } so stdout is JSON.
  const routerJs = `
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
    `;
  const routed = await runBrowser(session, ['eval', routerJs], step());
  if (!routed.value || routed.value.ok !== true) {
    return { results: [], message: (routed.value && routed.value.message) || 'flk.npc.gov.cn search navigation failed.' };
  }
  await runBrowser(session, ['wait', 'time', '5'], step());

  // Scrape the results in a SEPARATE eval; the route state above persists (verified).
  // Returns an ARRAY so stdout is JSON.
  const scrapeJs = `
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
    `;
  const scraped = await runBrowser(session, ['eval', scrapeJs], step());
  return { results: Array.isArray(scraped.value) ? scraped.value : [] };
}

async function health() {
  const avail = await ensureAvailable();
  // Keep the documented { ok, packageDir } shape (see SETUP.md); add connectivity info.
  return {
    ok: true,
    packageDir: OPENCLI.dir,
    connected: avail.ok,
    reason: avail.ok ? undefined : avail.reason,
  };
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
      description: 'Check OpenCLI package availability and browser connectivity.',
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

// Only start the stdio server when invoked directly (`node server.mjs ...`). When
// imported (e.g. by server.test.mjs) this stays inert and exposes the functions.
const isMain = !!process.argv[1]
  && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url);

if (isMain) {
  if (process.argv[2] === '--once') {
    await once();
  } else {
    await rpc();
  }
}

export {
  findOpenCliBin,
  daemonPort,
  probeStatus,
  ensureAvailable,
  makeStepBudget,
  fetchUrl,
  searchGovLaw,
  health,
  callTool,
  toolDescriptors,
};
