from __future__ import annotations

import os
import ssl

# macOS often has local certificate-chain issues; keep the crawler's historical
# permissive context for direct fallback probes.
_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE

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
