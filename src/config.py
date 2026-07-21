"""Keskitetty konfiguraatio: polut, ympäristömuuttujat, vakiot."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output"
LOG_DIR = BASE_DIR / "logs"
for _d in (DATA_DIR, OUTPUT_DIR, LOG_DIR):
    _d.mkdir(exist_ok=True)

DB_PATH = DATA_DIR / "monitor.db"
SOURCES_PATH = BASE_DIR / "sources.yaml"
REPORT_PATH = OUTPUT_DIR / "report.html"


def _load_dotenv() -> None:
    """Kevyt .env-lataus ilman riippuvuuksia."""
    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()

# --- Gemini ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-lite")

# --- Keruu ---
LOOKBACK_DAYS = int(os.environ.get("LOOKBACK_DAYS", "5"))   # 2 ajoa/vko -> 5 pv riittää, dedup hoitaa loput
MAX_PER_SOURCE = int(os.environ.get("MAX_PER_SOURCE", "15"))
FETCH_TIMEOUT = 15          # sekuntia / HTTP-pyyntö
MAX_WORKERS = 8             # rinnakkaisten hakujen määrä

# --- Analyysi (Gemini free tier: vain ~20 kutsua/vrk!) ---
# Iso erä minimoi kutsujen määrän: kutsut = artikkelit / BATCH_SIZE.
# Eräkoko ei vaikuta analyysin laatuun (sama prompti/skeema per artikkeli),
# vain siihen montako artikkelia kulkee yhdessä pyynnössä. gemini-2.5-flashin
# output-raja (~64k tokenia) riittää helposti 50 artikkelille.
BATCH_SIZE = 50
BATCH_PAUSE_S = 5
BATCH_RETRIES = 2           # yritystä per erä; epäonnistunut erä jää 'new'-tilaan -> uusi yritys seuraavassa ajossa

# --- Raportti ---
REPORT_DAYS = int(os.environ.get("REPORT_DAYS", "60"))      # kuinka vanhoja artikkeleita raportissa näytetään

# --- Sähköposti (valinnainen; jos SMTP_HOST puuttuu, ohitetaan) ---
SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
EMAIL_FROM = os.environ.get("EMAIL_FROM", SMTP_USER)
EMAIL_TO = [a.strip() for a in os.environ.get("EMAIL_TO", "").split(",") if a.strip()]

HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; GolfFederationMonitor/2.0; "
        "+https://golf.fi; media monitoring for Suomen Golfliitto)"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fi,en,sv,no,da,de,fr,es,nl,is,et,pl,it",
}

THEMES = ["juniorit", "naiset/tasa-arvo", "digitaalisuus/tekoäly", "vastuullisuus", "talous/rahoitus"]
CATEGORIES = [
    "tapahtumat", "naisten golf", "kestävä kehitys", "juniorityö", "kilpagolf",
    "golfpolitiikka", "innovaatiot", "seuratoiminta", "digitalisaatio",
    "sponsorointi", "jäsenmäärät", "muu",
]
