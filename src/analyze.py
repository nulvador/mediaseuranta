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

Perusperiaate: valtaosa golfliittojen uutisvirrasta on arkista hötöä, joka ei
kiinnosta viestintäpäällikköä. Punaisen ansaitsee vain uutinen, jossa on aitoa
substanssia (ks. kohta 5). Keltainen on harvinainen välitila. Kun epäröit,
valitse alempi taso tai jätä artikkeli pois (relevant=false).

Tee jokaiselle artikkelille:
1. relevant — false kaikelle arkiselle, myös:
   - kilpailu- ja ottelutulokset, sarjatilanteet, lähtöajat, karsinnat,
     osallistuja- ja tulosluettelot, joukkue- ja maajoukkuevalinnat,
     pelaajauutiset — vaikka kyse olisi junioreista, naisista tai arvokisoista
   - tapahtumatiedotteet ja -ennakot, kisaseuranta ("seuraa MM-kilpailua"),
     tapahtuman jälkiraportti tai onnistuminen ("golfpäivä onnistui hyvin")
   - ilmoittautumiset, vapaaehtoisrekry, kilpailujen järjestäjähaut
   - golfkenttä-listaukset ja -esittelyt, golfmatkailujutut
   - digitaalisen julkaisun/lehden uusi numero, navigaatio, mainokset
   POIKKEUS: vahva Suomi-kytkös (suomalainen pelaaja keskeisessä roolissa tai
   tapahtuma Suomessa) → relevant=true (yleensä matala).
   Jos sama uutinen esiintyy monta kertaa, vain yksi relevant=true, muut false.
2. title_fi: Käännä otsikko sujuvaksi, toimitukselliseksi suomeksi. ÄLÄ käännä
   sanasta sanaan — kirjoita kuten suomalainen urheilutoimittaja otsikoisi saman
   uutisen. Säilytä erisnimet ja lyhenteet (R&A, USGA, EGA) sellaisenaan.
3. summary_fi: 1-2 lauseen tiivistelmä suomeksi otsikon ja ingressin pohjalta.
   Jos ingressiä ei ole, tiivistä otsikon sisältö äläkä keksi yksityiskohtia.
