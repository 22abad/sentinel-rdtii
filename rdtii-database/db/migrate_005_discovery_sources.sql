-- Migration 005: Discovery source registry persistence
-- Run once: psql -U rdtii_user -d rdtii -f migrate_005_discovery_sources.sql

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS discovery_countries (
    country_code VARCHAR(3) PRIMARY KEY,
    label        TEXT        NOT NULL,
    languages    JSONB       NOT NULL DEFAULT '[]',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS discovery_sources (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    country_code     VARCHAR(3)  NOT NULL REFERENCES discovery_countries(country_code) ON DELETE CASCADE,
    name             TEXT        NOT NULL,
    base_url         TEXT        NOT NULL,
    domains          JSONB       NOT NULL DEFAULT '[]',
    source_grade     TEXT        NOT NULL DEFAULT 'primary' CHECK (source_grade IN ('primary', 'secondary', 'unknown')),
    adapter          TEXT        NOT NULL DEFAULT 'search_engine',
    source_type      TEXT        NOT NULL DEFAULT 'official_website',
    languages        JSONB       NOT NULL DEFAULT '[]',
    pillars          JSONB       NOT NULL DEFAULT '[]',
    indicators       JSONB       NOT NULL DEFAULT '[]',
    search_paths     JSONB       NOT NULL DEFAULT '[]',
    include_patterns JSONB       NOT NULL DEFAULT '[]',
    exclude_patterns JSONB       NOT NULL DEFAULT '[]',
    priority         INTEGER     NOT NULL DEFAULT 50,
    notes            TEXT        NOT NULL DEFAULT '',
    position         INTEGER     NOT NULL DEFAULT 0,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_discovery_sources_country_position
    ON discovery_sources(country_code, position);

WITH duplicate_sources AS (
    SELECT id,
           ROW_NUMBER() OVER (
               PARTITION BY country_code, name, base_url
               ORDER BY created_at, id
           ) AS duplicate_rank
    FROM discovery_sources
)
DELETE FROM discovery_sources
WHERE id IN (
    SELECT id
    FROM duplicate_sources
    WHERE duplicate_rank > 1
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_discovery_sources_country_name_url
    ON discovery_sources(country_code, name, base_url);

CREATE TABLE IF NOT EXISTS discovery_source_versions (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    registry    JSONB       NOT NULL,
    changed_by  UUID        REFERENCES users(id) ON DELETE SET NULL,
    change_note TEXT        NOT NULL DEFAULT '',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS discovery_source_audit_events (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_id    UUID        REFERENCES users(id) ON DELETE SET NULL,
    action      TEXT        NOT NULL,
    details     JSONB       NOT NULL DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO discovery_countries (country_code, label, languages)
VALUES
    ('AUS', 'Australia', '["en"]'::jsonb),
    ('CHN', 'China', '["zh","en"]'::jsonb),
    ('MYS', 'Malaysia', '["en","ms"]'::jsonb),
    ('SGP', 'Singapore', '["en"]'::jsonb),
    ('THA', 'Thailand', '["th","en"]'::jsonb)
ON CONFLICT (country_code) DO NOTHING;

INSERT INTO discovery_sources (
    country_code, name, base_url, domains, source_grade, adapter, source_type,
    languages, pillars, priority, notes, position
)
VALUES
    ('AUS', 'Federal Register of Legislation', 'https://www.legislation.gov.au', '["legislation.gov.au","www.legislation.gov.au"]'::jsonb, 'primary', 'australia_legislation', 'statute_portal', '["en"]'::jsonb, '[6,7]'::jsonb, 100, 'Official Australian legislation register; verified for Privacy Act 1988 and Telecommunications (Interception and Access) Act 1979.', 0),

    ('CHN', 'National Laws and Regulations Database', 'https://flk.npc.gov.cn', '["flk.npc.gov.cn"]'::jsonb, 'primary', 'china_flk', 'statute_portal', '["zh"]'::jsonb, '[6,7]'::jsonb, 100, 'Official national laws and regulations database', 0),
    ('CHN', 'State Council', 'https://www.gov.cn', '["gov.cn","www.gov.cn"]'::jsonb, 'primary', 'search_engine', 'government_portal', '["zh","en"]'::jsonb, '[6,7]'::jsonb, 90, '', 1),
    ('CHN', 'Cyberspace Administration of China', 'https://www.cac.gov.cn', '["cac.gov.cn","www.cac.gov.cn"]'::jsonb, 'primary', 'search_engine', 'regulator', '["zh"]'::jsonb, '[6,7]'::jsonb, 90, '', 2),

    ('MYS', 'Attorney General''s Chambers of Malaysia', 'https://lom.agc.gov.my', '["lom.agc.gov.my"]'::jsonb, 'primary', 'malaysia_lom', 'statute_portal', '["en","ms"]'::jsonb, '[6,7]'::jsonb, 100, 'Official AGC legislation portal; verified for Cyber Security Act 2024 Act 854 record.', 0),
    ('MYS', 'Personal Data Protection Department', 'https://www.pdp.gov.my', '["pdp.gov.my","www.pdp.gov.my"]'::jsonb, 'primary', 'search_engine', 'regulator', '["en","ms"]'::jsonb, '[6,7]'::jsonb, 90, 'Official Commissioner source; verified for PDPA 2010 and PDPA Amendment Act 2024 pages.', 1),
    ('MYS', 'National Cyber Security Agency', 'https://www.nacsa.gov.my', '["nacsa.gov.my","www.nacsa.gov.my"]'::jsonb, 'primary', 'search_engine', 'regulator', '["en","ms"]'::jsonb, '[7]'::jsonb, 85, 'Official NACSA legal page and gazette PDFs for Cyber Security Act 2024 commencement and incident notification regulations.', 2),

    ('SGP', 'Singapore Statutes Online', 'https://sso.agc.gov.sg', '["sso.agc.gov.sg"]'::jsonb, 'primary', 'singapore_sso', 'statute_portal', '["en"]'::jsonb, '[6,7]'::jsonb, 100, '', 0),
    ('SGP', 'Personal Data Protection Commission', 'https://www.pdpc.gov.sg', '["pdpc.gov.sg","www.pdpc.gov.sg"]'::jsonb, 'primary', 'search_engine', 'regulator', '["en"]'::jsonb, '[6,7]'::jsonb, 85, 'Official PDPC source; verified for DPIA guide.', 1),
    ('SGP', 'Ministry of Trade and Industry', 'https://www.mti.gov.sg', '["mti.gov.sg","www.mti.gov.sg"]'::jsonb, 'primary', 'search_engine', 'government_portal', '["en"]'::jsonb, '[6]'::jsonb, 85, 'Official MTI treaty pages; verified for DEPA and SADEA digital economy agreements.', 2),
    ('SGP', 'Infocomm Media Development Authority', 'https://www.imda.gov.sg', '["imda.gov.sg","www.imda.gov.sg"]'::jsonb, 'primary', 'search_engine', 'regulator', '["en"]'::jsonb, '[7]'::jsonb, 80, '', 3),

    ('THA', 'Office of the Council of State', 'https://www.ocs.go.th', '["ocs.go.th","searchlaw.ocs.go.th"]'::jsonb, 'primary', 'thailand_ocs', 'statute_portal', '["th","en"]'::jsonb, '[6,7]'::jsonb, 100, '', 0),
    ('THA', 'Electronic Transactions Development Agency', 'https://www.etda.or.th', '["etda.or.th","www.etda.or.th"]'::jsonb, 'primary', 'search_engine', 'regulator', '["th","en"]'::jsonb, '[6,7]'::jsonb, 85, '', 1),
    ('THA', 'Personal Data Protection Committee', 'https://www.pdpc.or.th', '["pdpc.or.th","www.pdpc.or.th"]'::jsonb, 'primary', 'search_engine', 'regulator', '["th","en"]'::jsonb, '[6,7]'::jsonb, 85, '', 2)
ON CONFLICT (country_code, name, base_url) DO UPDATE SET
    domains = EXCLUDED.domains,
    source_grade = EXCLUDED.source_grade,
    adapter = EXCLUDED.adapter,
    source_type = EXCLUDED.source_type,
    languages = EXCLUDED.languages,
    pillars = EXCLUDED.pillars,
    priority = EXCLUDED.priority,
    notes = EXCLUDED.notes,
    position = EXCLUDED.position,
    updated_at = NOW();
