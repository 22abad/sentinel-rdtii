-- ============================================================
-- UN-DigitalTrade-AI-Mapper Database Schema
-- PostgreSQL 17 + pgvector
--
-- Fresh development bootstrap only: this file is intentionally not an
-- incremental or idempotent migration. Run `make db-reset`, which recreates
-- the local volumes before Docker executes this schema. Introduce a versioned
-- migration baseline before any environment contains data that must persist.
-- ============================================================

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================================
-- Reference Data
-- ============================================================

CREATE TABLE countries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code VARCHAR(3) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    region VARCHAR(100),
    is_escap_member BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Comprehensive list of ESCAP members
INSERT INTO countries (code, name, region) VALUES 
('AFG', 'Afghanistan', 'Central Asia'),
('ARM', 'Armenia', 'Central Asia'),
('AZE', 'Azerbaijan', 'Central Asia'),
('AUS', 'Australia', 'Oceania'),
('BGD', 'Bangladesh', 'South Asia'),
('BTN', 'Bhutan', 'South Asia'),
('BRU', 'Brunei', 'Southeast Asia'),
('KHM', 'Cambodia', 'Southeast Asia'),
('CHN', 'China', 'East Asia'),
('FJI', 'Fiji', 'Oceania'),
('GEO', 'Georgia', 'Central Asia'),
('IND', 'India', 'South Asia'),
('IDN', 'Indonesia', 'Southeast Asia'),
('IRN', 'Iran', 'South Asia'),
('JPN', 'Japan', 'East Asia'),
('KAZ', 'Kazakhstan', 'Central Asia'),
('KGZ', 'Kyrgyzstan', 'Central Asia'),
('LAO', 'Laos', 'Southeast Asia'),
('MYS', 'Malaysia', 'Southeast Asia'),
('MDV', 'Maldives', 'South Asia'),
('MNG', 'Mongolia', 'East Asia'),
('MMR', 'Myanmar', 'Southeast Asia'),
('NPL', 'Nepal', 'South Asia'),
('NZL', 'New Zealand', 'Oceania'),
('PAK', 'Pakistan', 'South Asia'),
('PHL', 'Philippines', 'Southeast Asia'),
('KOR', 'Republic of Korea', 'East Asia'),
('RUS', 'Russian Federation', 'North Asia'),
('WSM', 'Samoa', 'Oceania'),
('SGP', 'Singapore', 'Southeast Asia'),
('LKA', 'Sri Lanka', 'South Asia'),
('TJK', 'Tajikistan', 'Central Asia'),
('THA', 'Thailand', 'Southeast Asia'),
('TUR', 'Turkey', 'Central Asia'),
('TKM', 'Turkmenistan', 'Central Asia'),
('UZB', 'Uzbekistan', 'Central Asia'),
('VNM', 'Vietnam', 'Southeast Asia')
ON CONFLICT (code) DO NOTHING;

CREATE TABLE rdtii_pillars (
    pillar_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pillar_number INTEGER NOT NULL,
    pillar_name VARCHAR(255) NOT NULL,
    country_code VARCHAR(3) REFERENCES countries(code),
    criterion_id VARCHAR(50) NOT NULL,
    criterion_name VARCHAR(500) NOT NULL,
    indicator_id VARCHAR(50) NOT NULL,
    indicator_description TEXT,
    weight_score NUMERIC(5, 3),
    overall_pillar_score NUMERIC(5, 3),
    "references" JSONB DEFAULT '[]',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- Document Ingestion Pipeline
-- ============================================================

CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    filename VARCHAR(500) NOT NULL,
    file_path VARCHAR(1000) NOT NULL,
    country_code VARCHAR(3) REFERENCES countries(code),
    source_url VARCHAR(2000) UNIQUE,
    upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'downloaded', 'processing', 'processed', 'failed')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE document_sections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    section_number VARCHAR(50),
    article_title VARCHAR(500),
    raw_text TEXT NOT NULL,
    page_start INTEGER,
    page_end INTEGER,
    source_pdf_offset INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- RAG: Chunks & Vector Embeddings
