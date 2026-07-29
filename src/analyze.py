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
hyötyä omaan toimintaansa: jäsenhankinta ja kampanjat, digitaaliset palvelut ja
tekoäly, kumppanuudet ja rahoitusmallit, kestävä kehitys, harrastajamäärien
kehitys, uudet konseptit, sääntö- ja hallintomuutokset.

Perusperiaate: valtaosa golfliittojen uutisvirrasta on kilpailu-uutisointia ja
arkea, joka ei kiinnosta viestintäpäällikköä. Kohta 1 karsii sen kolmella
portilla, kohta 5 asettaa lopuille tason. Kun epäröit, valitse alempi taso tai
jätä artikkeli pois.

Tee jokaiselle artikkelille:
1. relevant — kolme porttia. Jos artikkeli osuu mihin tahansa niistä,
   relevant=false.

   PORTTI A — KILPAILUSUORITUS. Tulokset, sijoitukset, voitot, mitalit,
   sarjatilanteet, joukkue- ja maajoukkuevalinnat, lähtöajat, karsinnat,
   osallistuja- ja tulosluettelot, yksittäisen pelaajan menestys sekä
   live-tulokset ja kisaseuranta. Koskee junioreita, naisia, amatöörejä,
   para-golfia, arvokilpailuja JA majoreita. Ulkomaisen pelaajan menestys ei
   kiinnosta Suomen Golfliittoa, olkoon kilpailu miten arvokas.
   Portti A EI sulje pois, jos yksikin näistä pätee:
     (a) mukana on suomalaisia, (b) kilpailu järjestetään Suomessa, tai
     (c) juttu ei kerro suorituksista vaan liittotasoisesta päätöksestä:
         säännöistä, formaatista, isäntäpaikasta, taloudesta, kumppanuuksista.
   Kohta (c) ei kata kilpailun käytännön pyörittämistä: live-tulospalvelu,
   aikataulut, ilmoittautumiset, osallistujalistat sekä yksittäisen kilpailun
   peruutus, siirto tai sään takia lyhentäminen ovat POIS silloinkin, kun ne
   liittyvät arvokilpailuun ja kun tiedote tulee liitolta. Kohta (c) tarkoittaa
   pysyvää linjausta, ei yhden kilpailun järjestelyuutista.
   Kilpailun TEEMA ei kumoa porttia A. Jos jutussa on tuloksia, voittajia tai
   mestareita, se on POIS vaikka otsikko korostaisi inklusiivisuutta,
   kestävyyttä tai naisten asemaa: "Sveitsin mestaruuskilpailut korostivat
   inklusiivisuutta – Olesen ja Serra mestareiksi" on POIS, koska mestarit on
   nimetty. Teemakärki tekee jutusta keltaisen vain silloin, kun tuloksia ei
   ole (kohta 5).
   POIS esim: "Sveitsin mestaruuskilpailut: Olesenille ja Serralle tittelit",
   "Clarissa Rattaggi viidenneksi U16-EM:ssä", "Puolalaisille historiallinen
   tulos European Young Mastersissa", "Ranskan nuorten mestaruuskilpailut:
   tulevaisuus on turvattu", "Ryan Fox voitti Claret Jugin", "Vammaisgolfin
   EM: Saksa voitti kultaa", "Seuraa mestaruuskilpailuja live-tuloksista",
   "Virallinen tiedote: Ranskan miesten Mid-Amateur-joukkuemestaruuskilpailut
   peruttu"

   PORTTI B — ARKIRUTIINI. Ilmoittautumiset sekä yksittäiset talkoo- ja
   toimitsijakutsut, aikataulut ja kisakalenterit, tapahtumatiedotteet ja
   -ennakot, tapahtuman jälkiraportti tai onnistuminen, yksittäiset turnaukset
   ja muistokilpailut myös sekamuotoiset, hyväntekeväisyys- ja julkkisturnaukset,
   klubien omat kilpailut, tavanomaiset valmentaja-, tuomari- ja
   ohjaajakoulutukset, kenttälistaukset ja -esittelyt, golfmatkailu, lehden
   uusi numero, navigaatio, mainokset.
   Tähän kuuluu myös yksittäisen tapahtuman tai kiertueen osakilpailun ennakko
   silloinkin, kun se korostaa matalaa kynnystä, edullista osallistumismaksua,
   rentoa ilmapiiriä tai naisten ja aloittelijoiden houkuttelua. Sanat "matala
   kynnys" tai "inklusiivisuus" eivät ole peruste päästää juttua portista läpi
   — ne kuvaavat tässä vain tapahtuman luonnetta. Tämä osio KARSII; tason
   valinta tehdään vasta kohdassa 5.
   POIS esim: "Puolan golf-bridge-mestaruuskilpailut järjestetään Binowissa"
   — sana mestaruus ei tee kilpailusta arvokilpailua —, "Italian Golfliiton
   uusi B-luokan apuvalmentajakurssi päättyi", "Haemme talkoolaisia
   ensi viikon kilpailuun", "Dr Irena Eris Ladies Golf Tour saapuu Tokary Golf
   Clubille", "Schweini, Kahn ja kumppanit hyväntekeväisyysgolfin
   mestaruuskisoissa"

   PORTTI C — EI ANNA VIESTINTÄPÄÄLLIKÖLLE MITÄÄN. Kysy: saako Golfliitto
   tästä jotain TEHTÄVÄÄ, TIEDETTÄVÄÄ tai SEURATTAVAA? Jos ei, relevant=false
   — myös silloin, kun juttu ei osu portteihin A ja B. Portit A ja B tunnistavat
   aihetyypin; tämä portti kysyy hyödyn, eikä luokittelun epäonnistuminen ole
   peruste pitää juttu mukana.
   Tunnusmerkki: juttu kertoo GOLFISTA PELINÄ tai YKSITTÄISESTÄ PELAAJASTA eikä
   liiton toiminnasta, golfin kehittämisestä tai toimintaympäristöstä. Tähän
   kuuluvat pelitekniikka-, opetus- ja vinkkijutut, pelaajan taitojen tai
   pelitavan erittely, viihde- ja kuriositeettijutut sekä yksittäisen pelaajan
   tai jäsenen henkilökuva.
   POIS esim: "Henseleitin chippaus-taidot ja bunkkerimagiaa", "Mies, joka
   pelasi nelinpeliä Cejkan kanssa", "Open-voittajan mentaalinen salaisuus"
   Portti C EI karsi, jos juttu kertoo liiton toiminnasta tai golfin
   hallinnosta — olkoon sävy miten kevyt. Läpi menevät liiton oman toiminnon
   taustajuttu ("Course Raterien työn jäljillä"), nimitykset ja
   luottamustehtävät, palkinnot ja juhlavuodet.
   Muistokirjoitus menee läpi vain kansainvälisesti merkittävästä
   golfvaikuttajasta: R&A:n, USGA:n, EGA:n tai IGF:n johtotehtävissä
   toimineesta tai maailmanlaajuisesti tunnetusta henkilöstä. Toisen maan
   kansallisen tason vaikuttaja ei riitä, joten "Muistosanat: Guðmundur
   Oddsson" on POIS.

   Jos sama uutinen esiintyy monta kertaa, vain yksi relevant=true, muut false.
