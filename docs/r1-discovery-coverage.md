# Round 1 — discovery coverage across Pillars 6 & 7

_This is a **discovery heatmap**: it shows, per provided economy and per RDTII
indicator, where our tool banked **NEW verified evidence** (a verbatim, in-force
provision absent from the official ESCAP inventory). It is generated directly
from the checked-in law library (`data/law_library/manifest.jsonl`); every 🆕
cell is backed by a verbatim provision + SHA-256 + an official-source URL._

## Heatmap

| Economy | 6.1 | 6.2 | 6.3 | 6.4 | 7.1 | 7.2 | 7.3 | 7.4 | 7.5 |
|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| 🇸🇬 SGP | · | · | ○ | 🆕 | 🆕 | · | 🆕 | · | · |
| 🇲🇾 MYS | · | · | ○ | · | 🆕 | · | 🆕 | 🆕 | · |
| 🇦🇺 AUS | · | · | ○ | 🆕 | 🆕 | 🆕 | 🆕 | · | 🆕 |

**Legend** — 🆕 NEW verified discovery banked · KNOWN baseline law covers this
indicator (found by the seeded/live pipeline, not a discovery) · ○ no
requirement in this economy (a legitimate score-0, not a gap).

**11 (economy × indicator) cells carry a NEW discovery**, spread across 6 of the
9 indicators: 6.4 (×2 economies — Australia's cell alone is backed by **five**
sub-national statutes: VIC, NT, NSW, TAS, WA), 7.1 (×3), 7.2 (×1), 7.3 (×3),
7.4 (×1), 7.5 (×1).

## How to read the non-🆕 cells (honest framing)

- **· KNOWN, covered by the pipeline, not a discovery.** e.g. Singapore's
  Cybersecurity Act 2018 (7.2), the PDPA's DPO duty (7.4), or Companies Act 1967
  s.199(4) local-storage rule (6.2) are all real, in-force evidence — but they
  are principal Acts already in the ESCAP baseline, so they are **KNOWN**, not
  discoveries. They surface through the seeded/live run; we do not double-count
  them as NEW. The offline library deliberately holds our discoveries plus a
  thin set of KNOWN anchors, so empty cells here are **not** submission gaps.
- **○ 6.3 (infrastructure localization) — a verified negative.** Two deep
  research passes confirmed that Singapore, Malaysia and Australia impose **no
  hard data-infrastructure-localization requirement** for these sectors; their
  regimes are conditional cross-border flow (6.4) or access-preservation. Under
  RDTII, "no requirement" is the correct score-0 — reporting it as a gap would
  be the error. See `docs/new-law-candidates.md` (2026-07-16 P6 sweep).

## The 21 banked NEW laws behind this heatmap

- **🇦🇺 Australia (11):** Privacy & Data Protection Act 2014 (VIC) IPP 9 · Information
  Act 2002 (NT) IPP 9 · Privacy & Personal Information Protection Act 1998 (NSW)
  s 19(2) · **Personal Information Protection Act 2004 (TAS) PIPP 9** · **Privacy
  & Responsible Information Sharing Act 2024 (WA) IPP 9 (commenced 1 Jul 2026)** ·
  Archives Act 1983 · Digital ID Act 2024 · Identity Verification Services Act
  2023 · Crimes Act 1914 s 3LA · Surveillance Devices Act 2004 s 27KA · **Cyber
  Security Act 2024 (7.2 — dedicated cyber framework)**.
- **🇲🇾 Malaysia (6):** Credit Reporting Agencies Act 2010 · PDPA (Amendment) Act
  2024 s 12A (**DPO → 7.4**) / s 12B / s 43A · PDP Regulations 2013 · Consumer
  Protection (Electronic Trade Transaction) Regulations 2024 (**12.9**, a
  beyond-6/7 capability demonstration).
- **🇸🇬 Singapore (4):** PDP Regulations 2021 · MAS Notice 658 · Banking Act 1970
  s 47 · Healthcare Services (General) Regulations 2021.

_(20 of the 21 sit in the mandatory Pillars 6/7 across all three provided
economies; the odd one out, MYS CP(ETT) Regs 2024, is a Pillar 12 find that
demonstrates the tool scales to additional pillars.)_
