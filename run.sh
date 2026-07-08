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

# Julkaise raportti GitHub Pagesiin, jos julkaisu on kytketty (docs/-kansio + git remote)
if [ -d docs ] && git remote get-url origin >/dev/null 2>&1 && [ -f output/report.html ]; then
  cp output/report.html docs/index.html
  git add docs/index.html
  if git commit -q -m "Päivitä raportti $(date +%Y-%m-%d)"; then
    git push -q origin main && echo "✅ Raportti julkaistu webiin" \
      || echo "⚠️  Julkaisu epäonnistui (git push) — raportti on silti output/-kansiossa"
  fi
fi

# Avaa raportti selaimeen (vain macOS, ohitetaan cron/launchd-ajossa jos ei näyttöä)
if [ -f output/report.html ] && [ -z "${NO_OPEN:-}" ]; then
  open output/report.html 2>/dev/null || true
fi
