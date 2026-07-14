# Timor-Leste (TLS) — bonus-economy scouting note

_Final-round bonus: Timor-Leste is worth 20 points (double a normal economy)
as the designated "hard challenge". Ten-minute reachability probe, Jul 14._

## Source reachability (probed)

| Source | Status | Relevance |
|---|---|---|
| Jornal da República (`mj.gov.tl/jornal`) — official gazette | ✅ HTTP 200 | THE primary legal source; Portuguese/Tetum |
| Government portal (`timor-leste.gov.tl`) | ✅ 200 | decrees, announcements |
| Banco Central (`bancocentral.tl`) | ✅ 200, rich | P12 payment regulation |
| WIPO Lex TL profile | ✅ 200 | P4 IP laws, English metadata |
| ILO NATLEX | ⚠️ 403 (bot-blocked) | secondary |
| `jornal.gov.tl`, `anc.tl` | ❌ unreachable | use mj.gov.tl mirror |

## Feasibility read

- **Doable as a bonus**: the gazette is plain HTTP (no JS wall), and our
  extraction already handles Portuguese-adjacent languages (Indonesian
  worked; DeepSeek handles Portuguese well).
- Legal landscape is thin by design (no comprehensive data-protection law),
  which for RDTII means many low-scoring indicators — *fast* to evidence.
- Synergy: Thursday's guest professor (trade law, Portugal) reads the
  source language natively — ideal human-review partner for a TLS sample.

## If we go (post-Round-1 submission)

1. Add `TLS` economy + a `timor_leste` gazette adapter (mj.gov.tl paths).
2. Baseline: no official TLS sheet exists in the Round 2 database — output
   would be pure NEW discovery (tagged, human-review gated).
3. Time-box: one day; anything more steals from the finale prep.
