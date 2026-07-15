"""Gemini-analyysi: relevanssi, käännös, kategoria, prioriteetti, teemat.

Keskeiset erot v1:een:
- Pienet erät (12 kpl) -> vastaukset eivät katkea
- Structured output (response_schema) -> ei enää JSON-parsintaongelmia
- Malli palauttaa vain uudet kentät + rivinumeron -> vähemmän tokeneita,
  alkuperäinen data ei voi korruptoitua käännöksen mukana
- Checkpoint: jokainen erä tallennetaan heti (save_cb) -> keskeytys ei hukkaa työtä
- Epäonnistunut erä jää 'new'-tilaan ja yritetään uudelleen seuraavassa ajossa
"""
import logging
import time
from typing import Callable, Literal

from pydantic import BaseModel, Field

from . import config

log = logging.getLogger(__name__)


class DailyQuotaExceeded(Exception):
    """Free tierin päiväkiintiö täynnä — lisäkutsut ovat turhia tänään."""


def _is_daily_quota_error(e: Exception) -> bool:
    msg = str(e)
    return "RESOURCE_EXHAUSTED" in msg and "PerDay" in msg


class AnalyzedItem(BaseModel):
    row: int = Field(description="Artikkelin numero syötelistassa (1-alkuinen)")
    relevant: bool = Field(description="Onko uutinen relevantti Suomen Golfliiton mediakatsaukseen")
    title_fi: str = Field(description="Sujuva suomenkielinen otsikko")
    summary_fi: str = Field(description="1-2 lauseen suomenkielinen tiivistelmä")
    category: str = Field(description="Yksi annetuista kategorioista")
    priority: Literal["korkea", "keskitaso", "matala"]
    themes: list[str] = Field(description="0-3 teemaa annetusta listasta")


_PROMPT_GOLF = """Olet Suomen Golfliiton VIESTINTÄPÄÄLLIKÖN mediamonitoroinnin
analyytikko. Saat listan golfliittojen ja golfalan virallisten
organisaatioiden uutisia.

Viestintäpäällikköä kiinnostaa VAIN se, mistä Suomen Golfliitto voi saada aitoa
hyötyä omaan toimintaansa: uudet kampanjat, jäsenhankinta, digitaaliset palvelut
ja tekoäly, yhteistyöt ja kumppanuudet, kestävä kehitys ja ekologisuus,
rahoitusmallit, harrastajamäärien kehitys, viestinnän ja tapahtumien uudet
konseptit, merkittävät sääntö- tai hallintomuutokset.

Viestintäpäällikköä EI kiinnosta tavallinen kilpaurheilu-uutisointi:
kilpailutulokset, joukkue- ja maajoukkuevalinnat, yksittäisten pelaajien
menestys, kiertueiden osakilpailut, lähtöajat, kilpailujen ilmoittautumisten
avautumiset, karsinnat ja karsintaselitykset, osallistujalistat ja
kilpailujärjestelyjen rutiinitiedotteet.

Tee jokaiselle artikkelille:
1. relevant:
   - false: kilpailutulokset, joukkuevalinnat, pelaajauutiset, lähtöajat,
     tulosluettelot, ilmoittautumiset, karsinnat, osallistujalistat,
     navigaatiotekstit, mainokset — riippumatta siitä onko kyse junioreista,
     naisista tai arvokisoista.
   - POIKKEUS: jos uutisella on VAHVA Suomi-kytkös (suomalainen pelaaja
     keskeisessä roolissa, tapahtuma Suomessa), pidä relevant=true.
   - Jos sama uutinen esiintyy listassa useaan kertaan (esim. sama
     kumppanuustiedote eri muodoissa), merkitse vain yksi relevant=true
     ja muut relevant=false.
   - true: kaikki, mikä osuu yllä lueteltuihin kiinnostuksen kohteisiin.
2. title_fi: Käännä otsikko sujuvaksi, toimitukselliseksi suomeksi. ÄLÄ käännä
   sanasta sanaan — kirjoita kuten suomalainen urheilutoimittaja otsikoisi saman
   uutisen. Säilytä erisnimet, kilpailujen nimet ja organisaatioiden lyhenteet
   (esim. R&A, USGA) sellaisenaan.
3. summary_fi: 1-2 lauseen tiivistelmä suomeksi otsikon ja ingressin pohjalta.
   Jos ingressiä ei ole, tiivistä otsikon sisältö äläkä keksi yksityiskohtia.
4. category: yksi näistä: {categories}
5. priority — OLE ANKARA. Korkea on harvinainen: tyypillisessä ajossa
   0-2 artikkelia sadasta ansaitsee sen. Korkea VAIN jos vähintään yksi täyttyy:
   a) Siirrettävä toimintamalli, josta on jo TULOKSIA tai mittakaavaa
      (esim. jäsenmäärän kasvu, todennettu harrastajalisäys) — pelkkä
      hankkeen, ohjelman tai kampanjan julkistus ei riitä.
   b) Merkittävä sääntö-, rahoitus- tai rakennemuutos, joka vaikuttaa
      golfliittojen toimintaan laajasti (R&A/USGA/EGA-tason päätökset).
   c) Digitaalinen palvelu tai kumppanuusmalli, jonka Golfliitto voisi
      suoraan kopioida, TAI vahva Suomi-kytkös.
   EI KOSKAAN korkea: tavallinen ohjelma- tai tapahtumatiedote, olemassa
   olevan ohjelman jatkuminen tai laajeneminen ilman tuloksia, nimitykset,
   palkinnot, juhlavuodet, varhaisen vaiheen hankkeet.
   - keskitaso: kiinnostava ilmiö tai lupaava konsepti ilman tuloksia.
   - matala: hyvä tietää. Poikkeussäännön kautta relevanteiksi jääneet
     kilpaurheilu-uutiset ovat korkeintaan matala.
   Jos epäröit kahden tason välillä, valitse AINA alempi.
6. themes: 0-3 kpl näistä, vain jos selvästi osuvat: {themes}

Artikkelit:
{articles}"""

