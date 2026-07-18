"""Best-effort law release-year resolution — four weighted signals, LLM decides.

A law's release/enactment year usually lives in its own citation ("… Act 2012",
"No. 26 of 2012"), so we can date a provision even with no source URL. Four
methods each vote a year with a confidence *portion*; the configured LLM makes
the final call, weighing those portions:

    portions:  title 0.35 + manifest 0.25 + llm 0.10  = 0.70   (the reliable group)
               in-text timeframe                       = 0.30   (law text has many years)
    tie order: title -> manifest -> timeframe -> llm

Grepping a lone year is unreliable (statutes cite several years — enactment,
amendment, "revised edition"), which is exactly why the signals are pooled and
the model arbitrates instead of trusting any single grep.
"""

from __future__ import annotations

import re

_YEAR_RE = re.compile(r"\b(1[89]\d{2}|20\d{2})\b")
_YMIN, _YMAX = 1800, 2099

# Confidence portions per method (user spec: title+manifest+llm = 0.70, timeframe = 0.30).
WEIGHTS = {"title": 0.35, "manifest": 0.25, "llm": 0.10, "timeframe": 0.30}
# Preference order for ties.
PREFERENCE = ["title", "manifest", "timeframe", "llm"]


def _years(text: str) -> list[int]:
    return [int(y) for y in _YEAR_RE.findall(text or "") if _YMIN <= int(y) <= _YMAX]


def _title_year(source_legislation: str, quote: str) -> int | None:
    """Earliest plausible year in the citation/title (enactment), then the quote.

    Earliest, because "2020 Revised Edition (Act 26 of 2012)" should date to the
    original 2012 enactment, not the consolidation.
    """
    for src in (source_legislation, quote):
        yrs = _years(src)
        if yrs:
            return min(yrs)
    return None


def _timeframe_year(last_update: str, timeframe_column: str) -> int | None:
    yrs = _years(f"{last_update} {timeframe_column}")
    return min(yrs) if yrs else None


def _normalise(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (name or "").lower()).strip()


def _manifest_year(source_legislation: str) -> int | None:
    """Match the name against the curated library; take its title/version year."""
    if not source_legislation:
        return None
    try:
        from law_library import load_library

        entries = load_library()
    except Exception:  # noqa: BLE001 — library optional / may be unprovisioned
        return None
    target = _normalise(source_legislation)
    if not target:
        return None
    target_tokens = set(target.split())
    best, best_overlap = None, 0.0
    for entry in entries:
        name = _normalise(entry.law_name)
        tokens = set(name.split())
        if not tokens:
            continue
        overlap = len(target_tokens & tokens) / len(tokens)
        if (name in target or target in name or overlap >= 0.6) and overlap > best_overlap:
            best, best_overlap = entry, overlap
    if best is None:
        return None
    yrs = _years(f"{best.law_name} {best.version}")
    return min(yrs) if yrs else None


def _llm_estimate_and_decide(
    provider, source_legislation: str, candidates: dict, tally: dict
) -> tuple[int | None, int | None]:
    """One model call: the LLM's own year estimate AND its final decision.

    Returns (estimate, final). The estimate becomes the weighted 'llm' vote; the
    final is the model's arbitration over every method's weighted portion.
    """
    if not provider or not source_legislation:
        return None, None
    method_lines = "; ".join(
        f"{m}={y} (portion {WEIGHTS[m]:.2f})" for m, y in candidates.items()
    ) or "none"
    totals = "; ".join(f"{y}: {w:.2f}" for y, w in sorted(tally.items())) or "none"
    prompt = (
        f"Law: {source_legislation}\n"
        f"Other methods estimated its release (enactment) year: {method_lines}.\n"
        f"Weighted totals per year: {totals}.\n\n"
        "Using your own knowledge AND these weighted portions (title+manifest+your "
        "own estimate together weigh 0.70; the in-text timeframe weighs 0.30), decide "
        "the single most likely ORIGINAL release year. On ties prefer "
        "title > manifest > timeframe > your-estimate.\n"
        "Respond in exactly two lines:\n"
        "ESTIMATE: <your own best 4-digit year, or NONE>\n"
        "FINAL: <the single 4-digit release year>"
    )
    try:
        out = provider.query(prompt, system="You resolve a law's release year.")
    except Exception:  # noqa: BLE001 — LLM failure must not break resolution
        return None, None
    estimate = final = None
    for line in out.splitlines():
        low = line.lower()
        yrs = _years(line)
        if low.startswith("estimate") and yrs:
            estimate = yrs[0]
        elif low.startswith("final") and yrs:
            final = yrs[0]
    if final is None:  # model ignored the format — take the last year it emitted
        yrs = _years(out)
        final = yrs[-1] if yrs else None
    return estimate, final


def resolve_release_year(
    *,
    source_legislation: str = "",
    quote: str = "",
    last_update: str = "",
    timeframe_column: str = "",
    provider=None,
) -> dict:
    """Resolve a fuzzy release year. See module docstring for the weighting."""
    candidates: dict[str, int] = {}
    if (y := _title_year(source_legislation, quote)) is not None:
        candidates["title"] = y
    if (y := _timeframe_year(last_update, timeframe_column)) is not None:
        candidates["timeframe"] = y
    if (y := _manifest_year(source_legislation)) is not None:
        candidates["manifest"] = y

    # LLM contributes its own estimate (the 'llm' vote) and the final decision.
    llm_estimate, llm_final = _llm_estimate_and_decide(
        provider, source_legislation, candidates, _tally(candidates)
    )
    if llm_estimate is not None:
        candidates["llm"] = llm_estimate

    tally = _tally(candidates)
    if not tally:
        return {
            "year": None, "confidence": 0.0, "decided_by": "none",
            "candidates": {}, "tally": {},
        }

    def _pref(year: int) -> int:
        for i, method in enumerate(PREFERENCE):
            if candidates.get(method) == year:
                return i
        return len(PREFERENCE)

    # Deterministic winner (fallback + when the model's final isn't a real signal).
    vote_winner = max(tally, key=lambda yr: (tally[yr], -_pref(yr)))
    decided_by = "weighted-vote"
    year = vote_winner
    if llm_final is not None:
        year, decided_by = llm_final, "llm"

    return {
        "year": year,
        "confidence": round(min(1.0, tally.get(year, 0.0)), 2),
        "decided_by": decided_by,
        "candidates": {m: y for m, y in candidates.items()},
        "tally": {str(k): round(v, 2) for k, v in tally.items()},
    }


def _tally(candidates: dict) -> dict:
    tally: dict[int, float] = {}
    for method, year in candidates.items():
        tally[year] = round(tally.get(year, 0.0) + WEIGHTS[method], 4)
    return tally
