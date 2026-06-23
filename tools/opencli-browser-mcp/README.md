# RDTII OpenCLI Browser Bridge

This bridge exposes a small MCP-style JSON-RPC surface over stdio and a
`--once` mode used by the FastAPI backend.

## Setup

Build OpenCLI first:

```bash
cd ../opencli
npm install
npm run build
```

Then point this project at that checkout if it is not the sibling directory:

```bash
export OPENCLI_PACKAGE_DIR=/absolute/path/to/opencli
```

OpenCLI Browser Bridge also needs Chrome/Chromium with the OpenCLI extension
connected, as documented in the OpenCLI repo.

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
- `health`: verify that the built OpenCLI package can be loaded.