-- ============================================================

CREATE TABLE document_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    section_id UUID NOT NULL REFERENCES document_sections(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    chunk_text TEXT NOT NULL,
    chunk_metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE chunk_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chunk_id UUID NOT NULL REFERENCES document_chunks(id) ON DELETE CASCADE,
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    country_code VARCHAR(3) REFERENCES countries(code),
    embedding vector(384),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_chunk_embeddings_embedding ON chunk_embeddings USING ivfflat (embedding vector_cosine_ops);
CREATE INDEX idx_chunk_embeddings_document ON chunk_embeddings(document_id);
CREATE INDEX idx_chunk_embeddings_country ON chunk_embeddings(country_code);

-- ============================================================
-- OCR / Extraction Cache (used by extract-sidecar)
-- ============================================================

CREATE TABLE extracted_documents (
    id           VARCHAR(36)  PRIMARY KEY,
    content_hash VARCHAR(64)  UNIQUE NOT NULL,
    filename     VARCHAR(500) NOT NULL,
    source_type  VARCHAR(50),
    ocr_provider VARCHAR(100),
    extracted_text TEXT        NOT NULL,
    expires_at   TIMESTAMP,
    created_at   TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- Extraction & Mapping
-- ============================================================

CREATE TABLE extracted_obligations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    section_id UUID NOT NULL REFERENCES document_sections(id) ON DELETE CASCADE,
    obligation_type VARCHAR(100),
    extracted_text TEXT NOT NULL,
    confidence_score NUMERIC(3, 2),
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'reviewed', 'rejected')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE regulation_mappings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    obligation_id UUID NOT NULL REFERENCES extracted_obligations(id) ON DELETE CASCADE,
    pillar_id UUID NOT NULL REFERENCES rdtii_pillars(pillar_id),
    criterion_id VARCHAR(50),
    evidence_text TEXT,
    compliance_status VARCHAR(20) CHECK (compliance_status IN ('compliant', 'partial', 'non-compliant', 'unknown')),
    mapped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    audited_by VARCHAR(100)
);

-- ============================================================
-- Transparency / Audit
-- ============================================================

