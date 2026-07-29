# Golf Media Monitor — ohjeet Claudelle

Suomen Golfliiton viestintäpäällikön mediaseuranta. Kerää uutiset golfliitoilta
ja suomalaisilta lajiliitoilta, suodattaa ja suomentaa ne Geminillä, julkaisee
salatun HTML-raportin GitHub Pagesiin.

## Kriittiset rajoitteet

**Gemini free tier: ~20 kutsua/vrk.** Kutsut = analysoitavat artikkelit /
BATCH_SIZE (50). Kiintiö nollautuu n. klo 10 Suomen aikaa.

- ÄLÄ ehdota `--reanalyze` koko kannalle. Se on satoja artikkeleita = koko
  päiväkiintiö. Käytä korkeintaan yhtä välilehteä: `--reanalyze urheilu_liitot`.
- `--reanalyze` koskee vain raportti-ikkunan (5 pv) artikkeleita. Vanhempia ei
  kannata merkitä: `pending_articles` ei poimi niitä, joten uusi arvio ei
  koskaan valmistuisi — merkintä vain hukkaisi vanhan arvion `expired`-tilaan.
- Promptin muutokset vaikuttavat uusiin artikkeleihin automaattisesti.
  Vanhoja ei tarvitse ajaa uusiksi. Muista silti: **jos muutat vain toisen
  välilehden promptia, raportissa näkyvät saman välilehden vanhat arviot ovat
  edelleen vanhalla promptilla tehtyjä.** Jos haluat nähdä muutoksen heti,
  `--reanalyze <välilehti>` on tähän oikea ja kiintiön kannalta halpa työkalu.
- Ilman Geminiä toimivat: `--report-only`, `--skip-analysis`, `--restore`,
  `--dedupe`, `--purge`, lähdekorjaukset, ulkoasumuutokset. Suosi näitä
  kehityksessä.

## Artikkelin elinkaari (status)

| status | merkitys | näkyy raportissa |
|---|---|---|
| `new` | kerätty, ei analysoitu | ei |
| `analyzed` | analysoitu, relevantti | kyllä |
| `irrelevant` | analysoitu, karsittu | ei |
| `stale` | analysoitu, prompti muuttunut → uusi arvio tulossa | kyllä (vanhalla arviolla) |
| `expired` | vanhentui ennen analyysiä | ei |

Keskeinen periaate: **raportti ei saa koskaan tyhjentyä**. Siksi
uudelleenanalyysi merkitsee `stale` (näkyy yhä) eikä `new` (katoaisi).

Malli jättää joskus rivejä kokonaan pois vastauksesta — tyypillisesti niitä,
jotka se karsisi portissa A. Ne jäävät `new`-tilaan ja lähtevät uudelleen
seuraavassa ajossa. Promptin loppu vaatii nyt yhden objektin joka riviä kohti,
ja `_analyze_batch` **varoittaa lokissa** puuttuvista otsikoineen. Jos loki
sanoo "Analysoidaan 120" mutta "Analysoitu 112", varoitus kertoo mitkä kahdeksan
jäivät ja miksi — ilman sitä ero jäi ennen kokonaan huomaamatta.

## Dedup: kaksi avainta

Sama juttu saapuu usein kahta reittiä: Google News antaa opaakin
redirect-URLin ja suora RSS kanonisen linkin. Pelkkä `url_hash` ei tunnista
paria, joten juttu analysoitiin kahdesti ja saattoi päätyä raporttiin
kaksi kertaa — pahimmillaan **eri verdiktillä** (sama otsikko sekä `analyzed`
että `irrelevant`).

- `url_hash` = sama linkki, `title_key` = lähde + normalisoitu otsikko.
- Normalisointi on tarkoituksella suppea: pienet kirjaimet, välimerkit pois,
  välit tiivistetään. **Älä lisää lähdenimen tai päätteen katkaisua** — se
  yhdistäisi myös aidosti eri juttuja, joilla on sama alku.
- Avain on lähdekohtainen. Kahden eri liiton uutinen samasta asiasta on kaksi
  eri juttua; niistä promptti valitsee yhden relevantiksi.
- `--dedupe` siivoaa ennen korjausta syntyneet parit. Kustakin ryhmästä jää
  elinkaaressa pisimmällä oleva rivi, tasatilanteessa suora linkki ennen
  Google News -redirectiä. Ei kuluta Gemini-kutsuja, turvallinen ajaa uudelleen.