4. category: yksi näistä: {categories}
5. priority:
   - korkea = uutisessa on aitoa substanssia Golfliitolle. Tyyppitapaukset:
     * Sääntö-, tasoitus- (WHS) tai amatööristatusmuutos, joka koskee pelaajia
     * Kansainvälinen kasvu- tai harrastajamääräraportti (R&A/USGA-tutkimukset)
     * Golfin terveys- tai hyvinvointitutkimus
     * Kestävä kehitys / ympäristöinnovaatio: vedenkäyttö, energia, uusi
       nurmilajike, biodiversiteetti golfkentillä
     * Kopioitava digipalvelu, tekoälyratkaisu tai avoin data (esim. AI-pohjainen
       tasoituslaskenta, uusi maksu-/tulospalvelujärjestelmä)
     * Merkittävä kumppanuus, sponsorointi- tai rahoitusmalli
     * Jäsen-/harrastajakehitysdata syineen ("naisten osuus uusista 41 %")
     * Liiton talouskriisi, skandaali tai johdon väärinkäytös
     * Safeguarding / häirinnän vastaiset ohjeet ja toimintamallit
     * Golfin olympiastatus tai kv-suurtapahtuman isännöinti (Ryder Cup ym.)
     * Uusi pelimuoto tai konsepti (simulaattoriliiga, matalan kynnyksen malli)
     * Merkittävä liittotason foorumi/linjaus tai asiantuntijanäkemys
       viestinnän/digin tulevaisuudesta
   - keskitaso (harvinainen): kiinnostava ilmiö tai trendi ilman suoraa
     hyötyä, jota ei voi suoraan kopioida (esim. "golfarit siirtyvät
     kärryihin", urheiluoikeudellinen tapaus).
   - matala: relevantiksi jäänyt arkijuttu, Suomi-kytköksiset kilpauutiset,
     rutiininomainen mutta lievästi kiinnostava sisältö.
   EI KOSKAAN korkea: nimitykset, palkinnot, juhlavuodet, tapahtuman
   järjestäminen/onnistuminen, ohjelman jatkuminen ilman uutta sisältöä.
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

Perusperiaate: valtaosa lajiliittojen uutisvirrasta on arkista hötöä, joka ei
kiinnosta Golfliittoa. Punaisen ansaitsee vain uutinen, jossa on aitoa
substanssia (ks. kohta 5). Keltainen on harvinainen välitila. Kun epäröit,
valitse alempi taso tai jätä pois (relevant=false).

Tee jokaiselle artikkelille:
1. relevant — OLE TIUKKA. false kaikelle arkiselle, myös:
   - kilpailu- ja ottelutulokset, sarjatilanteet, pelaaja- ja siirtouutiset,
     joukkue- ja maajoukkuevalinnat, myös Suomen mitalit ja arvokisamenestys
   - yksittäisen seuran arkitoiminta: pelaajarekry ("seura etsii pelaajia"),
     harjoitusvuorot, seuran omat leirit, akatemiajoukkueet
   - tavanomaiset valmentaja-, tuomari- ja ohjaajakoulutukset, valmentajaklinikat
   - tapahtumien ja leirien ilmoittautumiset, aikataulut, järjestäjähaut
   - kilpailu- ja tapahtumatiedotteet, -ennakot ja kisaseuranta
     ("nämä ottelut TV:ssä", "seuraa MM-kilpailua", "suurleiri käyntiin")
   - tapahtuman jälkiraportti/onnistuminen, navigaatiotekstit, mainokset
2. title_fi: otsikko sellaisenaan (uutiset ovat jo suomeksi), siivoa vain
   mahdollinen lähdejäänne lopusta.
3. summary_fi: 1-2 lauseen tiivistelmä, joka kertoo MIKSI tämä kiinnostaa
   Golfliittoa (ei lajin fania).
4. category: yksi näistä: {categories}
5. priority:
   - korkea = uutisessa on aitoa substanssia Golfliitolle. Tyyppitapaukset:
     * Lakimuutos tai poliittinen päätös urheilusta: liikuntalaki, seuratuki,
       verotus, OKM:n avustukset, veikkausvarat, Olympiakomitean linjaus
     * Viranomais- tai edunvalvontavoitto, jota Golfliitto voisi tavoitella:
       "pesäpalloilijoille ikäpoikkeuslupa ajokorttiin"
     * Kopioitava digipalvelu, tekoälyratkaisu tai avoin data: yhteinen
       jäsenrekisteri, avoin datarajapinta, tekoälyavusteinen videoanalyysi
     * Jäsen-/harrastajahankintamalli, josta on TULOKSIA: "sovellus toi
       10 000 uutta harrastajaa", "kokeile kuukausi toi 4 000 lisenssipelaajaa"
     * Merkittävä kaupallinen kumppanuus: "Jääkiekkoliitto ja Kesko 2 M€",
       "NOCCO Leijonien pääyhteistyökumppaniksi"
     * Liiton talouskriisi tai konkurssiuhka
     * Safeguarding / häirinnän vastaiset palvelut ja ohjelmat
       ("Et ole yksin -palvelun laajennus")
     * Koko toimialaa koskeva huolidata: "vapaaehtoisten määrä romahti 20 %"
   - keskitaso (harvinainen): merkittävä digitaalinen häiriö tai tietoturvatapaus
     (liiton verkkosivut kaatuivat — oppi varautumiseen), urheiluoikeudellinen
     tapaus (dopingjuttu käräjillä), kiinnostava ilmiö ilman suoraa hyötyä.
   - matala: nimitykset (myös kv-luottamustehtävät), palkinnot, juhlavuodet,
     relevantiksi jäänyt arkijuttu, muu hyvä tietää.
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
