# Golf Media Monitor — ohjeet Claudelle

Suomen Golfliiton viestintäpäällikön mediaseuranta. Kerää uutiset golfliitoilta
ja suomalaisilta lajiliitoilta, suodattaa ja suomentaa ne Geminillä, julkaisee
salatun HTML-raportin GitHub Pagesiin.

## Kriittiset rajoitteet

**Gemini free tier: ~20 kutsua/vrk.** Kutsut = analysoitavat artikkelit /
BATCH_SIZE (50). Kiintiö nollautuu n. klo 10 Suomen aikaa.

- ÄLÄ ehdota `--reanalyze` koko kannalle. Se on satoja artikkeleita = koko
  päiväkiintiö. Käytä korkeintaan yhtä välilehteä: `--reanalyze urheilu_liitot`.
- Promptin muutokset vaikuttavat uusiin artikkeleihin automaattisesti.
  Vanhoja ei tarvitse ajaa uusiksi.
- Ilman Geminiä toimivat: `--report-only`, `--skip-analysis`, `--restore`,
  `--purge`, lähdekorjaukset, ulkoasumuutokset. Suosi näitä kehityksessä.

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

## Ikäsäännöt

- **Näkyvyys 5 päivää** (`REPORT_DAYS`) artikkelin julkaisusta — tai
  havaitsemisesta, jos julkaisupäivää ei tiedetä. Tätä vanhemmat poistuvat.
- Yli 5 pv vanhoja **ei analysoida** lainkaan (`expire_old_pending`).
- `RETENTION_DAYS` (90) pitää dedup-historian, jottei vanha uutinen palaa uutena.

## Priorisointisäännöt (src/analyze.py)

Arviointi on kaksivaiheinen, eikä vaiheita saa sekoittaa: **kohta 1 karsii**
kahdella portilla, **kohta 5 asettaa lopuille tason** kolmella kysymyksellä.
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

**Portti B — arkirutiini.** Ilmoittautumiset ja yksittäiset talkookutsut,
aikataulut, tapahtumatiedotteet ja -ennakot, jälkiraportit, yksittäiset
turnaukset ja muistokilpailut (myös golf-bridge), klubien omat kilpailut,
tavanomaiset valmentaja- ja tuomarikoulutukset, kenttälistaukset, golfmatkailu,
lehden uusi numero, navigaatio, mainokset.

Lajiliitto-välilehdellä portti A on tiukempi: **suomalaispoikkeusta ei ole**,
myös Suomen mitalit karsiutuvat. Golfliittoa kiinnostavat muiden lajien
toimintamallit, ei menestys.

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

Lajiliitot: lakimuutokset ja seuratuki · OKM/veikkausvarat/Olympiakomitean
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
