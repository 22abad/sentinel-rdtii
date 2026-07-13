# Add Rust extract-sidecar, JWT auth, and frontend UX improvements

**Base:** `main` → **Head:** `Implement_Sidecar_For_RAG`

---

## Summary

- Introduce a standalone Rust/Axum microservice (`extract_sidecar`) that owns PDF/image OCR and text extraction, with SHA-256-based PostgreSQL caching and optional TTL expiry
- Add JWT-based user authentication (register, login, forgot/reset password) to the FastAPI backend
- Ship three new database migrations for auth tables, document ownership, and the extraction cache
- Add a mobile navigation drawer, `MapSearch` page, and `WorldMap` placeholder to the frontend
- Clean up the Makefile and Docker Compose to wire all three services together

---

## What changed

### `extract_sidecar/` — new Rust sidecar service
- Axum HTTP server listening on `SIDECAR_ADDR` (default `0.0.0.0:4000`)
- `POST /extract-text` multipart endpoint: accepts PDF, JPEG, PNG, TXT, MD
- SHA-256 content hashing → cache lookup in `extracted_documents` before OCR
- Provider cascade: Tesseract → OpenAI Vision fallback (mirrors the existing Python logic)
- `ON CONFLICT (content_hash) DO NOTHING` handles concurrent uploads safely
- API-key middleware (`Authorization: Bearer <SIDECAR_API_KEY>`) guards the endpoint
- `expires_in_days` multipart field for per-document TTL; omit for permanent storage
- Dockerized with its own `Dockerfile`; migration in `migrations/001_extracted_documents.sql`

### `ai-service/auth.py` — new JWT auth module
- `POST /auth/register`, `POST /auth/login`, `POST /auth/forgot-password`, `POST /auth/reset-password`
- `bcrypt` password hashing; `python-jose` JWT (HS256, configurable expiry via `JWT_EXPIRE_HOURS`)
- `get_current_user` FastAPI `Depends()` guard for protected routes
- Forgot-password flow: single-use tokens stored in `password_reset_tokens`, email sent via SMTP (falls back to log if `SMTP_HOST` unset)
- Always returns 200 on `/forgot-password` to avoid email enumeration

### Database migrations (`rdtii-database/db/`)
| File | Purpose |
|---|---|
| `migrate_001_auth.sql` | `users` table (id, username, email, password_hash, role, is_active, last_login) |
| `migrate_002_reset_tokens.sql` | `password_reset_tokens` table (single-use, TTL) |
| `migrate_003_document_ownership.sql` | Adds `owner_id` FK to documents table |
| `extract_sidecar/migrations/001_extracted_documents.sql` | `extracted_documents` cache table |

### Docker Compose (`docker-compose.yaml`)
- New `extract-sidecar` service wired to Postgres with `service_healthy` dependency
- `ai-service` now depends on both `postgres` and `extract-sidecar`; `EXTRACT_SIDECAR_URL` injected
- `db` target now runs `docker compose up -d` (detached)

### Makefile
- `dev` auto-detects Postgres container IP and patches `.env` before starting
- Three processes started: uvicorn, `cargo run` (sidecar), vite — all killed on `EXIT` trap
- New targets: `dev-sidecar`, `install-sidecar`, `migrate-sidecar`, `image` (full rebuild + up)
- Python path pinned to `/opt/homebrew/bin/python3.11` via `PYTHON` variable

### Frontend (`rdtii-frontend/`)
- **`MobileNav`** — animated slide-in drawer (Framer Motion), Escape-to-close, body-scroll lock, auth-aware sign-out
- **`MapSearch` page** — new `/mapsearch` route with `CountrySourcesPanel` and `FoundPdfsPanel` components
- **`WorldMap` placeholder** — SVG world map with animated gooey filter
- **`useAuth` hook** — wraps `AuthProvider` context; exposes `user`, `login`, `logout`
- **`ProtectedRoute`** — redirects unauthenticated users to `/login`
- **`legalSources.ts`** — static registry of country legal source URLs for map search

### PDF / OCR pipeline
- Crawler and `pdf_reader` updated to delegate extraction to the sidecar via HTTP when available
- Python Tesseract and OpenAI Vision fallback paths refined
- Old Rust OCR stubs removed from `pdf-reader/ocr-service/rust/` and `ai-service/pdf_reader/ocr_service/rust/` (now live in the sidecar)

---

## Test plan

- [ ] `make db` starts Postgres and Redis; containers are healthy
- [ ] `make migrate-sidecar` runs cleanly against the DB
- [ ] `make dev` starts all three processes (backend, sidecar, frontend) without error
- [ ] `POST /auth/register` creates a user; `POST /auth/login` returns a JWT
- [ ] `POST /auth/forgot-password` logs a reset link (SMTP not required in dev)
- [ ] `POST /extract-text` with a PDF returns extracted text; second upload of same file returns `cache_hit: true`
- [ ] Frontend mobile nav opens/closes, respects auth state, navigates correctly
- [ ] `MapSearch` page renders and country panel populates
- [ ] `make image` builds all Docker images and `docker compose up -d` starts cleanly

---

## Notes / follow-up

- `JWT_SECRET` must be set in `.env` for auth to work; service will crash at runtime otherwise
- `SMTP_HOST` is optional; without it, reset links are printed to the backend log
- The `PYTHON` path in the Makefile is macOS/Homebrew-specific — Linux deployments use the system `python3`; Docker build is unaffected
- `rdtii-frontend/public/Description_video.mp4` (85 MB) is committed as a binary; consider moving to a CDN or Git LFS before this branch is long-lived

🤖 Generated with [Claude Code](https://claude.com/claude-code)
