// Tests for the OpenCLI bridge's runtime glue — the parts that break when the
// environment is NOT a fully-connected OpenCLI on the dev's machine (CI, daemon
// not up yet, multi-profile). Run: `npm test` (uses Node's built-in runner, no deps).
//
// These exercise the real probe path against a throwaway local HTTP server that
// impersonates the daemon's /status, so no real OpenCLI daemon/extension is needed.

import { test } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';

import {
  makeStepBudget,
  ensureAvailable,
  health,
  findOpenCliBin,
} from './server.mjs';

// Start a fake daemon that answers /status with `payload`. Returns { port, close }.
function startFakeDaemon(payload) {
  return new Promise((resolve) => {
    const server = http.createServer((req, res) => {
      res.setHeader('content-type', 'application/json');
      res.end(JSON.stringify(payload));
    });
    server.listen(0, '127.0.0.1', () => {
      resolve({
        port: server.address().port,
        close: () => new Promise((r) => server.close(r)),
      });
    });
  });
}

// Grab an ephemeral port and immediately free it, so connecting there is refused
// (simulates "daemon not running").
function getClosedPort() {
  return new Promise((resolve) => {
    const s = http.createServer();
    s.listen(0, '127.0.0.1', () => {
      const { port } = s.address();
      s.close(() => resolve(port));
    });
  });
}

test('ensureAvailable does not permanently cache failure — recovers when the daemon comes up', async () => {
  // Phase 1: no daemon on the port -> unavailable.
  const closedPort = await getClosedPort();
  process.env.OPENCLI_DAEMON_PORT = String(closedPort);
  const first = await ensureAvailable();
  assert.equal(first.ok, false, 'first probe with no daemon must be unavailable');
  assert.match(first.reason, /not reachable/i);

  // Phase 2: daemon comes up (connected). A second call MUST re-probe and recover.
  const daemon = await startFakeDaemon({
    ok: true,
    extensionConnected: true,
    profiles: [{ extensionConnected: true }],
  });
  process.env.OPENCLI_DAEMON_PORT = String(daemon.port);
  try {
    const second = await ensureAvailable();
    assert.equal(second.ok, true, 'after the daemon connects, ensureAvailable must recover (no cached failure)');
  } finally {
    await daemon.close();
  }
});

test('ensureAvailable tolerates multi-profile: top-level disconnected but a profile connected -> available', async () => {
  const daemon = await startFakeDaemon({
    ok: true,
    extensionConnected: false, // aggregate says no...
    profiles: [{ extensionConnected: false }, { extensionConnected: true }], // ...but one context is connected
  });
  process.env.OPENCLI_DAEMON_PORT = String(daemon.port);
  try {
    const avail = await ensureAvailable();
    assert.equal(avail.ok, true, 'any connected profile should count as available');
  } finally {
    await daemon.close();
  }
});

test('ensureAvailable: daemon up but nothing connected -> unavailable (fast skip)', async () => {
  const daemon = await startFakeDaemon({
    ok: true,
    extensionConnected: false,
    profiles: [{ extensionConnected: false }],
  });
  process.env.OPENCLI_DAEMON_PORT = String(daemon.port);
  try {
    const avail = await ensureAvailable();
    assert.equal(avail.ok, false);
    assert.match(avail.reason, /extension is not connected/i);
  } finally {
    await daemon.close();
  }
});

test('makeStepBudget: steps share one deadline — later step gets less than the first, never the full budget again', async () => {
  const step = makeStepBudget('background', 60000);
  const first = step().timeoutMs;
  assert.ok(first <= 60000, 'first step must not exceed the total budget');
  await new Promise((r) => setTimeout(r, 25)); // let the clock advance
  const second = step().timeoutMs;
  assert.ok(second < first, `a later step must draw from the remaining budget (first=${first}, second=${second})`);
});

test('makeStepBudget: an exhausted budget is floored, never zero/negative', () => {
  const step = makeStepBudget('background', 0); // already at the deadline
  assert.equal(step().timeoutMs, 1500);
});

test('makeStepBudget: passes windowMode straight through', () => {
  assert.equal(makeStepBudget('foreground', 5000)().windowMode, 'foreground');
});

test('health: no daemon -> { ok:true, connected:false, reason } and packageDir resolves to the local npm package', async () => {
  const closedPort = await getClosedPort();
  process.env.OPENCLI_DAEMON_PORT = String(closedPort);

  const h = await health();
  assert.equal(h.ok, true, 'health.ok stays true (package resolvable) even when the daemon is down');
  assert.equal(h.connected, false, 'connected:false when the daemon is down');
  assert.ok(h.reason, 'a reason is reported when not connected');

  // Guard against regressing to the old "hunt for dist/src/runtime.js" detection:
  // packageDir must come from findOpenCliBin and point at the installed package.
  const bin = findOpenCliBin();
  assert.equal(h.packageDir, bin.dir, 'health.packageDir must match findOpenCliBin().dir');
  if (h.packageDir !== null) {
    assert.ok(
      h.packageDir.includes('@jackwener/opencli') || process.env.OPENCLI_PACKAGE_DIR,
      `packageDir should point at the installed package, got ${h.packageDir}`,
    );
  }
});