_PROMPT_SPORTS = """Olet Suomen Golfliiton VIESTINTÄPÄÄLLIKÖN mediamonitoroinnin
analyytikko. Saat listan muiden suomalaisten lajiliittojen uutisia.

Viestintäpäällikköä kiinnostaa VAIN se, mistä Golfliitto voi saada aitoa hyötyä
omaan toimintaansa lajiliittona: uudet kampanjat, jäsen- ja harrastajahankinta,
digitaaliset palvelut ja tekoäly, yhteistyöt ja kumppanuudet, sponsorointimallit,
kestävä kehitys ja ekologisuus, rahoitusratkaisut, seurakehitys, viestinnän ja
tapahtumien uudet konseptit, harrastajamäärien kehitys.

Viestintäpäällikköä EI kiinnosta lajien urheilu-uutisointi: ottelu- ja
kilpailutulokset, maajoukkuevalinnat ja kokoonpanot, yksittäisten urheilijoiden
menestys tai siirrot, otteluennakot.

Tee jokaiselle artikkelille:
1. relevant:
   - false: tulokset, joukkuevalinnat, urheilija- ja otteluuutiset — vaikka
     kyse olisi junioreista, naisista tai arvokisoista.
   - true: kaikki, mikä osuu yllä lueteltuihin kiinnostuksen kohteisiin.
2. title_fi: otsikko sellaisenaan (uutiset ovat jo suomeksi), siivoa vain
   mahdollinen lähdejäänne lopusta.
3. summary_fi: 1-2 lauseen tiivistelmä, joka kertoo MIKSI tämä kiinnostaa
   Golfliittoa (ei lajin fania).
4. category: yksi näistä: {categories}
5. priority — OLE ANKARA. Korkea on harvinainen: tyypillisessä ajossa
   0-2 artikkelia sadasta ansaitsee sen. Korkea VAIN jos vähintään yksi täyttyy:
   a) Siirrettävä toimintamalli, josta on jo TULOKSIA tai mittakaavaa
      (esim. "uusi seurapalvelumalli toi liitolle 2 000 uutta harrastajaa") —
      pelkkä hankkeen tai kampanjan julkistus ei riitä.
   b) Kaikkia lajiliittoja koskeva raha- tai politiikkapäätös: OKM:n
      avustukset, lakimuutos, Olympiakomitean linjaus, veikkausvarat.
   c) Merkittävä digitaalinen palvelu tai kaupallinen kumppanuusmalli,
      jonka Golfliitto voisi suoraan kopioida omaan toimintaansa.
   EI KOSKAAN korkea: tavallinen kampanja- tai tapahtumatiedote, yksittäisen
   tapahtuman onnistuminen (esim. "kiertue tavoitti 200 koululaista"),
   nimitysuutiset, juhlavuodet, palkinnot, lajin arkitoiminta, hanke jolla
   ei ole vielä tuloksia.
   - keskitaso: kiinnostava ilmiö tai lupaava konsepti ilman tuloksia.
   - matala: hyvä tietää.
   Jos epäröit kahden tason välillä, valitse AINA alempi.
6. themes: 0-3 kpl näistä, vain jos selvästi osuvat: {themes}

Artikkelit:
{articles}"""


