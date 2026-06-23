.PHONY: setup doctor dev dev-backend dev-frontend dev-sidecar install install-frontend install-opencli-bridge install-sidecar test db migrate migrate-sidecar image

PYTHON ?= $(shell command -v python3.11 2>/dev/null || command -v python3 2>/dev/null || command -v python 2>/dev/null)

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
		$(PYTHON) -m uvicorn main:app --reload --port 8000 --app-dir ai-service --log-level info & \
		(export DATABASE_URL=$$(grep '^DATABASE_URL=' .env | cut -d= -f2-) SIDECAR_API_KEY=$$(grep '^SIDECAR_API_KEY=' .env | cut -d= -f2-) SIDECAR_ADDR=$$(grep '^SIDECAR_ADDR=' .env | cut -d= -f2-) && cd extract_sidecar && cargo run) & \
		(export VITE_AUTH_BYPASS=$$(grep '^VITE_AUTH_BYPASS=' .env | cut -d= -f2-) && cd rdtii-frontend && npx vite --host 0.0.0.0 --force) & \
		wait

dev-backend:
	$(PYTHON) -m uvicorn main:app --reload --port 8000 --app-dir ai-service --log-level info

dev-frontend:
	export VITE_AUTH_BYPASS=$$(grep '^VITE_AUTH_BYPASS=' .env | cut -d= -f2-) && cd rdtii-frontend && npx vite --host 0.0.0.0 --force

dev-sidecar:
	export DATABASE_URL=$$(grep '^DATABASE_URL=' .env | cut -d= -f2-) SIDECAR_API_KEY=$$(grep '^SIDECAR_API_KEY=' .env | cut -d= -f2-) SIDECAR_ADDR=$$(grep '^SIDECAR_ADDR=' .env | cut -d= -f2-) && cd extract_sidecar && cargo run

install:
	cd ai-service && $(PYTHON) -m pip install -r requirements.txt && $(PYTHON) -m playwright install webkit

install-sidecar:
	cd extract_sidecar && cargo build --release

migrate-sidecar:
	psql "$$DATABASE_URL" -f extract_sidecar/migrations/001_extracted_documents.sql


install-frontend:
	cd rdtii-frontend && npm install

install-opencli-bridge:
	cd tools/opencli-browser-mcp && npm install

test:
	cd ai-service && $(PYTHON) -m pytest

db:
	docker compose up -d postgres redis

migrate:
	psql "$$(grep '^DATABASE_URL=' .env | cut -d= -f2-)" -f rdtii-database/db/migrate_001_auth.sql
	psql "$$(grep '^DATABASE_URL=' .env | cut -d= -f2-)" -f rdtii-database/db/migrate_002_reset_tokens.sql
	psql "$$(grep '^DATABASE_URL=' .env | cut -d= -f2-)" -f rdtii-database/db/migrate_003_document_ownership.sql

image:
	docker compose down
	cd rdtii-frontend && npm run build
	docker compose build --no-cache frontend extract-sidecar ai-service
	docker compose up -d
