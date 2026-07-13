"""CSV and JSON writers for the judge-validated submission contract.

CSV is written with a frozen column order and a UTF-8 BOM (``utf-8-sig``) so
Excel opens bilingual (e.g. Malay/Chinese) text correctly. JSON carries the
same rows plus extended metadata and a small run header.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from .schema import CSV_COLUMNS, SubmissionRow


def _timestamped_stem(economy: str, pillar: str, timestamp: str) -> str:
    """Build the ``<Economy>_P<pillar>_<timestamp>`` output file stem."""

    return f"{economy}_P{pillar}_{timestamp}"


def write_csv(rows: list[SubmissionRow], path: str | Path) -> Path:
    """Write rows to ``path`` as the 13-column CSV in the frozen order."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(CSV_COLUMNS))
        writer.writeheader()
        for row in rows:
            writer.writerow(row.csv_record())
    return path


def write_json(
    rows: list[SubmissionRow],
    path: str | Path,
    meta: dict | None = None,
) -> Path:
    """Write rows plus extended metadata and a run header to ``path``."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "meta": meta or {},
        "provisions": [row.json_record() for row in rows],
    }
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    return path


def write_outputs(
    rows: list[SubmissionRow],
    *,
    economy: str,
    pillar: str,
    timestamp: str,
    output_dir: str | Path = "outputs",
    formats: tuple[str, ...] = ("csv", "json"),
    meta: dict | None = None,
) -> dict[str, Path]:
    """Write the requested output formats and return the written paths.

    File names follow the README contract:
    ``outputs/<Economy>_P<pillar>_<timestamp>.{csv,json}``.
    """

    output_dir = Path(output_dir)
    stem = _timestamped_stem(economy, pillar, timestamp)
    written: dict[str, Path] = {}
    if "csv" in formats:
        written["csv"] = write_csv(rows, output_dir / f"{stem}.csv")
    if "json" in formats:
        written["json"] = write_json(rows, output_dir / f"{stem}.json", meta=meta)
    return written
