from __future__ import annotations

import os
import ssl

# Live Discovery evidence must retain normal TLS certificate and hostname
# verification. A certificate failure is a retrieval failure, not a live hit.
# python.org macOS builds ship without the system CA store wired up, which
# made every Wayback fallback die with CERTIFICATE_VERIFY_FAILED on a valid
# chain; certifi provides the standard Mozilla bundle without weakening
# verification in any way.
try:
    import certifi
    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:  # pragma: no cover — fall back to platform defaults
    _SSL_CTX = ssl.create_default_context()

# Download directory for crawler-managed temporary files.
DOWNLOADS_DIR = "./downloads"
if not os.path.exists(DOWNLOADS_DIR):
    os.makedirs(DOWNLOADS_DIR)

# Invalid URL schemes that should never be navigated or downloaded.
INVALID_URL_PATTERNS = [
    r"javascript:",
    r"mailto:",
    r"tel:",
    r"fax:",
]

# ── 已知受限站点的替代数据源 Fallback 映射 ─────────────────────────
# 当主 URL 爬取失败时，自动尝试替代来源获取同类内容
KNOWN_ALTERNATIVES: dict[str, list[dict]] = {
    "ratchakitcha.soc.go.th": [
        {
            "source": "ocs.go.th",
            "type": "search_ocs",
            "priority": 1,
            "note": "Thai Council of State law database (no Cloudflare)",
        },
    ],
    "meity.gov.in": [
        {
            "source": "digitalindia.gov.in",
            "type": "web",
            "priority": 1,
            "note": "Digital India portal — alternative to MEITY",
        },
        {
            "source": "mygov.in",
            "type": "web",
            "priority": 2,
            "note": "MyGov India — general government portal",
        },
    ],
    "indiacode.nic.in": [
        {
            "source": "digitalindia.gov.in",
            "type": "web",
            "priority": 1,
            "note": "Digital India portal — alternative to India Code",
        },
    ],
    "india.gov.in": [
        {
            "source": "mygov.in",
            "type": "web",
            "priority": 1,
            "note": "MyGov India — alternative national portal",
        },
    ],
    "mdes.go.th": [
        {
            "source": "ocs.go.th",
            "type": "search_ocs",
            "priority": 1,
            "note": "Thai Council of State law database — alternative to MDES",
        },
    ],
}