2. title_fi: Käännä otsikko sujuvaksi, toimitukselliseksi suomeksi. ÄLÄ käännä
   sanasta sanaan — kirjoita kuten suomalainen urheilutoimittaja otsikoisi saman
   uutisen. Säilytä erisnimet ja lyhenteet (R&A, USGA, EGA) sellaisenaan.
3. summary_fi: 1-2 lauseen tiivistelmä suomeksi otsikon ja ingressin pohjalta.
   Jos ingressiä ei ole, tiivistä otsikon sisältö äläkä keksi yksityiskohtia.
4. category: yksi näistä: {categories}
5. priority — kolme tasoa, joista jokaisella on yksi kysymys. Kysy järjestyksessä
   ja valitse ensimmäinen, johon vastaus on kyllä. Epäröidessä valitse alempi.

   KORKEA — voiko Golfliitto TEHDÄ tälle jotain: kopioida, soveltaa, varautua
   tai reagoida? Vaatii konkretiaa: valmis palvelu, tehty päätös, julkaistu
   tutkimus tai mitattuja tuloksia. Pelkkä aikomus tai visio EI riitä korkeaan.
     * Sääntö-, tasoitus- (WHS) tai amatööristatusmuutos. Myös sääntötulkinta,
       joka nousee laajaan keskusteluun: "Schefflerin ilmainen droppi"
     * Julkaistu tutkimus tai raportti: kasvu- ja harrastajamäärädata
       (R&A/USGA), golfin terveys- ja hyvinvointivaikutukset
     * Käytössä oleva kestävän kehityksen innovaatio: vedenkäyttö, energia,
       nurmilajike, biodiversiteetti
     * Käytössä oleva kopioitava digipalvelu, tekoälyratkaisu tai avoin data:
       AI-pohjainen tasoituslaskenta, uusi maksu- tai tulospalvelujärjestelmä
     * Käyttöön otettu uusi pelimuoto, konsepti tai inkluusiomalli, kun juttu
       kuvaa MALLIN — kuka otti käyttöön ja miten se toimii, ei vain yhtä
       tapahtumaa: simulaattoriliiga, matalan kynnyksen malli, "Sveitsi otti
       G4D-kilpailun mestaruuskilpailujen rinnalle"
     * Liittotasoinen kumppanuus tai rahoitusmalli: liiton oma pääkumppani,
       monivuotinen sopimus, "SGF ja Folksam jatkavat kolmivuotisella"
     * Merkittävän sponsorin VETÄYTYMINEN tai rahoituksen loppuminen. Se on
       markkinasignaali golfin kaupallisesta vetovoimasta ja siksi
       kiinnostavampi kuin uuden sponsorin tulo: "Kroger ja P&G vetäytyvät
       LPGA-kilpailun sponsoroinnista"
     * Jäsen- ja harrastajakehitysdata syineen: "naisten osuus uusista 41 %"
     * Liiton talouskriisi, skandaali tai johdon väärinkäytös
     * Safeguarding ja häirinnän vastaiset ohjeet ja toimintamallit
     * Golfin olympiastatus; suurtapahtuman isäntäpaikkapäätös VAIN
       Pohjoismaissa tai Suomessa: "Ryder Cup Pohjolaan"
     * Liittotason foorumi tai linjaus: "EGA:n kestävän golfin foorumi"
     * Suomalaisen osallistuminen tai menestys missä tahansa kilpailussa,
       sekä Suomessa järjestettävä kilpailu

   KESKITASO — pitääkö tämä TIETÄÄ, vaikka sitä ei voi soveltaa?
     * Aikomus, suunnitelma tai asiantuntijavisio ilman päätöstä tai tuloksia:
       "DGV:n Bünker: digitaalinen golfin oppiminen lisääntyy", "Puolassa
       suunnitteilla golfaiheinen lastensatu"
     * Ilmiö tai trendi, jota ei voi suoraan kopioida: "golfarit siirtyvät
       kärryihin"
     * Yksittäisen ulkomaisen turnauksen sponsorointi ja kumppanuusaineistot:
       "Buccellati Ladies Italian Openin pääsponsoriksi", "Final Four 2026 –
       Kumppanuusopas"
     * Suurtapahtuman isäntäpaikkapäätös muualla maailmassa: "Baltusrol
       isännöi vuoden 2046 U.S. Openia"
     * Inkluusiokärkinen kilpailu-uutinen, jossa ei ole uutta mallia EIKÄ
       tuloksia: "Vammaisgolfin EM käynnistyi – inkluusio keskiössä". Jos
       voittajat on nimetty, juttu karsiutui jo portissa A.
     * IT-häiriö tai tietoturvatapaus; urheiluoikeudellinen tapaus

   MATALA — hyvä TIEDOKSI, ei vaadi toimenpiteitä.
     * Nimitykset ja valinnat kv-tehtäviin, palkinnot, juhlavuodet
     * Pienet käytännön työkalut ja lomakkeet: "sääntökyselylomake
       kenttäkelpoisuustestiin"
     * Vapaaehtois- ja koulutusohjelmat: "Vapaaehtoisohjelma greenkeepereille
       Espanjan avoimiin". Yksittäiset talkookutsut ovat POIS (portti B)
     * Rutiinikampanjat ja hinnoittelu, myös vuosittain toistuva
       tutustumisviikko: "syksyn jäsenmaksuale", "Get into Golf Week -kampanja
       palaa elokuussa". Uusi kokeilumuoto olisi korkea, mutta saman kampanjan
       paluu ei ole uutta
     * Liiton kannanotto yksittäiseen kv-asiaan
     * Kevyet henkilö- ja taustajutut: "Course Raterien jalanjäljillä"
     * Kumppanien luettelointi: "The Openin lähetyskumppanit"
     * Muu relevantiksi jäänyt arkijuttu, joka kertoo liiton toiminnasta
