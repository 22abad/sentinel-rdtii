#!/usr/bin/env python3
"""Apply the legal reviewer's exported verdicts back into the project.

Katie's three review pages (outputs/katie-session/) each export a JSON file.
This tool closes the loop so her decisions actually change the system instead
of sitting in a download folder:

    python tools/apply_katie_verdicts.py katie-*.json            # dry-run (plan)
    python tools/apply_katie_verdicts.py katie-*.json --apply    # write changes

What each batch does:

- **Banked NEW-law indicator review** (page #1): a confirmed card whose
  indicator set differs from the library's `indicator_hints` updates the
  manifest entry (hints + a review note). A flagged card appends her note to
  the entry. Nothing is ever deleted automatically.
- **Live-discovery adjudication** (page #3): `valid` / `reassign` verdicts are
  printed as ready-to-run `promote_new_law.py --verify --article ...` commands
  (banking stays a human action); `reject` / `unsure` are recorded.
- **THA + TLS review** (page #2): decisions are recorded.

Every decision from every batch is appended to the audit ledger
`docs/legal-review-ledger.jsonl` (with reviewer, batch, and date), so "who
decided what, when" survives long after the browser's localStorage is gone.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
AI_SERVICE = REPO_ROOT / "ai-service"
if str(AI_SERVICE) not in sys.path:
    sys.path.insert(0, str(AI_SERVICE))

MANIFEST = REPO_ROOT / "data" / "law_library" / "manifest.jsonl"
LEDGER = REPO_ROOT / "docs" / "legal-review-ledger.jsonl"


def _norm(name: str) -> str:
    try:
        from submission.novelty import normalize_law_name

        return normalize_law_name(name or "")
    except Exception:  # noqa: BLE001
        return " ".join((name or "").lower().split())


def _rdtii_to_hint(code: str) -> str:
    """'P7-I4' -> '7.4' (manifest hints use dotted form)."""
    code = (code or "").strip().upper()
    if code.startswith("P") and "-I" in code:
        p, i = code[1:].split("-I", 1)
        return f"{p}.{i}"
    return code


def load_manifest() -> list[dict]:
    return [json.loads(l) for l in MANIFEST.read_text(encoding="utf-8").splitlines() if l.strip()]


def save_manifest(rows: list[dict]) -> None:
    MANIFEST.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
                        encoding="utf-8")


def detect_batch(doc: dict) -> str:
    batch = str(doc.get("batch", ""))
    if batch:
        return batch
    d = (doc.get("decisions") or [{}])[0]
    if "katie_indicators" in d and "our_hint" in d:
        return "banked-indicator-review"
    return "unknown"


def apply_banked_review(doc: dict, manifest: list[dict], apply: bool) -> list[str]:
    """Page #1: update indicator hints / notes on banked library entries."""
    actions: list[str] = []
    by_norm = {_norm(r["law_name"]): r for r in manifest}
    today = date.today().isoformat()
    for d in doc.get("decisions", []):
        verdict = d.get("verdict")
        if verdict in (None, "(not reviewed)"):
            continue
        entry = by_norm.get(_norm(d.get("law_name", "")))
        if entry is None:
            actions.append(f"SKIP (no library entry): {d.get('law_name','')[:60]}")
            continue
        note = (d.get("note") or "").strip()
        if verdict == "ok":
            new_hints = sorted({_rdtii_to_hint(c) for c in (d.get("katie_indicators") or []) if c})
            old_hints = sorted(entry.get("indicator_hints", []))
            if new_hints and new_hints != old_hints:
                actions.append(f"HINTS  {entry['law_id']}: {old_hints} -> {new_hints}")
                if apply:
                    entry["indicator_hints"] = new_hints
                    entry["notes"] = (entry.get("notes", "") +
                                      f" Indicator hints set per legal review {today}.").strip()
            else:
                actions.append(f"CONFIRM {entry['law_id']} (hints unchanged)")
            if apply and note:
                entry["notes"] = (entry.get("notes", "") + f" Legal review: {note}").strip()
        elif verdict == "flag":
            actions.append(f"FLAG   {entry['law_id']}: {note or '(no note)'}")
            if apply:
                entry["notes"] = (entry.get("notes", "") +
                                  f" FLAGGED by legal review {today}: {note or 'see reviewer'}.").strip()
    return actions


def report_adjudication(doc: dict) -> list[str]:
    """Page #3: print promote commands for accepted live finds; record the rest."""
    lines: list[str] = []
    for d in doc.get("decisions", []):
        v = d.get("verdict")
        if v in ("valid", "reassign"):
            inds = ([_rdtii_to_hint(c) for c in (d.get("correct_indicators") or [])]
                    if v == "reassign" else [_rdtii_to_hint(d.get("indicator", ""))])
            inds = [i for i in inds if i]
            pillars = sorted({i.split(".")[0] for i in inds}) or ["?"]
            lines.append(
                "ACCEPTED"
                + (" (reassigned)" if v == "reassign" else "")
                + f": {d.get('law_name','')[:60]}\n"
                f"    python tools/promote_new_law.py --economy SGP "
                f"--law-name \"{d.get('law_name','')}\" --url \"{d.get('url','')}\" "
                f"--pillars {','.join(pillars)} --indicators {','.join(inds) or '?'} "
                f"--article \"{d.get('article','')}\" --text-file <verbatim.txt> --verify"
            )
        elif v == "reject":
            lines.append(f"REJECTED: {d.get('law_name','')[:60]} — {d.get('note') or 'not indicator evidence'}")
        elif v == "unsure":
            lines.append(f"UNSURE:   {d.get('law_name','')[:60]} — needs discussion")
    return lines


def append_ledger(doc: dict, source: str, apply: bool) -> int:
    entries = []
    for d in doc.get("decisions", []):
        entries.append({
            "reviewer": doc.get("reviewer", "unknown"),
            "batch": detect_batch(doc),
            "source_file": source,
            "recorded_at": date.today().isoformat(),
            "decision": d,
        })
    if apply and entries:
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        with LEDGER.open("a", encoding="utf-8") as fh:
            for e in entries:
                fh.write(json.dumps(e, ensure_ascii=False) + "\n")
    return len(entries)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", help="Katie's exported JSON file(s)")
    ap.add_argument("--apply", action="store_true",
                    help="Write manifest updates + ledger entries (default: dry-run plan)")
    args = ap.parse_args(argv)

    manifest = load_manifest()
    changed = False
    for f in args.files:
        doc = json.loads(Path(f).read_text(encoding="utf-8"))
        batch = detect_batch(doc)
        print(f"\n=== {f}  (batch: {batch}, reviewer: {doc.get('reviewer','?')}) ===")
        if batch == "banked-indicator-review":
            for a in apply_banked_review(doc, manifest, args.apply):
                print("  " + a)
            changed = True
        elif batch == "live-discovery-adjudication":
            for line in report_adjudication(doc):
                print("  " + line)
        else:
            print(f"  ({len(doc.get('decisions', []))} decision(s) recorded to the ledger)")
        n = append_ledger(doc, Path(f).name, args.apply)
        print(f"  ledger: {n} decision(s){' appended' if args.apply else ' would be appended (dry-run)'}")

    if args.apply and changed:
        save_manifest(manifest)
        print(f"\n✅ manifest updated: {MANIFEST.relative_to(REPO_ROOT)}")
    elif not args.apply:
        print("\n(dry-run — re-run with --apply to write)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
