-- Migration 008: Sync required-country Discovery sources to the database registry

INSERT INTO discovery_sources (
    country_code, name, base_url, domains, source_grade, adapter, source_type,
    languages, pillars, indicators, priority, notes, position
)
VALUES
    (
        'AUS',
        'Department of Foreign Affairs and Trade',
        'https://www.dfat.gov.au',
        '["dfat.gov.au","www.dfat.gov.au"]'::jsonb,
        'primary',
        'search_engine',
        'government_portal',
        '["en"]'::jsonb,
        '[6]'::jsonb,
        '["6.5"]'::jsonb,
        90,
        'Official treaty texts and digital economy agreement pages for binding data-flow commitments.',
        1
    ),
    (
        'AUS',
        'Office of the Australian Information Commissioner',
        'https://www.oaic.gov.au',
        '["oaic.gov.au","www.oaic.gov.au"]'::jsonb,
        'primary',
        'search_engine',
        'regulator',
        '["en"]'::jsonb,
        '[7]'::jsonb,
        '["7.4"]'::jsonb,
        90,
        'Official privacy impact assessment rules and guidance.',
        2
    ),
    (
        'MYS',
        'Companies Commission of Malaysia',
        'https://www.ssm.com.my',
        '["ssm.com.my","www.ssm.com.my"]'::jsonb,
        'primary',
        'search_engine',
        'regulator',
        '["en","ms"]'::jsonb,
        '[7]'::jsonb,
        '["7.3"]'::jsonb,
        85,
        'Official Companies Act 2016 text and company-record retention materials.',
        3
    ),
    (
        'MYS',
        'Ministry of Investment Trade and Industry',
        'https://fta.miti.gov.my',
        '["fta.miti.gov.my"]'::jsonb,
        'primary',
        'search_engine',
        'government_portal',
        '["en","ms"]'::jsonb,
        '[6]'::jsonb,
        '["6.5"]'::jsonb,
        85,
        'Official CPTPP text and electronic-commerce commitment pages.',
        4
    )
ON CONFLICT (country_code, name, base_url) DO UPDATE SET
    domains = EXCLUDED.domains,
    source_grade = EXCLUDED.source_grade,
    adapter = EXCLUDED.adapter,
    source_type = EXCLUDED.source_type,
    languages = EXCLUDED.languages,
    pillars = EXCLUDED.pillars,
    indicators = EXCLUDED.indicators,
    priority = EXCLUDED.priority,
    notes = EXCLUDED.notes,
    position = EXCLUDED.position,
    updated_at = NOW();
