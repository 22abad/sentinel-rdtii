"""LLMProvider abstract base.

This abstraction is the cornerstone of the "swappable to open-weight" requirement.
Every provider exposes the same interface; main.py never imports a concrete provider.
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from telemetry import CostBasis, UsageCollector


_USAGE_CONTEXT: ContextVar[tuple[str, tuple[str, ...]] | None] = ContextVar(
    "rdtii_usage_context",
    default=None,
)
_USAGE_COLLECTOR: ContextVar[UsageCollector | None] = ContextVar(
    "rdtii_usage_collector",
    default=None,
)


@dataclass
class ExtractionUsage:
    """Token / cost telemetry for one extract_features call."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
    latency_ms: int = 0
    raw_response: str = field(default="", repr=False)


class ExtractionError(Exception):
    """Raised when the provider fails or returns unparseable output."""


class LLMProvider(ABC):
    """Abstract LLM provider for RDTII feature extraction.

    Contract:
        - The provider receives an article (chunk) and a feature spec
          (which features the deterministic scorer needs).
        - It returns a flat dict whose keys match feature_spec, plus a
          mandatory `verbatim_quote` string and 0+ optional metadata keys
          (`source_legislation`, `last_update`, `scope`, `impact`).
        - The provider MUST NOT compute or return a score. Scoring is
          owned by the deterministic Python layer.
        - The provider MUST NOT paraphrase the verbatim_quote. The
          downstream verifier rejects mappings whose quote is not a
          substring of the source.
    """

    name: str = "base"
    last_usage: ExtractionUsage | None = None
    usage_collector: UsageCollector | None = None

    def set_usage_collector(self, collector: UsageCollector | None) -> None:
        """Attach a fallback collector (primarily for direct provider tests)."""
        self.usage_collector = collector

    @contextmanager
    def usage_collection(self, collector: UsageCollector):
        """Bind telemetry to the current async/thread context for one run."""
        token = _USAGE_COLLECTOR.set(collector)
        try:
            yield
        finally:
            _USAGE_COLLECTOR.reset(token)

    @contextmanager
    def usage_operation(
        self,
        operation: str,
        indicator_ids: tuple[str, ...] = (),
    ):
        """Label nested provider calls without changing the public API."""
        token = _USAGE_CONTEXT.set((operation, indicator_ids))
        try:
            yield
        finally:
            _USAGE_CONTEXT.reset(token)

    @staticmethod
    def _usage_context(
        default_operation: str,
        default_indicator_ids: tuple[str, ...] = (),
    ) -> tuple[str, tuple[str, ...]]:
        return _USAGE_CONTEXT.get() or (default_operation, default_indicator_ids)

    def _record_usage(
        self,
        operation: str,
        usage: ExtractionUsage,
        *,
        indicator_ids: tuple[str, ...] = (),
        status: Literal["success", "failed"] = "success",
        error: Exception | None = None,
        cost_basis: CostBasis = "unavailable",
        pricing_date: str | None = None,
        input_usd_per_million: float | None = None,
        output_usd_per_million: float | None = None,
    ) -> None:
        """Finalize backward-compatible usage and append a run audit event."""
        self.last_usage = usage
        collector = _USAGE_COLLECTOR.get() or getattr(self, "usage_collector", None)
        if collector is None:
            return
        collector.record(
            operation=operation,
            provider=getattr(type(self), "name", self.__class__.__name__),
            model=getattr(self, "model_name", getattr(self, "name", "unknown")),
            latency_ms=usage.latency_ms,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cost_usd=usage.cost_usd,
            cost_basis=cost_basis,
            pricing_date=pricing_date,
            input_usd_per_million=input_usd_per_million,
            output_usd_per_million=output_usd_per_million,
            indicator_ids=indicator_ids,
            status=status,
            error_type=type(error).__name__ if error is not None else None,
        )

    @abstractmethod
    def query(self, prompt: str, system: str = "") -> str:
        """Free-form text completion — used by the RAG query endpoint.

        Args:
            prompt: The user's full prompt (question + context).
            system: Optional system instruction override.

        Returns:
            Raw text response from the LLM.

        Raises:
            ExtractionError on failure.
        """
        ...

    @abstractmethod
    def extract_features(
        self,
        article_text: str,
        indicator_id: str,
        feature_spec: dict[str, dict[str, str]],
    ) -> dict[str, Any]:
        """Extract features for a given (article, indicator) pair.

        Args:
            article_text: The legal text chunk (one article / clause).
            indicator_id: e.g. "6.1", "7.3".
            feature_spec: Mapping from feature_name -> {"type": "bool|int|str", "description": "..."}.

        Returns:
            dict with keys:
                - all keys from feature_spec
                - "verbatim_quote": str (mandatory)
                - optional: "source_legislation", "last_update", "scope", "impact"

        Raises:
            ExtractionError on failure (parsing, network, etc.).
        """
        ...

    def extract_batch(
        self,
        chunk_text: str,
        indicators: list[tuple[str, dict[str, dict[str, str]]]],
    ) -> dict[str, dict[str, Any]]:
        """Default batch extraction — loops over extract_features.

        Concrete providers that support true batching (single LLM call per
        chunk) should override this for performance. The default keeps the
        old per-indicator calling convention working for all providers.
        """
        result: dict[str, dict[str, Any]] = {}
        for indicator_id, feature_spec in indicators:
            result[indicator_id] = self.extract_features(
                chunk_text, indicator_id, feature_spec,
            )
        return result

    def repair_extraction(
        self,
        article_text: str,
        indicator_id: str,
        feature_spec: dict[str, dict[str, str]],
        previous_output: dict[str, Any],
        validation_errors: list[str],
    ) -> dict[str, Any]:
        """Repair an extraction that failed deterministic validation.

        The repair step is deliberately narrow: it may revise evidence,
        feature values, and source metadata only. Scoring remains owned by
        deterministic Python after the repaired JSON returns.
        """
        prompt = self.build_repair_prompt(
            article_text=article_text,
            indicator_id=indicator_id,
            feature_spec=feature_spec,
            previous_output=previous_output,
            validation_errors=validation_errors,
        )
        with self.usage_operation("repair", (indicator_id,)):
            raw = self.query(
                prompt,
                system="Output ONLY valid JSON. No prose, no markdown fences.",
            )
        return self.parse_json_response(raw)

    def estimate_cost_usd(self, input_tokens: int, output_tokens: int) -> float:
        """Subclasses should override with provider-specific pricing."""
        return 0.0

    # ── Shared helpers (used by concrete providers) ──────────────────

    @staticmethod
    def _get_recent_corrections() -> str:
        """Fetch the latest 5 rejected extractions with reviewer notes to use as negative few-shot examples.

        Optional prompt enhancement backed by Postgres. The judge CLI is DB-free
        and its lean install ships no psycopg2, so BOTH the driver import and the
        connection must degrade to "no corrections" instead of breaking
        extraction. The import lives inside the try for that reason — a
        ModuleNotFoundError here previously zeroed every batch on a fresh install.
        """
        import os

        conn = None
        try:
            import psycopg2

            db_config = {
                "dbname": os.getenv("POSTGRES_DB", "rdtii"),
                "user": os.getenv("POSTGRES_USER", "rdtii_user"),
                "password": os.getenv("POSTGRES_PASSWORD", "rdtii_password"),
                "host": os.getenv("POSTGRES_HOST", "postgres"),
                "port": os.getenv("POSTGRES_PORT", "5432"),
            }
            conn = psycopg2.connect(**db_config)
            cur = conn.cursor()
            cur.execute(
                "SELECT ds.raw_text, rm.compliance_status, at.reviewer_notes "
                "FROM audit_trail at "
                "JOIN regulation_mappings rm ON at.mapping_id = rm.id "
                "JOIN document_sections ds ON at.source_section_id = ds.id "
                "WHERE at.reviewer_notes IS NOT NULL AND at.reviewer_notes != '' AND rm.compliance_status = 'non-compliant' "
                "ORDER BY at.created_at DESC LIMIT 5"
            )
            rows = cur.fetchall()
            cur.close()
            conn.close()
            if not rows:
                return ""
                
            parts = ["\n=== IMPORTANT: RECENT HUMAN AUDITOR CORRECTIONS (DO NOT MAKE THESE ERRORS) ==="]
            for i, (text, status, notes) in enumerate(rows, 1):
                text_preview = text.strip().replace("\n", " ")[:200]
                parts.append(
                    f"Correction {i}:\n"
                    f"  - Extracted Text: \"{text_preview}...\"\n"
                    f"  - Human Feedback: \"{notes}\"\n"
                    f"  - Action required: Do NOT extract or map this type of content as valid policy."
                )
            return "\n".join(parts) + "\n=================================================================\n"
        except Exception:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
            return ""

    @staticmethod
    def build_prompt(
        article_text: str,
        indicator_id: str,
        feature_spec: dict[str, dict[str, str]],
    ) -> str:
        """Construct a uniform extraction prompt across all providers.

        Keeping this in the base class means provider comparisons (Gemini vs
        Llama 3 etc.) are testing the model, not the prompt.
        """
        feature_lines = []
        for fname, fmeta in feature_spec.items():
            ftype = fmeta.get("type", "bool")
            fdesc = fmeta.get("description", "")
            feature_lines.append(f'  - "{fname}" ({ftype}): {fdesc}')
        feature_block = "\n".join(feature_lines) if feature_lines else "  (none)"

        schema_keys = list(feature_spec.keys()) + [
            "verbatim_quote",
            "article_clause",
            "source_legislation",
            "last_update",
            "scope",
            "coverage",
            "cluster",
            "name",
            "policy_description",
        ]
        schema_lines = ",\n".join(f'  "{k}": ...' for k in schema_keys)

        return f"""You are a UN ESCAP digital trade policy analyst extracting structured
data from legal text for the RDTII 2.1 framework.

You are evaluating ONE specific indicator: {indicator_id}.
You MUST extract the following features by reading the article below:

{feature_block}

ABSOLUTE RULES:
- Output ONLY valid JSON. No prose, no markdown fences, no explanations.
- "verbatim_quote" MUST be an EXACT substring of the input text.
  - FOR NON-ENGLISH TEXTS: Copy the text character-for-character including all spaces and special characters. DO NOT attempt to normalize or reformat.
- "article_clause" MUST be the specific article, clause, or section number (e.g. "Article 18", "Section 5(2)", "Paragraph 10"). Output an empty string if not explicitly mentioned in the text.
- "source_legislation" MUST be the official title of the law/regulation, EXCLUDING any article, section, or clause numbers. Format it exactly as: [Country/Economy Name] [Law Name] ([Optional Abbreviation]), [Year], [Law Number] (e.g., "Singapore Personal Data Protection Act (PDPA), 2012, No. 26", "Malaysia Personal Data Protection Act (PDPA), 2010, No. 709").
- If a feature cannot be determined from the text, set it to its type's default (false / 0 / "").
- "scope" MUST be one of: "horizontal" / "sectoral" / "unknown".
- "coverage": detailed description of the measure's coverage (e.g. 'ICT products', 'Telecommunication equipments', 'Cross-cutting').
- "cluster": high-level policy cluster — one of "Traditional trade policies", "Digital governance policies", or "Other domestic policies".
- "name": mid-level policy category (e.g. "Tariffs & trade defence", "Non-technical NTMs", "Standards & procedures", "Online sales & transactions", "Public procurement", "Foreign direct investment", "Intellectual property rights").
- "policy_description": most specific policy type (e.g. "Trade defence measures", "Import bans", "Local content requirements", "Self-certification limitations").
- Do NOT include a score or any RDTII pillar/indicator number — only features.

JSON schema (all keys required):
{{
{schema_lines}
}}

{LLMProvider._get_recent_corrections()}

Input article:
\"\"\"
{article_text}
\"\"\"
"""

    @staticmethod
    def build_batch_prompt(
        article_text: str,
        indicators: list[tuple[str, dict[str, dict[str, str]]]],
    ) -> str:
        """Construct a batch prompt extracting ALL indicators in one LLM call."""
        parts: list[str] = []
        schema_parts: list[str] = []
        for indicator_id, feature_spec in indicators:
            parts.append(f"\nIndicator {indicator_id}:")
            for fname, fmeta in feature_spec.items():
                parts.append(f'  - "{fname}" ({fmeta.get("type", "bool")}): {fmeta.get("description", "")}')

            fnames = list(feature_spec.keys())
            fields = [f'    "verbatim_quote": "exact substring",']
            fields.append('    "article_clause": "specific article, clause, or section number (e.g. Article 18), or empty string",')
            for fname in fnames:
                fields.append(f'    "{fname}": ...,')
            fields.append('    "source_legislation": "official title of the law/regulation EXCLUDING article/clause numbers, formatted exactly as: [Country/Economy] [Law Name] ([Abbreviation]), [Year], [Law Number] (e.g. Singapore Personal Data Protection Act (PDPA), 2012, No. 26)",')
            fields.append('    "scope": "horizontal|sectoral|unknown",')
            fields.append('    "coverage": "detailed coverage description (e.g. ICT products)",')
            fields.append('    "cluster": "Traditional trade policies|Digital governance policies|Other domestic policies",')
            fields.append('    "name": "mid-level policy category (e.g. Tariffs & trade defence)",')
            fields.append('    "policy_description": "specific policy type (e.g. Trade defence measures)"')
            schema_parts.append(f'  "{indicator_id}": {{')
            schema_parts.extend(fields)
            schema_parts.append('  }')

        return f"""You are a UN ESCAP digital trade policy analyst extracting structured
data from legal text for the RDTII 2.1 framework.

Evaluate ALL of these indicators from the same article below:

{chr(10).join(parts)}

ABSOLUTE RULES:
- Output ONLY valid JSON. No prose, no markdown fences, no explanations.
- Each indicator MUST have a "verbatim_quote" that is an EXACT substring of the input — do NOT paraphrase.
- "article_clause" MUST be the specific article, clause, or section number (e.g. "Article 18", "Section 5(2)", "Paragraph 10"). Output an empty string if not explicitly mentioned in the text.
- "source_legislation" MUST be the official title of the law/regulation, EXCLUDING any article, section, or clause numbers. Format it exactly as: [Country/Economy Name] [Law Name] ([Optional Abbreviation]), [Year], [Law Number] (e.g., "Singapore Personal Data Protection Act (PDPA), 2012, No. 26", "Malaysia Personal Data Protection Act (PDPA), 2010, No. 709").
- If a feature cannot be determined, set to its type default (false / 0 / "").
- "scope" MUST be one of: "horizontal" / "sectoral" / "unknown".
- "coverage": detailed coverage description.
- "cluster": high-level policy cluster — "Traditional trade policies", "Digital governance policies", or "Other domestic policies".
- "name": mid-level policy category.
- "policy_description": specific policy type.
- Do NOT include scores — only features.

Return JSON:
{{
{chr(10).join(schema_parts)}
}}

{LLMProvider._get_recent_corrections()}

Input article:
\"\"\"
{article_text}
\"\"\"
"""

    @staticmethod
    def build_repair_prompt(
        article_text: str,
        indicator_id: str,
        feature_spec: dict[str, dict[str, str]],
        previous_output: dict[str, Any],
        validation_errors: list[str],
    ) -> str:
        """Construct a bounded prompt for repairing failed extraction JSON."""
        feature_lines = []
        for fname, fmeta in feature_spec.items():
            feature_lines.append(
                f'  - "{fname}" ({fmeta.get("type", "bool")}): {fmeta.get("description", "")}'
            )
        feature_block = "\n".join(feature_lines) if feature_lines else "  (none)"

        schema_keys = list(feature_spec.keys()) + [
            "verbatim_quote",
            "article_clause",
            "source_legislation",
            "last_update",
            "scope",
            "coverage",
            "cluster",
            "name",
            "policy_description",
        ]
        schema_lines = ",\n".join(f'  "{k}": ...' for k in schema_keys)
        previous_json = json.dumps(previous_output, ensure_ascii=False, indent=2, default=str)
        errors = "\n".join(f"- {err}" for err in validation_errors) or "- Unknown validation failure"

        return f"""You are repairing a failed RDTII 2.1 extraction for ONE indicator: {indicator_id}.

The previous JSON failed deterministic validation:
{errors}

Allowed feature fields:
{feature_block}

Repair rules:
- Output ONLY valid JSON. No prose, no markdown fences, no explanations.
- Do NOT include a score, pillar, or indicator field.
- "verbatim_quote" MUST be an exact substring of the input article.
- If no valid substantive evidence for this indicator exists in the article, set "verbatim_quote" to "" and set feature values to their type defaults.
- Correct only evidence, feature values, and source metadata.
- Use only keys in this schema:
{{
{schema_lines}
}}

Previous JSON:
{previous_json}

Input article:
\"\"\"
{article_text}
\"\"\"
"""

    @staticmethod
    def parse_json_response(raw_text: str) -> dict[str, Any]:
        """Robustly extract a JSON object from an LLM response.

        Handles:
            - Bare JSON / code fences / leading prose
            - Truncated JSON (max_tokens) — closes braces
            - Missing commas between key-value pairs
            - Trailing commas
        """
        if not raw_text:
            raise ExtractionError("Empty response from LLM")

        stripped = raw_text.strip()
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
        stripped = re.sub(r"\s*```\s*$", "", stripped)

        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1:
            raise ExtractionError(f"No JSON object found in: {raw_text[:200]}")

        def _last_comma_outside_string(value: str) -> int:
            """Return the last comma not enclosed in a JSON string."""
            in_string = False
            escaped = False
            last = -1
            for i, ch in enumerate(value):
                if escaped:
                    escaped = False
                    continue
                if ch == "\\":
                    escaped = True
                    continue
                if ch == '"':
                    in_string = not in_string
                    continue
                if ch == "," and not in_string:
                    last = i
            return last

        if end >= start:
            json_candidate = stripped[start : end + 1]
        else:
            json_candidate = stripped[start:]

        # Attempt 1: parse as-is
        try:
            return json.loads(json_candidate)
        except json.JSONDecodeError:
            pass

        # Attempt 2: common LLM JSON repairs
        repairs = [
            # Remove trailing commas before } or ]
            (r",\s*(\}|\])", r"\1"),
            # Insert missing commas: value followed by new key
            (r'(true|false|null|\d+|"[^"]*"|\}|\])\s+"', r'\1, "'),
            # Fix bare-word values that should be quoted (LLM shorthand)
            (r':\s+(true|false|null|"[^"]*")(\s*[,\}])', r': \1\2'),
        ]
        for pattern, replacement in repairs:
            repaired = re.sub(pattern, replacement, json_candidate)
            try:
                return json.loads(repaired)
            except json.JSONDecodeError:
                continue

        # Attempt 3: truncation repair — strip incomplete tail, close braces
        try:
            body = json_candidate
            last_comma = _last_comma_outside_string(body)
            if last_comma > 0:
                prefix = body[:last_comma]
            else:
                prefix = body
            depth = prefix.count("{") - prefix.count("}")
            if depth > 0:
                prefix += "}" * depth
            s = prefix.find("{")
            e = prefix.rfind("}")
            if s != -1 and e > s:
                return json.loads(prefix[s : e + 1])
        except json.JSONDecodeError:
            pass

        # Attempt 4: last resort — extract each indicator object individually
        try:
            result: dict[str, Any] = {}
            # Match top-level keys like "6.1" with their object values
            blocks = re.findall(
                r'"(\d+\.\d+)"\s*:\s*'
                r'(\{(?:[^{}]|\{[^{}]*\})*\})',
                json_candidate,
            )
            for key, block in blocks:
                try:
                    result[key] = json.loads(block)
                except json.JSONDecodeError:
                    continue
            if result:
                return result
        except Exception:
            pass

        raise ExtractionError(f"Unrepairable JSON: {raw_text[:300]}")
