-- Migration 004: Workbench canvas layout persistence
-- Run once: psql -U rdtii_user -d rdtii -f migrate_004_workbench_canvases.sql

CREATE TABLE IF NOT EXISTS workbench_canvases (
    owner_id   UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    scope_key  TEXT        NOT NULL DEFAULT 'default',
    layout     JSONB       NOT NULL DEFAULT '{"version":1,"nodes":[],"edges":[]}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (owner_id, scope_key)
);
