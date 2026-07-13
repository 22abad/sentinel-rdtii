-- Migration 007: Use specialized official-source discovery adapters

UPDATE discovery_sources
SET adapter = 'australia_legislation',
    updated_at = NOW()
WHERE country_code = 'AUS'
  AND name = 'Federal Register of Legislation'
  AND base_url = 'https://www.legislation.gov.au';

UPDATE discovery_sources
SET adapter = 'malaysia_lom',
    updated_at = NOW()
WHERE country_code = 'MYS'
  AND name = 'Attorney General''s Chambers of Malaysia'
  AND base_url = 'https://lom.agc.gov.my';
