#!/usr/bin/env bash
set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR" || exit 1

errors=0
warnings=0

ok() {
  printf "ok    %s\n" "$1"
}

warn() {
  warnings=$((warnings + 1))
  printf "warn  %s\n" "$1"
}

fail() {
  errors=$((errors + 1))
  printf "fail  %s\n" "$1"
}

have() {
  command -v "$1" >/dev/null 2>&1
}

env_value() {
  if [ -f .env ]; then
    grep -E "^$1=" .env | tail -n 1 | cut -d= -f2-
  fi
}

require_cmd() {
  if have "$1"; then
    ok "$1: $($1 --version 2>/dev/null | head -n 1)"
  else
    fail "$1 is not installed or not on PATH"
  fi
}

printf "SENTINEL macOS doctor\n"
printf "Project: %s\n\n" "$ROOT_DIR"

if [ "$(uname -s)" = "Darwin" ]; then
  macos_version="$(sw_vers -productVersion 2>/dev/null || uname -r)"
  ok "macOS: $macos_version"
else
  fail "this doctor target is only defined for macOS"
fi

printf "\n"
printf "Core tools\n"
if have python3.11; then
  PY_BIN="$(command -v python3.11)"
elif have python3; then
  PY_BIN="$(command -v python3)"
elif have python; then
  PY_BIN="$(command -v python)"
else
  PY_BIN=""
fi

if [ -n "$PY_BIN" ]; then
  ok "python: $("$PY_BIN" --version 2>&1) ($PY_BIN)"
else
  fail "python 3.11+ is not installed or not on PATH"
fi

require_cmd node
require_cmd npm
require_cmd git
require_cmd cargo

if have psql; then
  ok "psql: $(psql --version | head -n 1)"
else
  warn "psql is not installed; install Homebrew libpq or run migrations from another Postgres client"
fi

if have docker; then
  if docker info >/dev/null 2>&1; then
    ok "docker daemon is reachable"
  else
    fail "docker is installed but the daemon is not reachable; open Docker Desktop or OrbStack from Applications"
  fi
else
  fail "docker is not installed or not on PATH; install Docker Desktop or OrbStack"
fi

printf "\nProject files\n"
if [ -f .env ]; then
  ok ".env exists"
else
  fail ".env is missing; run: cp .env.example .env"
fi

if [ -f rdtii-frontend/package-lock.json ]; then
  ok "frontend package-lock.json exists"
else
  warn "frontend package-lock.json missing"
fi

if [ -d rdtii-frontend/node_modules ]; then
  ok "frontend node_modules exists"
else
  warn "frontend dependencies are not installed; run: make install-frontend"
fi

if [ -n "$PY_BIN" ]; then
  if "$PY_BIN" - <<'PY' >/dev/null 2>&1
import fastapi, uvicorn
PY
  then
    ok "Python backend packages import"
  else
    warn "Python backend packages are not importable; run: make install"
  fi
fi

printf "\nEnvironment\n"
provider="$(env_value RDTII_LLM_PROVIDER)"
database_url="$(env_value DATABASE_URL)"
sidecar_key="$(env_value SIDECAR_API_KEY)"
auth_bypass="$(env_value VITE_AUTH_BYPASS)"

if [ -n "$provider" ]; then
  ok "RDTII_LLM_PROVIDER=$provider"
else
  warn "RDTII_LLM_PROVIDER is not set"
fi

if [ -n "$database_url" ]; then
  ok "DATABASE_URL is set"
else
  fail "DATABASE_URL is missing from .env"
fi

if [ -n "$sidecar_key" ]; then
  ok "SIDECAR_API_KEY is set"
else
  fail "SIDECAR_API_KEY is missing from .env"
fi

if [ -n "$auth_bypass" ]; then
  ok "VITE_AUTH_BYPASS=$auth_bypass"
else
  warn "VITE_AUTH_BYPASS is not set; frontend auth guard will stay enabled"
fi

case "$provider" in
  deepseek)
    if [ -n "$(env_value DEEPSEEK_API_KEY)" ]; then
      ok "DEEPSEEK_API_KEY is set"
    else
      warn "DEEPSEEK_API_KEY is empty; DeepSeek extraction will fail until configured"
    fi
    ;;
  gemini)
    if [ -n "$(env_value GEMINI_API_KEY)" ]; then ok "GEMINI_API_KEY is set"; else warn "GEMINI_API_KEY is empty"; fi
    ;;
  openai)
    if [ -n "$(env_value OPENAI_API_KEY)" ]; then ok "OPENAI_API_KEY is set"; else warn "OPENAI_API_KEY is empty"; fi
    ;;
  claude)
    if [ -n "$(env_value CLAUDE_API_KEY)" ]; then ok "CLAUDE_API_KEY is set"; else warn "CLAUDE_API_KEY is empty"; fi
    ;;
esac

printf "\nServices\n"
if have docker && docker info >/dev/null 2>&1; then
  if docker ps --format '{{.Names}}' | grep -qx 'rdtii-postgres'; then
    ok "rdtii-postgres container is running"
  else
    warn "rdtii-postgres is not running; run: make db"
  fi

  if docker ps --format '{{.Names}}' | grep -qx 'rdtii-redis'; then
    ok "rdtii-redis container is running"
  else
    warn "rdtii-redis is not running; run: make db"
  fi
fi

if have curl; then
  if curl -fsS http://localhost:8000/health >/dev/null 2>&1; then
    ok "backend health responds on localhost:8000"
  else
    warn "backend is not responding on localhost:8000; run: make dev-backend or make dev"
  fi
else
  warn "curl is not installed; skipping HTTP health checks"
fi

if command -v lsof >/dev/null 2>&1; then
  if lsof -nP -iTCP:5173 -sTCP:LISTEN >/dev/null 2>&1; then
    ok "frontend dev server is listening on 5173"
  else
    warn "frontend dev server is not listening on 5173; run: make dev-frontend or make dev"
  fi
fi

printf "\nOpenCLI bridge\n"
opencli_dirs=()
if [ -n "${OPENCLI_PACKAGE_DIR:-}" ]; then
  opencli_dirs+=("$OPENCLI_PACKAGE_DIR")
fi
opencli_dirs+=("$ROOT_DIR/tools/opencli-browser-mcp/node_modules/@jackwener/opencli")
opencli_dirs+=("$(cd "$ROOT_DIR/.." && pwd)/opencli")

opencli_dir=""
for candidate in "${opencli_dirs[@]}"; do
  if [ -f "$candidate/dist/src/main.js" ]; then
    opencli_dir="$candidate"
    break
  fi
done

if [ -n "$opencli_dir" ]; then
  ok "OpenCLI package found at $opencli_dir"
else
  warn "OpenCLI package not found; run: make install-opencli-bridge, or set OPENCLI_PACKAGE_DIR"
fi

if [ -f tools/opencli-browser-mcp/server.mjs ]; then
  if node --check tools/opencli-browser-mcp/server.mjs >/dev/null 2>&1; then
    ok "OpenCLI bridge JavaScript parses"
  else
    fail "OpenCLI bridge JavaScript has syntax errors"
  fi
else
  warn "OpenCLI bridge server is missing"
fi

printf "\nSummary\n"
printf "errors: %s, warnings: %s\n" "$errors" "$warnings"

if [ "$errors" -gt 0 ]; then
  printf "doctor failed. Fix the failed checks above, then rerun: make doctor\n"
  exit 1
fi

printf "doctor passed. Warnings may still matter for specific workflows.\n"