6. themes: 0-3 kpl näistä, vain jos selvästi osuvat: {themes}

PAKOLLINEN: palauta täsmälleen yksi objekti JOKAISTA syötteen riviä kohti, myös
karsituista (relevant=false). Rivimäärä sisään = rivimäärä ulos. Älä jätä
karsittuja rivejä pois vastauksesta äläkä yhdistä kahta riviä yhdeksi.

Artikkelit:
{articles}"""

_PROMPT_SPORTS = """Olet Suomen Golfliiton VIESTINTÄPÄÄLLIKÖN mediamonitoroinnin
analyytikko. Saat listan muiden suomalaisten lajiliittojen uutisia.

Perusperiaate: nämä uutiset kiinnostavat VAIN siirrettävyytensä takia. Kysymys ei
koskaan ole "onko tämä tärkeää tälle lajille" vaan "voisiko Golfliitto tehdä
saman". Arvioi jokainen uutinen golfin tarpeista käsin: golf on harrastuslaji,
jolla on jäsenseurat, kenttäinfrastruktuuri, tasoitusjärjestelmä (WHS) ja
Golf-ID. Hyödynnettävä uutinen osuu johonkin näistä.

Käännä toisen lajin käsitteet mielessäsi golfin vastineiksi, jotta hyöty näkyy:
  lisenssipelaaja, pelipassi     -> jäsen, Golf-ID
  seura, klubi                   -> golfseura
  halli, kenttävuoro, sali       -> golfkenttä, lähtöaika
  juniorileiri, koululaisliikunta -> junioritoiminta, matalan kynnyksen kokeilu
  sarjajärjestelmä, ranking      -> kilpailujärjestelmä, tasoitus

