# SENTINEL macOS Setup

This guide is the shortest path for running the project locally on macOS.
Linux and Windows are not first-class setup targets for this hackathon build.
Use WSL or adapt these commands manually if you are not on macOS.

## Prerequisites

Recommended package manager:

```bash
brew install python@3.11 node git rust libpq
```

Install Docker Desktop or OrbStack separately:

- Docker Desktop: https://www.docker.com/products/docker-desktop/
- OrbStack: https://orbstack.dev/

Required tools:

- Python 3.11+
- Node.js 20+
- npm
- Docker Desktop or OrbStack
- Rust/Cargo, for `extract_sidecar`
- `psql`, available from Homebrew `libpq`

If `psql` is installed by Homebrew but not on PATH, add it for your shell:

```bash
echo 'export PATH="/opt/homebrew/opt/libpq/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

## 1. Create Environment

```bash
cd /path/to/UN-DigitalTrade-AI-Mapper-private
cp .env.example .env
```

Edit `.env` and set at least one model API key. The default provider is
DeepSeek:

```env
RDTII_LLM_PROVIDER=deepseek
DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_API_KEY=...
```

For local demos, this keeps the login code but skips the frontend route guard:

```env
VITE_AUTH_BYPASS=true
```

Discovery can run without a search API key; generic official sources will be
marked as fixture fallback. To enable live generic web discovery, configure a
search backend:

```env
DISCOVERY_SEARCH_BACKEND=serpapi
SERPAPI_API_KEY=...
```

## Discovery Live Smoke Test

The live smoke runner calls the production `DiscoveryService.search()` flow
against the configured official government sites. It is intentionally manual:
normal pull-request CI continues to use deterministic mocks and fixtures.

Run all current positive-evidence checks for the required countries (AUS, MYS,
and SGP):

```bash
make smoke-discovery
```

Run countries incrementally while diagnosing a site or adapter:

```bash
make smoke-discovery SMOKE_ARGS='--countries SGP'
make smoke-discovery SMOKE_ARGS='--countries AUS MYS'
```

CHN and THA adapters remain future/optional work and are not part of the
required-country live smoke suite.

The broader AUS/MYS/SGP Pillar 6/7 research status is tracked in
`ai-service/discovery/required_country_coverage.yaml`. Regenerate its readable
matrix with `make discovery-coverage`.

The command writes timestamped JSON and Markdown files under `reports/` and
returns a non-zero status when a live acceptance check fails. Those generated
files are ignored by Git. Reports contain candidate metadata, URLs, validation
quality, durations, and warnings; they do not contain fetched legal text,
headers, cookies, or API keys.

A case passes only when the expected law comes from the official site's search
results (a configured known-law mapping is not enough), both candidate and final
URLs stay on configured official domains, the document fetch reports a valid
HTTP status and verified TLS transport, and the fetched text has `good` quality,
contains the law title, and matches the requested indicator. Archive/fixture
retrieval remains visible as fallback and must carry an explanatory warning.

## 2. Install Dependencies

```bash
make setup
```

This creates `.env` if needed, installs Python dependencies, installs the
Playwright browser used by the crawler, installs the optional OpenCLI bridge
package, and installs frontend npm packages.

If you want to install pieces separately:

```bash
make install
make install-opencli-bridge
make install-frontend
make install-sidecar
```

## 3. Initialize Database

```bash
make db-reset
```

This recreates the local database from the consolidated `init.sql` and starts:

- Postgres on `localhost:5433`
- Redis on `localhost:6379`

`db-reset` deletes the project's local Postgres and Redis data volumes. Use
`make db` instead when you only need to start an existing database.

The consolidated schema is a development bootstrap, not a repeatable migration
and not an upgrade path for persistent data. Before deploying with real users
or review records, establish a versioned migration baseline and stop resetting
the database.

If Docker is not reachable, open Docker Desktop or OrbStack from Applications
and rerun:

```bash
make db-reset
```

## 4. Check Local Setup

```bash
make doctor
```

`doctor` checks macOS local tools, `.env`, Python imports, Docker reachability, DB
containers, backend health, frontend port, and the optional OpenCLI bridge.

Warnings do not always block all workflows. For example, OpenCLI warnings only
matter when using `browser_mode=opencli`.

## 6. Run the App

```bash
make dev
```

This starts:

- FastAPI backend on `http://localhost:8000`
- Extract sidecar on `http://localhost:4000`
- Vite frontend on `http://localhost:5173`

Open:

```text
http://localhost:5173/workbench
```

## Running Services Separately

Backend only:

```bash
make dev-backend
```

Frontend only:

```bash
make dev-frontend
```

Sidecar only:

```bash
make dev-sidecar
```

## OpenCLI Browser Bridge

OpenCLI is optional. Use it when Browser mode is set to `OpenCLI`, or when
`auto` mode falls back to OpenCLI for difficult rendered pages.

For normal local setup, install the bridge package:

```bash
make install-opencli-bridge
```

This installs `@jackwener/opencli` into
`tools/opencli-browser-mcp/node_modules`.

For OpenCLI development, you can still point at a local checkout:

```bash
export OPENCLI_PACKAGE_DIR=/absolute/path/to/opencli
```

Health check:

```bash
node tools/opencli-browser-mcp/server.mjs --once health
```

Expected shape:

```json
{"ok":true,"packageDir":"/path/to/@jackwener/opencli","connected":true}
```

`ok`/`packageDir` report that the bridge can find the OpenCLI package;
`connected` reports whether the daemon + browser extension are currently up. When
they are not, `health` still returns `ok:true` with `connected:false` and a
`reason` (the bridge degrades gracefully rather than hanging).

The bridge also requires the OpenCLI browser/extension/daemon to be connected
for real page extraction.

## Common Problems

### `[vite] http proxy error: /health ECONNREFUSED`

The frontend is running, but the backend is not listening on port `8000`.

Fix:

```bash
make dev-backend
```

or restart everything:

```bash
make dev
```

### `SIDECAR_API_KEY must be set`

Your sidecar process did not receive the internal sidecar auth key.

Check `.env`:

```env
SIDECAR_API_KEY=dev-sidecar-secret
```

Then restart:

```bash
make dev
```

### Register/Login Fails With Missing User Columns

The local database was created from an older schema.

Fix:

```bash
make db-reset
```

### `make dev` Starts Frontend But Not Backend

Run:

```bash
make doctor
```

The most common macOS causes are missing Python dependencies, no Python on
PATH, or Docker Desktop/OrbStack not running.

### DeepSeek Model Error

The default model is:

```env
DEEPSEEK_MODEL=deepseek-v4-flash
```

If the provider returns `model not found`, update `DEEPSEEK_MODEL` in `.env`
to the model id currently enabled for your DeepSeek account.