Tiedostettu kompromissi: jos lähde julkaisee toistuvasti **täsmälleen samalla
otsikolla** (nimeämätön uutiskirje tms.), vain ensimmäinen menee läpi
`RETENTION_DAYS`-ikkunan ajan. Havaituissa tapauksissa toistuvassa otsikossa on
aina erotin (viikkonumero, kuukausi, päivä), ja loput olivat navigaatioroskaa
("Tulospalvelu Palloliitto"). Jos jokin lähde vaikuttaa hiljenneen ilman syytä,
tarkista ensin `title_key`-törmäys — älä oleta lähdettä rikkinäiseksi.

## Ikäsäännöt

- **Näkyvyys 5 päivää** (`REPORT_DAYS`) artikkelin julkaisusta — tai
  havaitsemisesta, jos julkaisupäivää ei tiedetä. Tätä vanhemmat poistuvat.
- Yli 5 pv vanhoja **ei analysoida** lainkaan (`expire_old_pending`).
- `RETENTION_DAYS` (90) pitää dedup-historian, jottei vanha uutinen palaa uutena.

## Priorisointisäännöt (src/analyze.py)

Arviointi on kaksivaiheinen, eikä vaiheita saa sekoittaa: **kohta 1 karsii**
kolmella portilla, **kohta 5 asettaa lopuille tason** kolmella kysymyksellä.

### Rautainen sääntö: portti ei koskaan mainitse tasoa

Tämä on kalibroinnin tärkein oppi, ja se maksoi kolme peräkkäistä virhekierrosta
7/2026. Jokainen kerta kun porttiosioon tai tasolistaan kirjoitettiin täsmennys
muodossa "X on korkea" tai "korkea tarkoittaa myös Y", malli käytti sitä
**ylennysperusteena** ja nosti juttuja jotka porttien olisi pitänyt karsia:

| Lisätty täsmennys | Mitä malli nosti |
|---|---|
| "matalan kynnyksen MALLI on korkea" (porttiin B) | "Get into Golf Week" ja Sveitsin tulosjuttu punaiseksi |
| "Juttu kertoo järjestelmästä: käyttöönotosta…" (korkeaan) | "uuden tilastointiohjelman käyttökoulutus" punaiseksi |

Siksi: **porttiosio karsii eikä mainitse tasoja lainkaan.** Jos raja koskee
sitä, mikä *karsiutuu*, kirjoita se porttiin. Jos se koskee sitä, mikä *nousee*,
kirjoita se kohtaan 5 — mutta älä koskaan kirjoita porttiin lausetta, josta voi
lukea "tämä kuuluu korkeaan".
Jokainen sääntö kuuluu täsmälleen yhteen paikkaan — päällekkäisyydet sekoittavat
mallin. Epäröidessä valitse alempi taso tai jätä pois.

### Vaihe 1: kaksi porttia (relevant=false)

**Portti A — kilpailusuoritus.** Tulokset, sijoitukset, voitot, mitalit,
sarjatilanteet, joukkuevalinnat, lähtöajat, karsinnat, osallistujalistat,
yksittäisen pelaajan menestys, live-tulokset ja kisaseuranta. Koskee junioreita,
naisia, amatöörejä, para-golfia, arvokilpailuja **ja majoreita**. Ulkomaisen
pelaajan menestys ei kiinnosta, olkoon kilpailu miten arvokas.

Portti A ei sulje pois, jos: **(a)** mukana on suomalaisia, **(b)** kilpailu on
Suomessa, tai **(c)** juttu kertoo liittotasoisesta päätöksestä — säännöistä,
formaatista, isäntäpaikasta, taloudesta, kumppanuuksista. Kohta (c) **ei** kata
kilpailun käytännön pyörittämistä (live-tulospalvelu, aikataulut,
ilmoittautumiset, osallistujalistat) edes arvokilpailussa — tämä rajaus on
pakollinen, koska ilman sitä malli päästi läpi live-tulosseurannan punaisena.
Samasta syystä (c) ei kata **yksittäisen kilpailun peruutusta, siirtoa tai
lyhentämistä** silloinkaan, kun tiedote tulee liitolta: kohta (c) tarkoittaa
pysyvää linjausta, ei yhden kilpailun järjestelyuutista.

