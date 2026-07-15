#!/usr/bin/env bash
# Judge-reproducibility gate: reproduce the EXACT documented setup in a clean
# virtualenv (fresh `pip install -r requirements.txt`) and run the headline
# command. Catches "works on my machine" dependency gaps — e.g. a missing
# psycopg2 that once zeroed every extraction on a fresh install.
#
#   bash tools/check_reproducibility.sh
#
# Exit 0 only if the headline command writes output files with the lean deps.
# Requires DEEPSEEK_API_KEY in .env (or any configured provider).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

VENV="$(mktemp -d)/repro-venv"
OUT="$(mktemp -d)/repro-out"
echo "→ fresh venv: $VENV"

python3 -m venv "$VENV"
echo "→ pip install -r requirements.txt (lean judge path)…"
"$VENV/bin/pip" install --quiet -r requirements.txt

# shellcheck disable=SC1091
set -a; [ -f .env ] && source .env; set +a

echo "→ headline command: python main.py --economy Singapore --pillar 6 --offline"
set +e
"$VENV/bin/python" main.py --economy Singapore --pillar 6 --offline \
  --output-dir "$OUT" --format both >/tmp/repro_run.log 2>&1
code=$?
set -e

rows=$(ls "$OUT"/*.csv 2>/dev/null | head -1)
if [ "$code" -eq 0 ] && [ -n "$rows" ]; then
  n=$(($(wc -l < "$rows") - 1))
  echo "✅ REPRODUCIBLE — fresh install wrote $n provisions to $(basename "$rows")"
  rm -rf "$(dirname "$VENV")" "$(dirname "$OUT")"
  exit 0
else
  echo "❌ NOT REPRODUCIBLE — exit=$code, no/empty output. Tail of run log:"
  grep -viE 'Playwright|Wayback|Skipping' /tmp/repro_run.log | tail -15
  echo "(fresh venv kept at $VENV for debugging)"
  exit 1
fi
