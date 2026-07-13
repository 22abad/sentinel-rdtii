# RDTII OpenCLI Browser Bridge

This bridge exposes a small MCP-style JSON-RPC surface over stdio and a
`--once` mode used by the FastAPI backend.

## Setup

For normal project setup, install this bridge package:

```bash
npm install
```

This installs `@jackwener/opencli` into this bridge directory's
`node_modules`.

For OpenCLI development, point this project at a local checkout:

```bash
export OPENCLI_PACKAGE_DIR=/absolute/path/to/opencli
```

OpenCLI Browser Bridge also needs Chrome/Chromium with the OpenCLI extension
connected, as documented in the OpenCLI repo.

## Runtime requirements

This bridge drives OpenCLI through its **CLI** (`opencli browser <session> ...`),
spawned as a subprocess — it does not import OpenCLI's internal modules. At runtime
it requires:

- the **OpenCLI daemon running** (default port 19825). The bridge probes the
  daemon's `/status` over HTTP and **does not auto-start it**, so run the daemon as
  a persistent service (e.g. `opencli daemon restart` at backend startup, or set
  `OPENCLI_DAEMON_PORT` if you moved it).
- the **Chrome/Chromium extension connected** to that daemon.

If either is missing, every tool returns a fast error / empty result (a ~2.5s
availability probe, never a long hang) so the FastAPI fallback chain
(HTTP → Playwright → archive) continues uninterrupted. Check with `opencli doctor`
or the `health` tool.

## FastAPI Modes

`browser_mode=auto` keeps the existing HTTP/Playwright path and tries OpenCLI
only as a final rendered-page fallback.

`browser_mode=playwright` uses the existing crawler path only.

`browser_mode=opencli` tries this bridge first. It is intended for pages where
a real authorized browser session is required, while still keeping the existing
file, HTTP, Playwright, and archive fallbacks available if the bridge cannot
extract text.

## Tools

- `fetch_url`: render a URL through OpenCLI and return cleaned legal text.
- `search_gov_law`: search China's National Laws and Regulations Database.
- `health`: report the resolved OpenCLI package dir and whether the daemon +
  extension are connected (`{ ok, packageDir, connected }`).