**Portti B — arkirutiini.** Ilmoittautumiset ja yksittäiset talkookutsut,
aikataulut, tapahtumatiedotteet ja -ennakot, jälkiraportit, yksittäiset
turnaukset ja muistokilpailut (myös golf-bridge), hyväntekeväisyys- ja
julkkisturnaukset, klubien omat kilpailut, tavanomaiset valmentaja- ja
tuomarikoulutukset, kenttälistaukset, golfmatkailu, lehden uusi numero,
navigaatio, mainokset.

Lajiliitto-välilehdellä portti A on tiukempi: **suomalaispoikkeusta ei ole**,
myös Suomen mitalit karsiutuvat. Golfliittoa kiinnostavat muiden lajien
toimintamallit, ei menestys.

Portti B kattaa myös tapaukset, joissa arkiviestissä **mainitaan** järjestelmä.
Ilmoittautumis-, määräaika-, koulutus- ja aikatauluviesti karsiutuu, vaikka
siinä nimettäisiin uusi järjestelmä tai sen käyttökoulutus: uutinen on määräaika
tai koulutus, ei järjestelmä. Järjestelmän mainitseminen ≠ järjestelmästä
kertominen.

**Portti C — tarkoitusportti.** Portit A ja B tunnistavat aihetyypin (kilpailu,
arkirutiini). Portti C kysyy hyödyn: *saako Golfliitto tästä jotain tehtävää,
tiedettävää tai seurattavaa?* Ilman sitä sisältö joka ei ole kilpailu eikä
hallintoa — lukijalle suunnattu golfsisältö, muistokirjoitus, pelaajakuvaus —
läpäisi molemmat portit ja valui matalan kaatoluokkaan. **Luokittelun
epäonnistuminen ei ole peruste pitää juttu mukana.**

