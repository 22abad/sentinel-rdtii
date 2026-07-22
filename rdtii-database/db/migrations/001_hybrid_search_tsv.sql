-- Hybrid search: add the lexical arm to document_chunks.
--
-- init.sql already carries this for a fresh `docker compose up`. This file is
-- for a long-lived dev volume created before hybrid search existed. Without
-- it, retrieval still works — rag/hybrid.py probes for the column and degrades
-- to dense-only — it just loses the lexical arm.
--
-- Apply:  docker exec -i rdtii-postgres psql -U rdtii_user -d rdtii \
--           < rdtii-database/db/migrations/001_hybrid_search_tsv.sql
--
-- Idempotent. ADD COLUMN of a STORED generated column rewrites the table, so
-- expect it to take a moment on a large corpus.

ALTER TABLE document_chunks
    ADD COLUMN IF NOT EXISTS chunk_tsv TSVECTOR
    GENERATED ALWAYS AS (to_tsvector('simple', chunk_text)) STORED;

CREATE INDEX IF NOT EXISTS idx_document_chunks_tsv
    ON document_chunks USING GIN (chunk_tsv);