CREATE TABLE audit_trail (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    mapping_id UUID NOT NULL REFERENCES regulation_mappings(id) ON DELETE CASCADE,
    source_section_id UUID NOT NULL REFERENCES document_sections(id) ON DELETE CASCADE,
    highlight_start INTEGER,
    highlight_end INTEGER,
    reviewer_notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- Optional: User Management
-- ============================================================

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(100) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE,
    role VARCHAR(20) DEFAULT 'viewer' CHECK (role IN ('admin', 'reviewer', 'viewer')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- Authentication & Access Control
-- ============================================================

ALTER TABLE users
    ADD COLUMN password_hash VARCHAR(255) NOT NULL DEFAULT '',
    ADD COLUMN is_active     BOOLEAN      NOT NULL DEFAULT TRUE,
    ADD COLUMN last_login    TIMESTAMP;

CREATE TABLE password_reset_tokens (
    id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token      VARCHAR(64) UNIQUE NOT NULL,
    expires_at TIMESTAMP   NOT NULL,
    used       BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP   DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_prt_token   ON password_reset_tokens(token);
CREATE INDEX idx_prt_user_id ON password_reset_tokens(user_id);

ALTER TABLE documents
    ADD COLUMN uploaded_by UUID REFERENCES users(id) ON DELETE SET NULL;

CREATE INDEX idx_documents_uploaded_by ON documents(uploaded_by);

CREATE TABLE user_document_access (
    user_id      UUID        NOT NULL REFERENCES users(id)      ON DELETE CASCADE,
    document_id  UUID        NOT NULL REFERENCES documents(id)  ON DELETE CASCADE,
    access_level VARCHAR(20) NOT NULL DEFAULT 'viewer'
        CHECK (access_level IN ('owner', 'reviewer', 'viewer')),
    granted_by   UUID        REFERENCES users(id) ON DELETE SET NULL,
    granted_at   TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, document_id)
);

CREATE INDEX idx_uda_user_id     ON user_document_access(user_id);
CREATE INDEX idx_uda_document_id ON user_document_access(document_id);

CREATE TABLE workbench_canvases (
    owner_id   UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    scope_key  TEXT        NOT NULL DEFAULT 'default',
    layout     JSONB       NOT NULL DEFAULT '{"version":1,"nodes":[],"edges":[]}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (owner_id, scope_key)
);

-- ============================================================
-- Activity log — a general, queryable audit trail of every step a
-- user (or the system) takes: ingest, extract, discover, review, export.
-- Powers the frontend "activity timeline" and makes work reproducible.
-- ============================================================

CREATE TABLE activity_log (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID,                    -- who (NULL for system/CLI actions)
    action      VARCHAR(50) NOT NULL,    -- ingest | extract | discover | review | export | ...
    target_type VARCHAR(50),             -- document | mapping | economy | workflow | ...
    target_id   VARCHAR(200),            -- id/reference of the acted-on object
    economy     VARCHAR(64),             -- economy context, when relevant
    status      VARCHAR(20) DEFAULT 'success' CHECK (status IN ('success','failed','partial')),
    summary     TEXT,                    -- short human-readable result summary
    detail      JSONB,                   -- structured detail (counts, params, output refs)
    created_at  TIMESTAMP   DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_activity_log_user    ON activity_log(user_id, created_at DESC);
CREATE INDEX idx_activity_log_target  ON activity_log(target_type, target_id);
CREATE INDEX idx_activity_log_created ON activity_log(created_at DESC);

-- ============================================================
-- Verified evidence — a reusable, deduplicated store of extraction
-- results (one indicator mapping = one row). "Work done once is banked":
-- the same (economy, indicator, law, quote) is never stored twice, and an
-- approved row can be reused instead of re-extracting on a later run.
-- ============================================================

CREATE TABLE verified_evidence (
    id             UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    economy        VARCHAR(64)  NOT NULL,
    indicator_id   VARCHAR(20)  NOT NULL,   -- e.g. 'P6-I4'
    law_name       VARCHAR(500) NOT NULL,
    law_name_norm  VARCHAR(500) NOT NULL,   -- normalized, for dedup
    verbatim_quote TEXT         NOT NULL,
    quote_hash     VARCHAR(64)  NOT NULL,   -- sha256 of the normalized quote
    article        VARCHAR(200),
    source_url     VARCHAR(2000),
    source_sha256  VARCHAR(64),             -- provenance of the source document
    score          NUMERIC,
    review_status  VARCHAR(20)  DEFAULT 'draft' CHECK (review_status IN ('draft','approved','rejected')),
    created_by     UUID,
    created_at     TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    updated_at     TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (economy, indicator_id, law_name_norm, quote_hash)
);
CREATE INDEX idx_verified_evidence_lookup ON verified_evidence(economy, indicator_id, review_status);
CREATE INDEX idx_verified_evidence_source ON verified_evidence(source_sha256);

-- ============================================================
-- Extraction cache — skip re-running the LLM on identical content.
-- Keyed by the SHA-256 of the exact source text; stores the full
-- extraction response JSON so a repeat run returns it verbatim.
-- ============================================================

CREATE TABLE extraction_cache (
    source_sha256 VARCHAR(64) PRIMARY KEY,
    response      JSONB       NOT NULL,
    provider      VARCHAR(100),
    created_at    TIMESTAMP   DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- Discovery Source Registry
-- ============================================================

CREATE TABLE discovery_countries (
    country_code VARCHAR(3) PRIMARY KEY,
    label        TEXT        NOT NULL,
    languages    JSONB       NOT NULL DEFAULT '[]',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE discovery_sources (
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
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (country_code, name, base_url)
);

CREATE INDEX idx_discovery_sources_country_position
    ON discovery_sources(country_code, position);

CREATE TABLE discovery_source_versions (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    registry    JSONB       NOT NULL,
    changed_by  UUID        REFERENCES users(id) ON DELETE SET NULL,
    change_note TEXT        NOT NULL DEFAULT '',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE discovery_source_audit_events (
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
    ('THA', 'Thailand', '["th","en"]'::jsonb);

INSERT INTO discovery_sources (
    country_code, name, base_url, domains, source_grade, adapter, source_type,
    languages, pillars, indicators, search_paths, include_patterns,
    exclude_patterns, priority, notes, position
)
VALUES
    ('AUS', 'Federal Register of Legislation', 'https://www.legislation.gov.au', '["legislation.gov.au","www.legislation.gov.au"]'::jsonb, 'primary', 'australia_legislation', 'statute_portal', '["en"]'::jsonb, '[6,7]'::jsonb, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, 100, 'Official Australian legislation register; verified for Privacy Act 1988 and Telecommunications (Interception and Access) Act 1979.', 0),
    ('AUS', 'Department of Foreign Affairs and Trade', 'https://www.dfat.gov.au', '["dfat.gov.au","www.dfat.gov.au"]'::jsonb, 'primary', 'search_engine', 'government_portal', '["en"]'::jsonb, '[6]'::jsonb, '["6.5"]'::jsonb, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, 90, 'Official treaty texts and digital economy agreement pages for binding data-flow commitments.', 1),
    ('AUS', 'Office of the Australian Information Commissioner', 'https://www.oaic.gov.au', '["oaic.gov.au","www.oaic.gov.au"]'::jsonb, 'primary', 'search_engine', 'regulator', '["en"]'::jsonb, '[7]'::jsonb, '["7.4"]'::jsonb, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, 90, 'Official privacy impact assessment rules and guidance.', 2),

    ('CHN', 'National Laws and Regulations Database', 'https://flk.npc.gov.cn', '["flk.npc.gov.cn"]'::jsonb, 'primary', 'china_flk', 'statute_portal', '["zh"]'::jsonb, '[6,7]'::jsonb, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, 100, 'Official national laws and regulations database', 0),
    ('CHN', 'State Council', 'https://www.gov.cn', '["gov.cn","www.gov.cn"]'::jsonb, 'primary', 'search_engine', 'government_portal', '["zh","en"]'::jsonb, '[6,7]'::jsonb, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, 90, '', 1),
    ('CHN', 'Cyberspace Administration of China', 'https://www.cac.gov.cn', '["cac.gov.cn","www.cac.gov.cn"]'::jsonb, 'primary', 'search_engine', 'regulator', '["zh"]'::jsonb, '[6,7]'::jsonb, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, 90, '', 2),

    ('MYS', 'Attorney General''s Chambers of Malaysia', 'https://lom.agc.gov.my', '["lom.agc.gov.my"]'::jsonb, 'primary', 'malaysia_lom', 'statute_portal', '["en","ms"]'::jsonb, '[6,7]'::jsonb, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, 100, 'Official AGC legislation portal; verified for Cyber Security Act 2024 Act 854 record.', 0),
    ('MYS', 'Personal Data Protection Department', 'https://www.pdp.gov.my', '["pdp.gov.my","www.pdp.gov.my"]'::jsonb, 'primary', 'search_engine', 'regulator', '["en","ms"]'::jsonb, '[6,7]'::jsonb, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, 90, 'Official Commissioner source; verified for PDPA 2010 and PDPA Amendment Act 2024 pages.', 1),
    ('MYS', 'National Cyber Security Agency', 'https://www.nacsa.gov.my', '["nacsa.gov.my","www.nacsa.gov.my"]'::jsonb, 'primary', 'search_engine', 'regulator', '["en","ms"]'::jsonb, '[7]'::jsonb, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, 85, 'Official NACSA legal page and gazette PDFs for Cyber Security Act 2024 commencement and incident notification regulations.', 2),
    ('MYS', 'Companies Commission of Malaysia', 'https://www.ssm.com.my', '["ssm.com.my","www.ssm.com.my"]'::jsonb, 'primary', 'search_engine', 'regulator', '["en","ms"]'::jsonb, '[7]'::jsonb, '["7.3"]'::jsonb, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, 85, 'Official Companies Act 2016 text and company-record retention materials.', 3),
    ('MYS', 'Ministry of Investment Trade and Industry', 'https://fta.miti.gov.my', '["fta.miti.gov.my"]'::jsonb, 'primary', 'search_engine', 'government_portal', '["en","ms"]'::jsonb, '[6]'::jsonb, '["6.5"]'::jsonb, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, 85, 'Official CPTPP text and electronic-commerce commitment pages.', 4),

    ('SGP', 'Singapore Statutes Online', 'https://sso.agc.gov.sg', '["sso.agc.gov.sg"]'::jsonb, 'primary', 'singapore_sso', 'statute_portal', '["en"]'::jsonb, '[6,7]'::jsonb, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, 100, '', 0),
    ('SGP', 'Personal Data Protection Commission', 'https://www.pdpc.gov.sg', '["pdpc.gov.sg","www.pdpc.gov.sg"]'::jsonb, 'primary', 'search_engine', 'regulator', '["en"]'::jsonb, '[6,7]'::jsonb, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, 85, 'Official PDPC source; verified for DPIA guide.', 1),
    ('SGP', 'Ministry of Trade and Industry', 'https://www.mti.gov.sg', '["mti.gov.sg","www.mti.gov.sg","isomer-user-content.by.gov.sg"]'::jsonb, 'primary', 'official_index', 'government_portal', '["en"]'::jsonb, '[6]'::jsonb, '["6.5"]'::jsonb, '["/trade-international-economic-relations/agreements/digital-economy-agreements-dea/sadea/"]'::jsonb, '["australia-singapore-digital-economy-agreement.*\\.pdf"]'::jsonb, '[]'::jsonb, 85, 'Official MTI treaty page and Singapore Government Isomer-hosted SADEA PDF for the binding Article 23 data-flow commitment.', 2),
    ('SGP', 'Infocomm Media Development Authority', 'https://www.imda.gov.sg', '["imda.gov.sg","www.imda.gov.sg"]'::jsonb, 'primary', 'search_engine', 'regulator', '["en"]'::jsonb, '[7]'::jsonb, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, 80, '', 3),

    ('THA', 'Office of the Council of State', 'https://www.ocs.go.th', '["ocs.go.th","www.ocs.go.th","searchlaw.ocs.go.th"]'::jsonb, 'primary', 'thailand_ocs', 'statute_portal', '["th","en"]'::jsonb, '[6,7]'::jsonb, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, 100, '', 0),
    ('THA', 'Electronic Transactions Development Agency', 'https://www.etda.or.th', '["etda.or.th","www.etda.or.th"]'::jsonb, 'primary', 'search_engine', 'regulator', '["th","en"]'::jsonb, '[6,7]'::jsonb, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, 85, '', 1),
    ('THA', 'Personal Data Protection Committee', 'https://www.pdpc.or.th', '["pdpc.or.th","www.pdpc.or.th"]'::jsonb, 'primary', 'search_engine', 'regulator', '["th","en"]'::jsonb, '[6,7]'::jsonb, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, 85, '', 2);

-- ============================================================
-- Final Embedding Shape & Sidecar Links
-- ============================================================

ALTER TABLE chunk_embeddings ALTER COLUMN embedding TYPE vector(384);
DROP INDEX idx_chunk_embeddings_embedding;
CREATE INDEX idx_chunk_embeddings_embedding
    ON chunk_embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

ALTER TABLE extracted_documents
    ADD COLUMN source_url TEXT;

CREATE INDEX idx_ext_docs_hash ON extracted_documents(content_hash);
CREATE INDEX idx_ext_docs_url ON extracted_documents(source_url)
    WHERE source_url IS NOT NULL;
CREATE INDEX idx_ext_docs_expires ON extracted_documents(expires_at)
    WHERE expires_at IS NOT NULL;

ALTER TABLE documents
    ADD COLUMN sidecar_doc_id TEXT
    REFERENCES extracted_documents(id) ON DELETE SET NULL;

ALTER TABLE document_chunks
    ADD COLUMN extracted_doc_id TEXT
    REFERENCES extracted_documents(id) ON DELETE SET NULL;