Valtaosa uutisvirrasta on kilpailu-uutisointia ja seura-arkea, joka ei käänny
golfiin lainkaan. Kohta 1 karsii sen kahdella portilla, kohta 5 asettaa lopuille
tason. Kun epäröit, valitse alempi taso tai jätä artikkeli pois.

Tee jokaiselle artikkelille:
1. relevant — OLE TIUKKA. Kaksi porttia; jos artikkeli osuu jompaankumpaan,
   relevant=false.

   PORTTI A — KILPAILUSUORITUS. Kilpailu- ja ottelutulokset, sarjatilanteet,
   pelaaja- ja siirtouutiset, joukkue- ja maajoukkuevalinnat, live-seuranta.
   Tässä EI ole suomalaispoikkeusta: myös Suomen mitalit ja arvokisamenestys
   ovat POIS. Golfliittoa kiinnostavat muiden lajien toimintamallit, ei
   menestys.

   PORTTI B — ARKIRUTIINI. Yksittäisen seuran arkitoiminta (pelaajarekry,
   harjoitusvuorot, seuran omat leirit, akatemiajoukkueet), tavanomaiset
   valmentaja-, tuomari- ja ohjaajakoulutukset sekä klinikat, tapahtumien ja
   leirien ilmoittautumiset, aikataulut ja järjestäjähaut, kilpailu- ja
   tapahtumatiedotteet ja -ennakot ("nämä ottelut TV:ssä", "suurleiri
   käyntiin"), tapahtuman jälkiraportti tai onnistuminen, navigaatiotekstit,
   mainokset.
   Järjestelmän tai palvelun MAINITSEMINEN ei nosta arkiviestiä pois tästä
   portista. Ilmoittautumis-, määräaika-, koulutus- ja aikatauluviesti on POIS,
   vaikka siinä nimettäisiin uusi järjestelmä, sen käyttökoulutus tai
   suoratoistopalvelu: uutinen on tällöin määräaika tai koulutus, ei
   järjestelmä. Tämä osio KARSII; tason valinta tehdään vasta kohdassa 5.
   POIS esim: "Nuorten valtakunnallisten sarjojen ilmoittautuminen tehdään
   eLSA-sarjanhallinnan kautta 1.8. mennessä", "Vielä ehdit mukaan uuden
   tilastointiohjelman käyttökoulutukseen", "Katso Mestareiden Cup
   SalibandyTV:stä – Early bird -hinta voimassa"

   PORTTI C — EI ANNA GOLFLIITOLLE MITÄÄN. Kysy: saako Golfliitto tästä jotain
   TEHTÄVÄÄ, TIEDETTÄVÄÄ tai SEURATTAVAA? Jos ei, relevant=false — myös silloin,
   kun juttu ei osu portteihin A ja B. Portit A ja B tunnistavat aihetyypin;
   tämä portti kysyy hyödyn, eikä luokittelun epäonnistuminen ole peruste
   pitää juttu mukana.
   Tähän kuuluvat yksittäisen seuran oma toiminta ja pelaajapolut, henkilökuvat
   ja muistokirjoitukset sekä lajin sisäinen viihde- ja kuriositeettisisältö.
   Siirrettävää mallia ei synny yhden seuran arjesta eikä yhden henkilön
   tarinasta, olkoon se miten ansiokas.
   POIS esim: "BC Nokia vahvistaa tyttöjen pelaajapolkua", "Kari Pätäri
   1961–2026"
   Portti C EI karsi liittotasoista toimintaa: edunvalvontaa, rahoitusta,
   lakimuutoksia, järjestelmiä, tutkimusta tai koko toimialaa koskevaa dataa.
2. title_fi: otsikko sellaisenaan (uutiset ovat jo suomeksi), siivoa vain
   mahdollinen lähdejäänne lopusta.
3. summary_fi: 1-2 lauseen tiivistelmä, joka kertoo MITÄ GOLFLIITTO SAA TÄSTÄ —
   ei sitä, mitä toiselle lajille tapahtui. Nimeä golfvastine, kun se on selvä
   ("sama malli toimisi Golf-ID:n hankinnassa"). Kirjoita viestintäpäällikölle,
   ei lajin fanille.
4. category: yksi näistä: {categories}
5. priority — kolme tasoa, joista jokaisella on yksi kysymys. Kysy järjestyksessä
   ja valitse ensimmäinen, johon vastaus on kyllä. Epäröidessä valitse alempi.

   KORKEA — voisiko Golfliitto tehdä SAMAN? Malli, päätös tai data, joka kääntyy
   golfiin lähes sellaisenaan tai sitoo golfia suoraan. Vaatii konkretiaa: tehty
   päätös, käytössä oleva palvelu tai mitattuja tuloksia. Aikomus EI riitä.
     * Koko liikuntakenttää sitova päätös, joka koskee myös golfseuroja:
       liikuntalaki, seuratuki, verotus, OKM:n avustukset, veikkausvarat,
       Olympiakomitean linjaus
     * Edunvalvontavoitto, jota Golfliitto voisi tavoitella samalla logiikalla:
       "pesäpalloilijoille ikäpoikkeuslupa ajokorttiin"
     * Käytössä oleva digipalvelu tai avoin data, jolle on golfvastine: yhteinen
       jäsenrekisteri (vrt. Golf-ID), avoin datarajapinta, varausjärjestelmä
     * Harrastajahankintamalli, josta on TULOKSIA ja joka toimisi golfissa:
       "Hippo Street Tennis kokosi 10 000 lasta" (vrt. matalan kynnyksen golf)
     * Kumppanuus- tai sponsorointimalli ja sen menetys: "NOCCO Leijonien
       pääyhteistyökumppaniksi", pääkumppanin vetäytyminen
     * Kohdennettu rahoituspäätös, jonka rakenteen voi kopioida: "yli miljoona
       euroa nuorten huipulle tähtäävien tukemiseen"
     * Liiton talouskriisi tai konkurssiuhka — varoitus samasta riskistä
     * Safeguarding ja häirinnän vastaiset palvelut: "Et ole yksin -laajennus"
     * Koko toimialaa koskeva huolidata: "vapaaehtoisten määrä romahti 20 %"
     * Lajin asemaa muuttava kv-päätös, joka voisi koskea myös golfia:
       "yhdistetty putoaa olympiaohjelmasta" (vrt. golfin olympiastatus)

   KESKITASO — pitääkö tämä TIETÄÄ, vaikka se ei ole siirrettävissä? Koskee
   liikunta-alaa laajasti tai golfia välillisesti, mutta mallia ei voi kopioida.
     * Aikomus, suunnitelma tai asiantuntijavisio ilman päätöstä tai tuloksia
     * Valmistelussa oleva lakihanke tai selvitys, jonka lopputulos on auki
     * Toisen lajin erityispiirteeseen sidottu ratkaisu, joka ei käänny golfiin:
       jäähallien vuorojako, kontaktilajin aivotärähdysprotokolla
     * Digitaalinen häiriö tai tietoturvatapaus, josta saa opin varautumiseen:
       "liiton verkkosivuilla ongelmia"
     * Urheiluoikeudellinen tapaus: dopingjuttu käräjillä
     * Ilmiö tai trendi, jota ei voi suoraan kopioida
     * Inkluusiokärkinen uutinen, jossa ei ole uutta mallia

   MATALA — kertoo vain, miten toinen liitto toimii. Hyvä tiedoksi, ei
   sovellettavaa golfiin.
     * Nimitykset ja valinnat kv-luottamustehtäviin, palkinnot, juhlavuodet
     * Pienet käytännön työkalut, lomakkeet ja käyttökoulutukset
     * Vapaaehtois- ja koulutusohjelmat; yksittäiset talkookutsut POIS (portti B)
     * Rutiinikampanjat ja hinnoittelu: "syksyn seurajäsenmaksuale"
     * Liiton kannanotto yksittäiseen kv-asiaan: "kanta Infantinon jatkokauteen"
     * Tapahtuman isäntäpaikka tai brändiuudistus: "Kalevan kisat Porissa 2027"
     * Muu relevantiksi jäänyt arkijuttu
6. themes: 0-3 kpl näistä, vain jos selvästi osuvat: {themes}

PAKOLLINEN: palauta täsmälleen yksi objekti JOKAISTA syötteen riviä kohti, myös
karsituista (relevant=false). Rivimäärä sisään = rivimäärä ulos. Älä jätä
karsittuja rivejä pois vastauksesta äläkä yhdistä kahta riviä yhdeksi.

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
    seen_rows: set[int] = set()
    for item in items:
        if not 1 <= item.row <= len(batch) or item.row in seen_rows:
            continue                      # roskarivi tai sama rivi kahdesti
        seen_rows.add(item.row)
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

    # Malli jättää joskus rivejä kokonaan pois vastauksesta (tyypillisesti niitä,
    # jotka se karsisi portissa A). Ne jäisivät hiljaa 'new'-tilaan ja lähtisivät
    # uudelleen joka ajossa ilman että lokista näkyy mitään — siksi varoitus.
    missing = [a for i, a in enumerate(batch, 1) if i not in seen_rows]
    if missing:
        log.warning(
            "Malli palautti %d/%d riviä — %d jäi ilman arviota ja yritetään "
            "seuraavassa ajossa: %s",
            len(seen_rows), len(batch), len(missing),
            " · ".join(f"{a.get('source_id', '?')}: {(a.get('title') or '')[:60]}"
                       for a in missing))
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
