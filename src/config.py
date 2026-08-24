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
# Artikkeli näkyy katsauksessa 7 päivää julkaisustaan (tai havaitsemisestaan,
# jos julkaisupäivää ei tiedetä). Tätä vanhemmat poistuvat näkyvistä.
REPORT_DAYS = int(os.environ.get("REPORT_DAYS", "7"))
# Analyysi-ikkuna on tarkoituksella katsausikkunaa LYHYEMPI: yli 5 pv vanhoja
# ei analysoida lainkaan, koska Gemini-kutsut kuuluvat tuoreille uutisille.
# Näkyvyyden pidentäminen ei siis lisää yhtään kutsua — 6-7 pv vanha juttu
# näkyy sillä arviolla, joka sille tehtiin tuoreena.
#
# ÄLÄ yhdistä näitä takaisin yhdeksi vakioksi. REPORT_DAYS ohjasi ennen myös
# analyysiä, joten näkyvyyden pidentäminen olisi samalla laajentanut
# analysoitavien joukkoa — juuri se kalleinta mitä tässä voi tehdä.
ANALYZE_DAYS = int(os.environ.get("ANALYZE_DAYS", "5"))
# Raakalista ("kaikki löydetyt") elää raporttinäkymää pidempään: se on
# varmistus sille, ettei suodatus ole pudottanut jotain olennaista, joten
# viikko antaa aikaa palata edellisen ajon satoon.
RAW_DAYS = int(os.environ.get("RAW_DAYS", "7"))
# Kannassa hasheja pidetään pidempään, jotta dedup toimii eivätkä vanhat
# uutiset palaa raporttiin uusina.
RETENTION_DAYS = int(os.environ.get("RETENTION_DAYS", "90"))

# --- Suomalainen media (oma välilehti) ---
# Media-välilehti käyttää TÄSMÄLLEEN samoja ikkunoita kuin muut välilehdet:
# LOOKBACK_DAYS keruussa, ANALYZE_DAYS analyysissä, REPORT_DAYS näkyvyydessä,
# RAW_DAYS raakalistassa. Erillisiä MEDIA_DAYS-/MEDIA_LOOKBACK_DAYS-vakioita ei
# ole, eikä niitä pidä palauttaa: ne tekivät storesta haarautuvan (CASE WHEN tab)
# ilman että kukaan hyötyi pidemmästä ikkunasta.
#
# Vakio on jäljellä vain siksi, että media tarvitsee oman promptin, oman
# dedup-avaimen (otsikko ilman lähdettä) ja oman saatetekstin raportissa.
MEDIA_TAB = "media"

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
