#!/usr/bin/env python3
"""Run auditable Discovery checks against live official websites."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence
from urllib.parse import parse_qsl, urlsplit, urlunsplit


REPO_ROOT = Path(__file__).resolve().parents[1]
AI_SERVICE_ROOT = REPO_ROOT / "ai-service"
sys.path.insert(0, str(AI_SERVICE_ROOT))

from discovery.metadata import source_allows_url  # noqa: E402
from discovery.registry import get_sources  # noqa: E402
from discovery.schemas import DiscoverySearchRequest, LegalCandidate, LegalSourceConfig  # noqa: E402
from discovery.service import DiscoveryService  # noqa: E402
from discovery.smoke_cases import SMOKE_CASES, SmokeCase  # noqa: E402


SCHEMA_VERSION = 2
MIN_DOCUMENT_CHARS = 1000
REJECTED_PAGE_TERMS = (
    "error, block, or challenge page",
    "navigation-heavy",
    "captcha",
    "cloudflare",
    "page not found",
    "access denied",
)
SENSITIVE_KEYS = re.compile(
    r"(?:authorization|cookie|password|secret|api[_-]?key|token|signature|credential|^sig$)",
    re.IGNORECASE,
)
SENSITIVE_QUERY_KEYS = re.compile(
    r"(?:api[_-]?key|token|signature|credential|x-amz-|^sig$)",
    re.IGNORECASE,
)
URL_PATTERN = re.compile(r"https?://[^\s<>\"']+")
HEADER_PATTERN = re.compile(
    r"(?im)\b(authorization|proxy-authorization|cookie|set-cookie|x-api-key|"
    r"ocp-apim-subscription-key)\s*:\s*[^\r\n]+"
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--countries", nargs="+", default=[])
    parser.add_argument("--cases", nargs="+", default=[])
    parser.add_argument("--indicators", nargs="+", default=[])
    parser.add_argument("--browser-mode", choices=("auto", "playwright", "opencli"), default="auto")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--case-timeout", type=float, default=180.0)
    parser.add_argument("--registry-backend", choices=("file", "database"), default="file")
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "reports")
    parser.add_argument("--list-cases", action="store_true")
    return parser.parse_args(argv)


def _split_values(values: Iterable[str]) -> set[str]:
    return {item.strip() for value in values for item in value.split(",") if item.strip()}


def select_cases(args: argparse.Namespace) -> list[SmokeCase]:
    countries = {value.upper() for value in _split_values(args.countries)}
    case_ids = {value.casefold() for value in _split_values(args.cases)}
    indicators = _split_values(args.indicators)
    known_countries = {case.country for case in SMOKE_CASES}
    known_ids = {case.case_id.casefold() for case in SMOKE_CASES}
    unknown = sorted(countries - known_countries)
    unknown_ids = sorted(case_ids - known_ids)
    if unknown or unknown_ids:
        raise ValueError("Unknown smoke selection: " + ", ".join([*unknown, *unknown_ids]))
    selected = [
        case for case in SMOKE_CASES
        if (not countries or case.country in countries)
        and (not case_ids or case.case_id.casefold() in case_ids)
        and (not indicators or case.indicator in indicators)
    ]
    if not selected:
        raise ValueError("No smoke cases match the selected filters.")
    return selected


async def run_case(case: SmokeCase, args: argparse.Namespace) -> dict[str, Any]:
    started = time.perf_counter()
    request = DiscoverySearchRequest(
        country_code=case.country,
        pillars=[int(case.indicator.split(".", 1)[0])],
        indicators=[case.indicator],
        keywords=case.expected_title,
        source_mode="official_only",
        include_secondary_leads=False,
        browser_mode=args.browser_mode,
        limit=args.limit,
        strict_live=True,
    )
    try:
        response = await asyncio.wait_for(
            DiscoveryService().search(request), timeout=args.case_timeout
        )
    except Exception as exc:
        reason = (
            f"Discovery search timed out after {args.case_timeout:g} seconds."
            if isinstance(exc, asyncio.TimeoutError)
            else f"Discovery search failed: {exc.__class__.__name__}: {exc}"
        )
        return _failed_case(case, request, started, reason)

    duration_ms = int(response.diagnostics.get("duration_ms") or 0)
    if not duration_ms:
        duration_ms = round((time.perf_counter() - started) * 1000)
    sources = {source.name: source for source in get_sources(case.country)}
    candidates = [candidate_record(case, item, sources, duration_ms) for item in response.candidates]
    failures = case_failure_reasons(case, candidates)
    selected = next(
        (item for item in candidates if item["acceptance_passed"]),
        next((item for item in candidates if item["target_match"]), candidates[0] if candidates else None),
    )
    return {
        "case_id": case.case_id,
        "country": case.country,
        "expected_title": case.expected_title,
        "indicator": case.indicator,
        "request": _request_record(request),
        "duration_ms": duration_ms,
        "status": "passed" if not failures else "failed",
        "candidate_count": len(candidates),
        "target_found": any(item["target_match"] for item in candidates),
        "selected_candidate": selected,
        "candidates": candidates,
        "queries": list(response.queries),
        "diagnostics": _diagnostics_record(response.diagnostics),
        "failure_reasons": failures,
    }


def _failed_case(
    case: SmokeCase,
    request: DiscoverySearchRequest,
    started: float,
    reason: str,
) -> dict[str, Any]:
    return {
        "case_id": case.case_id,
        "country": case.country,
        "expected_title": case.expected_title,
        "indicator": case.indicator,
        "request": _request_record(request),
        "duration_ms": round((time.perf_counter() - started) * 1000),
        "status": "failed",
        "candidate_count": 0,
        "target_found": False,
        "selected_candidate": None,
        "candidates": [],
        "queries": [],
        "diagnostics": {},
        "failure_reasons": [reason],
    }


def _request_record(request: DiscoverySearchRequest) -> dict[str, Any]:
    return {
        "country_code": request.country_code,
        "pillars": request.pillars,
        "indicators": request.indicators,
        "keywords": request.keywords,
        "source_mode": request.source_mode,
        "browser_mode": request.browser_mode,
        "retrieval_mode": "strict_live" if request.strict_live else "auto",
        "limit": request.limit,
    }


def _diagnostics_record(diagnostics: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "raw_hits", "deduped_hits", "filtered_off_domain", "filtered_low_relevance",
        "duration_ms", "mode", "live_hits", "fixture_hits", "fallback_hits",
        "strict_rejected_non_live_hits", "live_discovery_success",
        "validation_attempted", "validation_verified", "validation_failed", "validation_weak",
    }
    record = {
        key: value for key, value in diagnostics.items()
        if key in allowed and isinstance(value, (str, int, float, bool, type(None)))
    }
    for key in ("retrieval_modes", "discovery_methods"):
        if isinstance(diagnostics.get(key), dict):
            record[key] = diagnostics[key]
    if isinstance(diagnostics.get("warnings"), list):
        record["warnings"] = [str(item)[:1000] for item in diagnostics["warnings"][:50]]
    return record


def candidate_record(
    case: SmokeCase,
    candidate: LegalCandidate,
    source_by_name: dict[str, LegalSourceConfig],
    duration_ms: int,
) -> dict[str, Any]:
    source = source_by_name.get(candidate.source_name)
    metadata = dict(candidate.validation_metadata or {})
    final_url = str(metadata.get("final_url") or candidate.url)
    warnings = list(dict.fromkeys([
        *candidate.warnings,
        *[str(item) for item in metadata.get("quality_warnings") or []],
    ]))
    target_match = _candidate_matches_target(case, candidate)
    official_domain_valid = bool(source and source_allows_url(source, candidate.url))
    final_url_official = bool(source and source_allows_url(source, final_url))
    origin = str(metadata.get("document_origin_domain") or "").casefold()
    origin_trusted = bool(
        source and origin in {domain.casefold() for domain in source.domains}
    ) or metadata.get("document_origin_trusted") is True
    http_status = _optional_int(metadata.get("http_status"))
    char_count = int(metadata.get("char_count") or 0)
    page_acceptable = all((
        metadata.get("quality_status") == "good",
        char_count >= MIN_DOCUMENT_CHARS,
        http_status is not None and 200 <= http_status < 400,
        metadata.get("tls_verified") is True,
        origin_trusted,
        final_url_official,
        not any(term in " ".join(warnings).casefold() for term in REJECTED_PAGE_TERMS),
    ))
    fallback_explained = candidate.retrieval_mode != "fallback" or bool(warnings)
    document_mode = str(metadata.get("document_retrieval_mode") or "")
    indicator_match = case.indicator in set(metadata.get("matched_indicators") or [])
    identity_match = metadata.get("document_identity_match") is True
    evidence_markers = {
        str(marker) for marker in metadata.get("evidence_markers") or []
    }
    required_evidence_markers = set(case.required_evidence_markers)
    missing_evidence_markers = sorted(required_evidence_markers - evidence_markers)
    evidence_markers_passed = not missing_evidence_markers
    accepted = all((
        target_match,
        candidate.discovery_method == "official_search",
        official_domain_valid,
        candidate.retrieval_mode == "live",
        document_mode == "live",
        candidate.validation_status == "verified",
        indicator_match,
        identity_match,
        evidence_markers_passed,
        page_acceptable,
        fallback_explained,
    ))
    return {
        "country": case.country,
        "indicator": case.indicator,
        "source_name": candidate.source_name,
        "adapter": candidate.source_adapter,
        "discovery_method": candidate.discovery_method,
        "title": candidate.title,
        "url": candidate.url,
        "final_url": final_url,
        "source_domain": candidate.source_domain,
        "retrieval_mode": candidate.retrieval_mode,
        "document_retrieval_mode": document_mode,
        "fetch_method": str(metadata.get("fetch_method") or ""),
        "http_status": http_status,
        "tls_verified": metadata.get("tls_verified") is True,
        "document_origin_domain": origin,
        "document_origin_trusted": origin_trusted,
        "document_identity_match": identity_match,
        "validation_status": candidate.validation_status,
        "quality_status": str(metadata.get("quality_status") or ""),
        "content_type": str(metadata.get("content_type") or ""),
        "char_count": char_count,
        "matched_indicators": list(metadata.get("matched_indicators") or []),
        # Reports persist stable marker ids only, never fetched legal text.
        "evidence_markers": sorted(evidence_markers),
        "required_evidence_markers": sorted(required_evidence_markers),
        "missing_evidence_markers": missing_evidence_markers,
        "evidence_markers_passed": evidence_markers_passed,
        "duration_ms": duration_ms,
        "warnings": warnings,
        "target_match": target_match,
        "official_domain_valid": official_domain_valid,
        "final_url_official": final_url_official,
        "page_acceptable": page_acceptable,
        "fallback_explained": fallback_explained,
        "acceptance_passed": accepted,
    }


def _candidate_matches_target(case: SmokeCase, candidate: LegalCandidate) -> bool:
    title = _normalize(f"{candidate.title}")
    if any(_normalize(alias) in title for alias in case.aliases):
        return True
    identity = _normalize(f"{candidate.external_id} {candidate.url}")
    return any(_normalize(item) in identity for item in case.expected_ids)


def _normalize(value: str) -> str:
    return re.sub(r"[^\w]+", " ", value.casefold()).strip()


def case_failure_reasons(case: SmokeCase, candidates: list[dict[str, Any]]) -> list[str]:
    if not candidates:
        return ["No candidate was returned."]
    targets = [item for item in candidates if item["target_match"]]
    if not targets:
        returned = "; ".join(item["title"] for item in candidates[:5])
        return [f"Expected law was not found. Returned: {returned}"]
    if any(item["acceptance_passed"] for item in targets):
        return []
    checks = (
        ("discovery_method", "official_search", "Expected law did not come from an official site search result."),
        ("retrieval_mode", "live", "Expected law was not retrieved live."),
        ("document_retrieval_mode", "live", "Expected-law text was not fetched live."),
        ("validation_status", "verified", "Expected law was not verified."),
        ("document_identity_match", True, "Fetched text did not contain the candidate law identity."),
        ("final_url_official", True, "Expected law redirected outside the configured official domains."),
        ("page_acceptable", True, "Expected-law page failed HTTP, TLS, quality, or redirect checks."),
    )
    reasons = [reason for key, expected, reason in checks if not any(item[key] == expected for item in targets)]
    if not any(case.indicator in item["matched_indicators"] for item in targets):
        reasons.append(f"Fetched text did not provide evidence for indicator {case.indicator}.")
    if case.required_evidence_markers and not any(
        item["evidence_markers_passed"] for item in targets
    ):
        missing = sorted({
            marker
            for item in targets
            for marker in item["missing_evidence_markers"]
        })
        reasons.append("Fetched text was missing required evidence markers: " + ", ".join(missing) + ".")
    return reasons or ["Expected law did not satisfy all smoke acceptance checks."]


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    candidates = [candidate for result in results for candidate in result["candidates"]]
    countries: dict[str, dict[str, int]] = defaultdict(lambda: {
        "queries": 0, "queries_with_candidates": 0, "passed": 0, "failed": 0, "duration_ms": 0,
    })
    failures = []
    for result in results:
        country = countries[result["country"]]
        country["queries"] += 1
        country["queries_with_candidates"] += bool(result["candidate_count"])
        country[result["status"]] += 1
        country["duration_ms"] += result["duration_ms"]
        if result["failure_reasons"]:
            failures.append({
                "case_id": result["case_id"], "country": result["country"],
                "indicator": result["indicator"], "reasons": result["failure_reasons"],
            })
    return {
        "total_queries": len(results),
        "queries_with_candidates": sum(bool(item["candidate_count"]) for item in results),
        "passed_queries": sum(item["status"] == "passed" for item in results),
        "failed_queries": sum(item["status"] == "failed" for item in results),
        "candidate_count": len(candidates),
        "candidate_retrieval_modes": dict(Counter(item["retrieval_mode"] for item in candidates)),
        "document_retrieval_modes": dict(Counter(item["document_retrieval_mode"] or "unknown" for item in candidates)),
        "validation_statuses": dict(Counter(item["validation_status"] for item in candidates)),
        "countries": dict(countries),
        "failures": failures,
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Discovery Live Smoke Report", "",
        f"Generated: `{report['generated_at']}`", "",
        f"Retrieval mode: **{report['configuration'].get('retrieval_mode', 'unknown')}**", "",
        f"Passed: **{summary['passed_queries']}/{summary['total_queries']}**", "",
        "| Country | Indicator | Expected law | Result | Candidate | Mode | Validation | Duration |",
        "|---|---|---|---|---|---|---|---:|",
    ]
    for case in report["cases"]:
        candidate = case["selected_candidate"] or {}
        lines.append(
            f"| {case['country']} | {case['indicator']} | {case['expected_title']} | "
            f"{case['status']} | {candidate.get('title', '—')} | "
            f"{candidate.get('retrieval_mode', '—')} | {candidate.get('validation_status', '—')} | "
            f"{case['duration_ms']} ms |"
        )
    lines.extend(["", "## Failures", ""])
    if not summary["failures"]:
        lines.append("None.")
    else:
        for failure in summary["failures"]:
            lines.append(f"- `{failure['case_id']}`: " + "; ".join(failure["reasons"]))
    return "\n".join(lines) + "\n"


def redact_sensitive(value: Any, key: str = "") -> Any:
    if SENSITIVE_KEYS.search(key):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {item_key: redact_sensitive(item, str(item_key)) for item_key, item in value.items()}
    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]
    if isinstance(value, str):
        text = HEADER_PATTERN.sub(lambda match: f"{match.group(1)}: [REDACTED]", value)
        return URL_PATTERN.sub(lambda match: _redact_url(match.group(0)), text)
    return value


def _redact_url(url: str) -> str:
    try:
        parsed = urlsplit(url)
        query = [
            (key, "[REDACTED]" if SENSITIVE_QUERY_KEYS.search(key) else value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        ]
        from urllib.parse import urlencode
        return urlunsplit((
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            urlencode(query, safe="[]"),
            parsed.fragment,
        ))
    except ValueError:
        return "[REDACTED_URL]"


def _optional_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


async def run(args: argparse.Namespace, cases: list[SmokeCase]) -> dict[str, Any]:
    os.environ["DISCOVERY_REGISTRY_BACKEND"] = args.registry_backend
    results = []
    for index, case in enumerate(cases, 1):
        print(f"[{index}/{len(cases)}] {case.country} {case.indicator} — {case.expected_title}")
        result = await run_case(case, args)
        results.append(result)
        print(json.dumps(redact_sensitive(result["selected_candidate"] or {
            "country": case.country,
            "indicator": case.indicator,
            "status": result["status"],
            "failure_reasons": result["failure_reasons"],
        }), ensure_ascii=False, indent=2))
    return redact_sensitive({
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "configuration": {
            "retrieval_mode": "strict_live",
            "browser_mode": args.browser_mode,
            "limit": args.limit,
            "case_timeout_seconds": args.case_timeout,
            "registry_backend": args.registry_backend,
        },
        "cases": results,
        "summary": summarize(results),
    })


def write_reports(report: dict[str, Any], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = output_dir / f"discovery-smoke-{stamp}.json"
    markdown_path = output_dir / f"discovery-smoke-{stamp}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    return json_path, markdown_path


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if not 1 <= args.limit <= 50 or args.case_timeout <= 0:
        raise SystemExit("--limit must be 1-50 and --case-timeout must be positive")
    try:
        cases = select_cases(args)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    if args.list_cases:
        for case in cases:
            print(case.case_id)
        return 0
    report = asyncio.run(run(args, cases))
    json_path, markdown_path = write_reports(report, args.output_dir)
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"JSON report: {json_path}")
    print(f"Markdown report: {markdown_path}")
    return 1 if report["summary"]["failed_queries"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