- Golfliitot: karsii pelitekniikka- ja opetusjutut, pelaajan taitojen erittelyn,
  viihde- ja kuriositeettijutut, yksittäisen pelaajan henkilökuvan. Tunnusmerkki:
  juttu kertoo **golfista pelinä tai yksittäisestä pelaajasta**, ei liiton
  toiminnasta. Ei karsi liiton oman toiminnon taustajuttua ("Course Raterien työn
  jäljillä"), nimityksiä, palkintoja eikä juhlavuosia.
- Lajiliitot: karsii yksittäisen seuran oman toiminnan ja pelaajapolut,
  henkilökuvat ja muistokirjoitukset. Ei karsi liittotasoista edunvalvontaa,
  rahoitusta, lakimuutoksia, järjestelmiä eikä toimialadataa.
- **Muistokirjoitus** menee golfliitoissa läpi vihreänä vain kansainvälisesti
  merkittävästä vaikuttajasta (R&A, USGA, EGA, IGF -johtotehtävät tai
  maailmanlaajuisesti tunnettu). Toisen maan kansallisen tason vaikuttaja ei
  riitä. Lajiliitoissa muistokirjoitukset karsiutuvat aina.
- Matalan kaatoluokka on rajattu muotoon "muu relevantiksi jäänyt arkijuttu,
  **joka kertoo liiton toiminnasta**". Rajaamaton kaatoluokka toimi magneettina:
  se muutti "en osaa luokitella" muotoon "pidetään vihreänä".

### Lajiliitot arvioidaan golfin näkökulmasta

Lajiliittojen prompti ei arvioi uutista sen oman lajin kannalta vaan
**siirrettävyytenä golfiin**. Kaikki kolme tasoa on kirjoitettu tästä kulmasta:
punainen = kääntyy golfiin lähes sellaisenaan tai sitoo golfseuroja suoraan,
keltainen = koskee liikunta-alaa laajasti mutta mallia ei voi kopioida (myös
toisen lajin erityispiirteeseen sidotut ratkaisut, esim. jäähallien vuorojako),
vihreä = kertoo vain miten toinen liitto toimii.

Prompti sisältää käsitekartan, joka pakottaa käännöksen: lisenssipelaaja →
jäsen/Golf-ID, seura → golfseura, halli ja kenttävuoro → golfkenttä ja lähtöaika,
juniorileiri → matalan kynnyksen kokeilu. Myös `summary_fi` vaatii kertomaan mitä
**Golfliitto saa tästä**, ei mitä toiselle lajille tapahtui.

### Vaihe 2: kolme tasoa, yksi kysymys kullekin

**Punainen — voiko Golfliitto tehdä tälle jotain?** Kopioida, soveltaa, varautua
tai reagoida. **Vaatii konkretiaa:** valmis palvelu, tehty päätös, julkaistu
tutkimus tai mitattuja tuloksia. Pelkkä aikomus tai visio ei riitä.

Golfliitot: sääntö-/tasoitus- (WHS) /amatööristatusmuutokset ja laajaan
keskusteluun nousevat sääntötulkinnat · julkaistut tutkimukset ja kasvuraportit
(R&A/USGA, terveysvaikutukset) · käytössä olevat kestävän kehityksen innovaatiot
· käytössä olevat kopioitavat digipalvelut ja tekoälyratkaisut · käyttöön otetut
uudet pelimuodot, konseptit ja **inkluusiomallit** · **liittotasoiset**
kumppanuudet ja rahoitusmallit · **merkittävän sponsorin vetäytyminen**
(markkinasignaali, ja siksi kiinnostavampi kuin uuden sponsorin tulo) ·
jäsenkehitysdata syineen · talouskriisi tai skandaali · safeguarding ·
olympiastatus · suurtapahtuman isäntäpaikka **vain Pohjoismaissa** ·
liittotason foorumit ja linjaukset · suomalaisten osallistuminen ja menestys.

Lajiliitot — tässä kysymys ei ole "voiko tehdä jotain" vaan **"voisiko Golfliitto
tehdä saman"**: lakimuutokset ja seuratuki · OKM/veikkausvarat/Olympiakomitean
linjaukset · edunvalvontavoitot (ajokortin ikäpoikkeus) · käytössä olevat
digijärjestelmät ja avoin data · harrastajahankintamallit **joista on tuloksia**
· isot kaupalliset kumppanuudet ja niiden menetys · kohdennetut
rahoituspäätökset · talouskriisit · häirinnän vastaiset palvelut · toimialan
huolidata · lajin asemaa muuttavat kv-päätökset (olympiaohjelma).

**Keltainen — pitääkö tämä tietää, vaikka sitä ei voi soveltaa?** Ei enää
harvinainen välitila, vaan oma selkeä luokkansa.

Aikomus, suunnitelma tai asiantuntijavisio **ilman päätöstä tai tuloksia** ·
ilmiöt ja trendit · **yksittäisen ulkomaisen turnauksen** sponsorointi ja
kumppanuusaineistot (vrt. liittotasoinen kumppanuus = punainen) ·
isäntäpaikkapäätökset muualla maailmassa · **inkluusiokärkinen kilpailu-uutinen,
jossa ei ole uutta mallia** · IT-häiriöt ja tietoturvatapaukset ·
urheiluoikeudelliset tapaukset.

**Vihreä — hyvä tiedoksi, ei vaadi toimenpiteitä.**

Nimitykset ja kv-luottamustehtävät, palkinnot, juhlavuodet · pienet käytännön
työkalut ja lomakkeet · **vapaaehtois- ja koulutusohjelmat** (yksittäiset
talkookutsut sen sijaan karsiutuvat portissa B) · rutiinikampanjat ja
hinnoittelu · liiton kannanotto yksittäiseen kv-asiaan · kevyet henkilö- ja
taustajutut · kumppanien luettelointi · muu relevantiksi jäänyt arkijuttu.

### Inkluusio kulkee kaikkien kolmen tason läpi

Tämä on setin hankalin raja, joten se on kirjattu erikseen: käyttöön otettu
**inkluusiomalli on punainen** ("Sveitsi otti G4D-kilpailun mestaruuskilpailujen
rinnalle"), **inkluusiokärkinen kilpailu-uutinen keltainen** ("Vammaisgolfin EM
käynnistyi – inkluusio keskiössä"), **para-golfin tulokset pois** kuten muutkin
ulkomaiset tulokset.

Neljäs ja kavalin tapaus: **matalan kynnyksen MALLI on punainen, yksittäisen
tapahtuman ENNAKKO on pois** (portti B) — vaikka ennakko luettelisi täsmälleen
samat hyvät ominaisuudet: matala kynnys, edullinen osallistumismaksu, rento
ilmapiiri, naisten ja aloittelijoiden houkuttelu. Punainen vaatii, että juttu
kuvaa mallin: kuka otti käyttöön ja miten se toimii. Kalibroitu esimerkki
poissuljetusta: "Dr Irena Eris Ladies Golf Tour saapuu Tokary Golf Clubille"
(7/2026 malli nosti tämän punaiseksi, koska ingressi korosti matalaa kynnystä).

**Kalibrointitapa:** kun käyttäjä sanoo "tämä oli väärässä laatikossa", lisää
kyseinen otsikko esimerkkinä oikean tason listaan promptissa. Poista samalla
ristiriitaiset vanhat säännöt. Älä kirjoita samaa sääntöä kahteen tasoon —
jos raja on aito, kirjoita se **vastakkainasetteluna** ("liittotasoinen =
punainen, turnaustason = keltainen"), ei kahtena erillisenä sääntönä.

## Arkkitehtuuri

```
sources.yaml       lähteet (RSS → HTML → Google News, ensimmäinen osuma voittaa)
src/config.py      polut, .env, vakiot
src/sources.py     YAML-lataus, Google News -lokaalit per kieli
src/fetch.py       rinnakkainen keruu, 15 s timeout, alidomain-suodatus
src/store.py       SQLite: dedup, statukset, ikäsäännöt, migraatiot
src/analyze.py     Gemini structured output, erä-checkpointit, kiintiösulake
src/report.py      HTML-raportti (Suomi Golf -brändi, Racing Green, Montserrat)
src/encrypt.py     AES-GCM-salaus web-julkaisuun
src/emailer.py     valinnainen SMTP (odottaa tunnuksia)
src/main.py        pääohjelma
run.sh             ajo + salaus + git push GitHub Pagesiin
deploy/            launchd-ajastus (ti + pe klo 10:15)
```

## Lähdesäännöt (sources.yaml)

- **Vain viralliset liitot** golfliitot-välilehdellä. Ei medioita, ei
  kolmansien osapuolten uutisointia.
- Google News `site:`-haku kattaa alidomainit → `fetch.py` suodattaa ne pois.
- Vapaa `google_news_query` vain kun domain ei ole GN-indeksissä. Varo:
  vapaa hakulause tuo muiden medioiden juttuja (aiheutti Cisco-duplikaatit).
- Suora RSS on aina paras: oikeat päivämäärät ja linkit. Google News antaa
  joskus vanhalle jutulle tuoreen päiväyksen. Tarkista silti, että syötteessä on
  `<link>`: esim. swissgolf.ch/rss antaa vain guidin, joten artikkeliin ei pääse.
- **Tarkista aina HTML-lähteen päivämääräselektori.** Päivämäärätön artikkeli
  tulkitaan tuoreeksi, joten osumaton selektori nostaa vanhat jutut raporttiin
  ikuisesti tuoreina. Näin kävi Islannille, Italialle ja Tanskalle (7/2026).
- Templaattisivustot (Knockout, Vue) näyttävät toimivilta: kortteja löytyy, mutta
  ne ovat tyhjiä runkoja, joissa linkki on `#!` ja otsikoksi valikoituu CMS:n
  painike ("Edit Article"). `fetch.py` hylkää nyt listaussivulle itseensä
  osoittavat linkit — jos lähde tuottaa outoja otsikoita, epäile templaattia.
- **Nollalähde ei ole aina rikki.** Erottele: "N liian vanhaa" = lähde toimii,
  julkaisee harvoin (esim. STERF, SGF, OKM). "muun median juttua" tai
  "puutteellista" = reitti on väärä ja se kannattaa korjata.

## Julkaisu

`run.sh` salaa raportin (`REPORT_PASSWORD` .env:stä) ja pushaa `docs/index.html`.
Jos salaus epäonnistuu, julkaisu ohitetaan — salaamatonta ei koskaan pushata.
Osoite: https://nulvador.github.io/mediaseuranta/

## Muuta

- `.env` ei koskaan versionhallintaan (API-avain, salasana, SMTP).
- Testit: `python -m pytest tests/ -q`
- Kieli: kaikki käyttäjälle näkyvä ja kommentit suomeksi.
