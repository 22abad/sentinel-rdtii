#!/usr/bin/env python3
"""Batch runner — every economy x pillar combination in one command.

Mirrors the judges' README template:

    python batch_run.py --economies Singapore Australia Malaysia --pillar 6 7

Each (economy, pillar-set) pair is one `main.py` run, so a failure in one
economy never aborts the rest; per-run exit codes are reported at the end.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="batch_run.py", description=__doc__)
    parser.add_argument("--economies", nargs="+", required=True,
                        help="e.g. Singapore Australia Malaysia")
    parser.add_argument("--pillar", nargs="+", default=["6", "7"],
                        help="pillar ids, e.g. 6 7 (default) or 'all'")
    parser.add_argument("--output-dir", default="outputs")
    parser.add_argument("--provider", default=None)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--from-corpus", action="store_true",
                        help="Round-2 reproducible path: map fetched official baseline corpus")
    parser.add_argument("--max-documents", type=int, default=None)
    args = parser.parse_args(argv)

    pillar_arg = ",".join(args.pillar) if args.pillar != ["all"] else "all"
    failures: list[tuple[str, int]] = []
    for economy in args.economies:
        cmd = [sys.executable, str(REPO_ROOT / "main.py"),
               "--economy", economy, "--pillar", pillar_arg,
               "--output-dir", args.output_dir]
        if args.provider:
            cmd += ["--provider", args.provider]
        if args.offline:
            cmd += ["--offline"]
        if args.from_corpus:
            cmd += ["--from-corpus"]
        if args.max_documents is not None:
            cmd += ["--max-documents", str(args.max_documents)]
        print(f"\n=== {economy} (pillar {pillar_arg}) ===")
        code = subprocess.call(cmd)
        if code != 0:
            failures.append((economy, code))

    print("\n=== batch summary ===")
    for economy in args.economies:
        status = next((f"FAILED (exit {c})" for e, c in failures if e == economy), "ok")
        print(f"  {economy}: {status}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