def _format_articles(batch: list[dict]) -> str:
    lines = []
    for i, a in enumerate(batch, 1):
        lines.append(
            f"{i}. [{a.get('language','?')}] {a.get('source_name','')}: {a.get('title','')}\n"
            f"   Ingressi: {(a.get('summary') or '(ei ingressiä)')[:300]}"
        )
    return "\n".join(lines)


def _analyze_batch(client, batch: list[dict], tab: str) -> list[dict]:
    from google.genai import types

    template = _PROMPT_SPORTS if tab == "urheilu_liitot" else _PROMPT_GOLF
    prompt = template.format(
        categories=", ".join(config.CATEGORIES),
        themes=", ".join(config.THEMES),
        articles=_format_articles(batch),
    )
    resp = client.models.generate_content(
        model=config.GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=list[AnalyzedItem],
            temperature=0.2,
        ),
    )
    items: list[AnalyzedItem] = resp.parsed or []

    results = []
    for item in items:
        if not 1 <= item.row <= len(batch):
            continue
        art = batch[item.row - 1]
        results.append({
            "article_id": art["id"],
            "relevant": item.relevant,
            "title_fi": item.title_fi.strip(),
            "summary_fi": item.summary_fi.strip(),
            "category": item.category if item.category in config.CATEGORIES else "muu",
            "priority": item.priority,
            "themes": [t for t in item.themes if t in config.THEMES][:3],
        })
    return results


def analyze_pending(pending: list[dict], save_cb: Callable[[list[dict]], None]) -> tuple[int, int]:
    """Analysoi 'new'-tilaiset artikkelit erissä. Palauttaa (analysoitu, epäonnistuneet erät).

    save_cb kutsutaan HETI jokaisen onnistuneen erän jälkeen (checkpoint).
    """
    if not config.GEMINI_API_KEY:
        log.warning("GEMINI_API_KEY puuttuu — analyysi ohitetaan, artikkelit jäävät 'new'-tilaan")
        return 0, 0

    from google import genai
    client = genai.Client(api_key=config.GEMINI_API_KEY)

    analyzed = 0
    failed_batches = 0
    consecutive_failed = 0
    by_tab: dict[str, list[dict]] = {}
    for a in pending:
        by_tab.setdefault(a["tab"], []).append(a)

    total_batches = sum(
        (len(v) + config.BATCH_SIZE - 1) // config.BATCH_SIZE for v in by_tab.values()
    )
    batch_no = 0

    for tab, articles in by_tab.items():
        for i in range(0, len(articles), config.BATCH_SIZE):
            batch = articles[i:i + config.BATCH_SIZE]
            batch_no += 1
            log.info("Erä %d/%d (%s, %d artikkelia)", batch_no, total_batches, tab, len(batch))

            results = None
            try:
                for attempt in range(1, config.BATCH_RETRIES + 1):
                    try:
                        results = _analyze_batch(client, batch, tab)
                        break
                    except Exception as e:  # noqa: BLE001 — free tier heittelee 429/503
                        if _is_daily_quota_error(e):
                            raise DailyQuotaExceeded from e
                        log.warning("Erä %d yritys %d/%d epäonnistui: %s",
                                    batch_no, attempt, config.BATCH_RETRIES,
                                    str(e).split("{")[0].strip())
                        if attempt < config.BATCH_RETRIES:
                            time.sleep(10 * attempt)
            except DailyQuotaExceeded:
                remaining = total_batches - batch_no + 1
                log.warning(
                    "Geminin PÄIVÄKIINTIÖ TÄYNNÄ — keskeytetään analyysi. "
                    "%d erää jäi jonoon — aja ./run.sh uudelleen, kun kiintiö on "
                    "nollautunut (vuorokauden sisällä), niin jono puretaan.",
                    remaining)
                return analyzed, failed_batches + remaining

            if results:
                save_cb(results)          # checkpoint heti
                analyzed += len(results)
                consecutive_failed = 0
            else:
                failed_batches += 1       # jää 'new' -> uusi yritys seuraavassa ajossa
                consecutive_failed += 1
                if consecutive_failed >= 2:
                    # Kaksi erää putkeen nurin = systeeminen vika (ruuhka/kiintiö).
                    # Ei tuhlata kutsuja loppuihin — jono säilyy seuraavaan ajoon.
                    remaining = total_batches - batch_no
                    log.warning(
                        "Kaksi erää peräkkäin epäonnistui — malli todennäköisesti "
                        "ruuhkautunut. Keskeytetään analyysi, %d erää jää jonoon. "
                        "Kokeile myöhemmin uudelleen tai vaihda mallia "
                        "(GEMINI_MODEL .env-tiedostossa).", remaining)
                    return analyzed, failed_batches + remaining

            if batch_no < total_batches:
                time.sleep(config.BATCH_PAUSE_S)

    return analyzed, failed_batches
