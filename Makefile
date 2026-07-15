.PHONY: setup doctor dev dev-backend dev-frontend dev-sidecar install install-frontend install-opencli-bridge install-sidecar test smoke-discovery discovery-coverage golden-coverage db db-reset image
.PHONY: setup doctor dev dev-backend dev-frontend dev-sidecar install install-frontend install-opencli-bridge install-sidecar test eval-setup eval-golden smoke-discovery discovery-coverage db db-reset image

PYTHON ?= $(shell command -v python3.11 2>/dev/null || command -v python3 2>/dev/null || command -v python 2>/dev/null)
SMOKE_ARGS ?=

setup:
	@if [ ! -f .env ]; then cp .env.example .env; echo "Created .env from .env.example. Edit API keys before running extraction."; fi
	$(MAKE) install
	$(MAKE) install-opencli-bridge
	$(MAKE) install-frontend

doctor:
	bash scripts/doctor.sh

dev:
	@echo "Starting backend, sidecar, and frontend..."
	@trap 'kill 0' EXIT; \
		(export EXTRACT_SIDECAR_URL=$$(grep '^EXTRACT_SIDECAR_URL=' .env | cut -d= -f2-); if [ -z "$$EXTRACT_SIDECAR_URL" ]; then export EXTRACT_SIDECAR_URL=http://localhost:4000; fi; $(PYTHON) -m uvicorn main:app --reload --reload-dir ai-service --reload-exclude ".venv" --reload-exclude "downloads" --port 8000 --app-dir ai-service --log-level info) & \
		(export DATABASE_URL=$$(grep '^DATABASE_URL=' .env | cut -d= -f2-) SIDECAR_API_KEY=$$(grep '^SIDECAR_API_KEY=' .env | cut -d= -f2-) SIDECAR_ADDR=$$(grep '^SIDECAR_ADDR=' .env | cut -d= -f2-) && cd extract_sidecar && cargo run) & \
		(export VITE_AUTH_BYPASS=$$(grep '^VITE_AUTH_BYPASS=' .env | cut -d= -f2-) && cd rdtii-frontend && npx vite --host 0.0.0.0 --force) & \
		wait

dev-backend:
	$(PYTHON) -m uvicorn main:app --reload --reload-dir ai-service --reload-exclude ".venv" --reload-exclude "downloads" --port 8000 --app-dir ai-service --log-level info

dev-frontend:
	export VITE_AUTH_BYPASS=$$(grep '^VITE_AUTH_BYPASS=' .env | cut -d= -f2-) && cd rdtii-frontend && npx vite --host 0.0.0.0 --force

dev-sidecar:
	export DATABASE_URL=$$(grep '^DATABASE_URL=' .env | cut -d= -f2-) SIDECAR_API_KEY=$$(grep '^SIDECAR_API_KEY=' .env | cut -d= -f2-) SIDECAR_ADDR=$$(grep '^SIDECAR_ADDR=' .env | cut -d= -f2-) && cd extract_sidecar && cargo run

install:
	cd ai-service && $(PYTHON) -m pip install -r requirements.txt && $(PYTHON) -m playwright install webkit

install-sidecar:
	cd extract_sidecar && cargo build --release

install-frontend:
	cd rdtii-frontend && npm install

install-opencli-bridge:
	cd tools/opencli-browser-mcp && npm install

test:
	cd ai-service && $(PYTHON) -m pytest

eval-setup:
	$(PYTHON) -m pip install -r requirements.txt

eval-golden:
	$(PYTHON) scripts/evaluate_golden_set.py --mode offline --output evaluation/reports/golden-offline.json

smoke-discovery:
	cd ai-service && DISCOVERY_REGISTRY_BACKEND=file PYTHONPATH=. $(PYTHON) ../scripts/discovery_smoke.py $(SMOKE_ARGS)

discovery-coverage:
	$(PYTHON) scripts/discovery_coverage.py --write

golden-coverage:
	$(PYTHON) scripts/check_golden_coverage.py

db:
	docker compose up -d postgres redis

db-reset:
	@echo "DESTRUCTIVE: resetting local Postgres and Redis data volumes..."
	docker compose down --volumes
	docker compose up -d --wait postgres redis

image:
	docker compose down
	cd rdtii-frontend && npm run build
	docker compose build --no-cache frontend extract-sidecar ai-service
	docker compose up -d
