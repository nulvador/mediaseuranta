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
  publish_ok=1
  # Salaa raportti ennen julkaisua, jos REPORT_PASSWORD on asetettu .env:ssä
  set +e
  python -m src.encrypt output/report.html docs/index.html
  enc_rc=$?
  set -e
  if [ "$enc_rc" -eq 0 ]; then
    echo "🔒 Raportti salattu julkaisua varten"
  elif [ "$enc_rc" -eq 3 ]; then
    cp output/report.html docs/index.html   # salasanaa ei asetettu -> avoin julkaisu
  else
    echo "⚠️  Salaus epäonnistui — julkaisu OHITETAAN, ettei sisältö päädy verkkoon avoimena"
    publish_ok=0
  fi
  if [ "$publish_ok" = "1" ]; then
    git add docs/index.html
    if git commit -q -m "Päivitä raportti $(date +%Y-%m-%d)"; then
      git push -q origin main && echo "✅ Raportti julkaistu webiin" \
        || echo "⚠️  Julkaisu epäonnistui (git push) — raportti on silti output/-kansiossa"
    fi
  fi
fi

# Avaa raportti selaimeen (vain macOS, ohitetaan cron/launchd-ajossa jos ei näyttöä)
if [ -f output/report.html ] && [ -z "${NO_OPEN:-}" ]; then
  open output/report.html 2>/dev/null || true
fi
