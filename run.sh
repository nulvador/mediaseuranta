#!/bin/bash
# Golf Media Monitor v2 — ajoskripti
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
source .venv/bin/activate

pip install -q -r requirements.txt

python -m src.main "$@"

# Avaa raportti selaimeen (vain macOS, ohitetaan cron/launchd-ajossa jos ei näyttöä)
if [ -f output/report.html ] && [ -z "${NO_OPEN:-}" ]; then
  open output/report.html 2>/dev/null || true
fi
