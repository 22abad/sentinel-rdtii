"""Run-scoped, thread-safe telemetry for LLM benchmark calls.

Design attribution:
    The per-call -> run aggregate model is informed by OpenCode's session
    usage architecture (message usage plus session totals). This module is an
    independent Python implementation; no OpenCode source code is copied.

The collector deliberately stores operational metadata only. Prompts, model
responses, credentials, and legal-document text are never persisted here.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal


UsageSource = Literal["provider_response", "unavailable"]
CostBasis = Literal[
    "actual_tokens_x_pricing_snapshot",
    "local_api_cost",
    "unavailable",
]


def _timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def cache_note(usage: dict[str, Any]) -> str:
    """" (N% input from provider cache)" when a split was reported, else "".

    Silent when none was: a provider that reports nothing is unknown, not 0%,
    and a cost line implying otherwise is why our own figures ran high. Set
    ``<PROVIDER>_CACHE_HIT_USD_PER_MTOK`` to have the discount priced in too.

    The percentage is shown over its OWN denominator, not the run's
    ``input_tokens`` total, and names that denominator whenever the two differ.
    A run can mix a reporting provider with a silent one (failover, or a
    cross-model checker on Ollama) through the same collector, and dividing
    cached tokens by every provider's tokens would advertise a discount the run
    did not get.
    """
    hit = int(usage.get("cache_hit_tokens", 0) or 0)
    miss = int(usage.get("cache_miss_tokens", 0) or 0)
    accounted = hit + miss
    if accounted <= 0:
        return ""
    note = f" ({hit / accounted:.0%} input from provider cache"
    total_input = int(usage.get("input_tokens", 0) or 0)
    if total_input > accounted:
        note += f", of {accounted:,} accounted of {total_input:,} input tokens"
    return note + ")"


@dataclass(frozen=True)
class CallUsageRecord:
    """Immutable audit record for one provider request."""

    run_id: str
    call_id: str
    recorded_at: str
    operation: str
    provider: str
    model: str
    status: Literal["success", "failed"]
    latency_ms: int
    input_tokens: int | None = None
    output_tokens: int | None = None
    #: Vendor prefix-cache split of ``input_tokens``; None = not reported.
    cache_hit_tokens: int | None = None
    cache_miss_tokens: int | None = None
    usage_source: UsageSource = "unavailable"
    cost_usd: float | None = None
    cost_basis: CostBasis = "unavailable"
    pricing_date: str | None = None
    input_usd_per_million: float | None = None
    output_usd_per_million: float | None = None
    cache_hit_usd_per_million: float | None = None
    indicator_ids: tuple[str, ...] = ()
    error_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["indicator_ids"] = list(self.indicator_ids)
        return payload


@dataclass
class UsageCollector:
    """Collect provider calls for one pipeline or benchmark run."""

    run_id: str
    metadata: dict[str, Any] = field(default_factory=dict)
    started_at: str = field(default_factory=_timestamp)
    _records: list[CallUsageRecord] = field(default_factory=list, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _started_perf: float = field(default_factory=time.perf_counter, repr=False)
    _finished_perf: float | None = field(default=None, repr=False)
    _successful_calls: int = field(default=0, repr=False)
    _failed_calls: int = field(default=0, repr=False)
    _calls_with_unknown_usage: int = field(default=0, repr=False)
    _known_input_count: int = field(default=0, repr=False)
    _known_output_count: int = field(default=0, repr=False)
    _known_cost_count: int = field(default=0, repr=False)
    _known_input_tokens: int = field(default=0, repr=False)
    _known_output_tokens: int = field(default=0, repr=False)
    _known_cache_hit_tokens: int = field(default=0, repr=False)
    _known_cache_miss_tokens: int = field(default=0, repr=False)
    _calls_with_cache_accounting: int = field(default=0, repr=False)
    _known_cost_usd: float = field(default=0.0, repr=False)
    _latency_sum_ms: int = field(default=0, repr=False)
    _operations: dict[str, int] = field(default_factory=dict, repr=False)

    def finish(self) -> None:
        """Freeze wall-clock duration when the owning run completes."""
        with self._lock:
            if self._finished_perf is None:
                self._finished_perf = time.perf_counter()

    def record(
        self,
        *,
        operation: str,
        provider: str,
        model: str,
        latency_ms: int,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        cache_hit_tokens: int | None = None,
        cache_miss_tokens: int | None = None,
        cost_usd: float | None = None,
        cost_basis: CostBasis = "unavailable",
        pricing_date: str | None = None,
        input_usd_per_million: float | None = None,
        output_usd_per_million: float | None = None,
        cache_hit_usd_per_million: float | None = None,
        indicator_ids: tuple[str, ...] = (),
        status: Literal["success", "failed"] = "success",
        error_type: str | None = None,
    ) -> CallUsageRecord:
        usage_available = input_tokens is not None and output_tokens is not None
        record = CallUsageRecord(
            run_id=self.run_id,
            call_id=uuid.uuid4().hex,
            recorded_at=_timestamp(),
            operation=operation,
            provider=provider,
            model=model,
            status=status,
            latency_ms=max(0, int(latency_ms)),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_hit_tokens=cache_hit_tokens,
            cache_miss_tokens=cache_miss_tokens,
            usage_source="provider_response" if usage_available else "unavailable",
            cost_usd=cost_usd,
            cost_basis=cost_basis,
            pricing_date=pricing_date,
            input_usd_per_million=input_usd_per_million,
            output_usd_per_million=output_usd_per_million,
            cache_hit_usd_per_million=cache_hit_usd_per_million,
            indicator_ids=indicator_ids,
            error_type=error_type,
        )
        with self._lock:
            self._records.append(record)
            if record.status == "success":
                self._successful_calls += 1
            else:
                self._failed_calls += 1
            if record.usage_source == "unavailable":
                self._calls_with_unknown_usage += 1
            if record.input_tokens is not None:
                self._known_input_count += 1
                self._known_input_tokens += record.input_tokens
            if record.output_tokens is not None:
                self._known_output_count += 1
                self._known_output_tokens += record.output_tokens
            if record.cache_hit_tokens is not None or record.cache_miss_tokens is not None:
                self._calls_with_cache_accounting += 1
                self._known_cache_hit_tokens += record.cache_hit_tokens or 0
                self._known_cache_miss_tokens += record.cache_miss_tokens or 0
            if record.cost_usd is not None:
                self._known_cost_count += 1
                self._known_cost_usd += record.cost_usd
            self._latency_sum_ms += record.latency_ms
            self._operations[record.operation] = (
                self._operations.get(record.operation, 0) + 1
            )
        return record

    @property
    def records(self) -> tuple[CallUsageRecord, ...]:
        with self._lock:
            return tuple(self._records)

    def summary(self) -> dict[str, Any]:
        with self._lock:
            end = self._finished_perf or time.perf_counter()
            call_count = len(self._records)
            return {
                "llm_calls": call_count,
                "successful_calls": self._successful_calls,
                "failed_calls": self._failed_calls,
                "calls_with_unknown_usage": self._calls_with_unknown_usage,
                "input_tokens": (
                    self._known_input_tokens
                    if self._known_input_count == call_count
                    else None
                ),
                "output_tokens": (
                    self._known_output_tokens
                    if self._known_output_count == call_count
                    else None
                ),
                "known_input_tokens": self._known_input_tokens,
                "known_output_tokens": self._known_output_tokens,
                "calls_with_cache_accounting": self._calls_with_cache_accounting,
                "known_cache_hit_tokens": self._known_cache_hit_tokens,
                "known_cache_miss_tokens": self._known_cache_miss_tokens,
                # Share of billed input tokens the vendor served from its prefix
                # cache — reported ONLY when every call in the run accounted for
                # its cache split. None otherwise, which covers both "nobody
                # reported" and the trap: a run mixing a reporting provider with
                # a silent one (failover, or the cross-model checker on Ollama,
                # which share this collector). There the ratio over accounted
                # tokens reads ~96% while the true share of the run's input is
                # ~13%, and a single number cannot say so. Consumers that want
                # the partial picture have known_cache_* and
                # calls_with_cache_accounting to compute it explicitly.
                "cache_hit_rate": (
                    round(
                        self._known_cache_hit_tokens
                        / max(1, self._known_cache_hit_tokens + self._known_cache_miss_tokens),
                        4,
                    )
                    if self._calls_with_cache_accounting
                    and self._calls_with_cache_accounting == call_count
                    else None
                ),
                "cost_usd": (
                    round(self._known_cost_usd, 10)
                    if self._known_cost_count == call_count
                    else None
                ),
                "known_cost_usd": round(self._known_cost_usd, 10),
                "latency_sum_ms": self._latency_sum_ms,
                "wall_clock_ms": max(
                    0,
                    int((end - self._started_perf) * 1000),
                ),
                "operations": dict(sorted(self._operations.items())),
            }

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "generated_at": _timestamp(),
            "metadata": self.metadata,
            "summary": self.summary(),
            "calls": [record.to_dict() for record in self.records],
        }

    def render_markdown(self, report: dict[str, Any] | None = None) -> str:
        report = report or self.to_dict()
        summary = report["summary"]

        def display(value: Any, *, money: bool = False) -> str:
            if value is None:
                return "Unavailable"
            if money:
                return f"${value:.6f}"
            return f"{value:,}" if isinstance(value, int) else str(value)

        lines = [
            f"# LLM usage report: `{self.run_id}`",
            "",
            f"Generated: `{report['generated_at']}`",
            "",
        ]
        if report["metadata"].get("disclaimer"):
            lines.extend([f"> {report['metadata']['disclaimer']}", ""])
        if report["metadata"].get("mode"):
            lines.extend([f"Mode: `{report['metadata']['mode']}`", ""])
        lines.extend([
            "## Summary",
            "",
            "| Metric | Value |",
            "| --- | ---: |",
            f"| LLM calls | {summary['llm_calls']} |",
            f"| Successful calls | {summary['successful_calls']} |",
            f"| Failed calls | {summary['failed_calls']} |",
            f"| Calls with unavailable token usage | {summary['calls_with_unknown_usage']} |",
            f"| Input tokens | {display(summary['input_tokens'])} |",
            f"| Output tokens | {display(summary['output_tokens'])} |",
            f"| API cost | {display(summary['cost_usd'], money=True)} |",
            f"| Known API cost subtotal | {display(summary['known_cost_usd'], money=True)} |",
            f"| Sum of call latency | {summary['latency_sum_ms'] / 1000:.3f} s |",
            "",
            "## Calls",
            "",
            "| Operation | Provider / model | Status | Tokens (in/out) | Cost | Latency |",
            "| --- | --- | --- | ---: | ---: | ---: |",
        ])
        for record in self.records:
            tokens = (
                f"{record.input_tokens:,} / {record.output_tokens:,}"
                if record.input_tokens is not None and record.output_tokens is not None
                else "Unavailable"
            )
            cost = f"${record.cost_usd:.6f}" if record.cost_usd is not None else "Unavailable"
            lines.append(
                f"| `{record.operation}` | {record.provider} / `{record.model}` | "
                f"{record.status} | {tokens} | {cost} | {record.latency_ms / 1000:.3f} s |"
            )
        lines.extend([
            "",
            "> Cost is provider-reported or calculated from actual returned token usage and the recorded pricing snapshot. It may differ from the final invoice.",
            "",
        ])
        return "\n".join(lines)

    def write_json(self, output_path: str | Path) -> Path:
        """Explicitly export machine-readable evidence for a benchmark run."""
        self.finish()
        json_path = Path(output_path)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        report = self.to_dict()
        json_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return json_path

    def write_markdown(self, output_path: str | Path) -> Path:
        """Explicitly export a human-readable report; never called at runtime."""
        self.finish()
        markdown_path = Path(output_path)
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(self.render_markdown(), encoding="utf-8")
        return markdown_path
