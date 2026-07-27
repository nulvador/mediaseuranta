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

Perusperiaate: **substanssi = punainen, arki = pois tai vihreä.** Keltainen on
harvinainen välitila. Epäröidessä valitse alempi taso tai jätä pois.

### Punainen (korkea) — aitoa substanssia

Golfliitot: sääntö-/tasoitus- (WHS) /amatööristatusmuutokset · R&A/USGA-tutkimukset
ja kasvuraportit · golfin terveystutkimukset · kestävän kehityksen innovaatiot
(vedenkäyttö, energia, nurmilajikkeet, biodiversiteetti) · kopioitavat
digipalvelut ja tekoälyratkaisut · merkittävät kumppanuudet ja rahoitusmallit ·
jäsenkehitysdata syineen · liiton talouskriisi tai skandaali · safeguarding ·
olympiastatus · suurtapahtuman isäntäpaikka **vain Pohjoismaissa** · uudet
pelimuodot ja konseptit.

Lajiliitot: lakimuutokset ja seuratuki · OKM/veikkausvarat/Olympiakomitean
linjaukset · edunvalvontavoitot (esim. ajokortin ikäpoikkeus) · yhteiset
digijärjestelmät ja avoin data · harrastajahankintamallit **joista on tuloksia** ·
isot kaupalliset kumppanuudet · talouskriisit · häirinnän vastaiset palvelut ·
toimialan huolidata (vapaaehtoisten romahdus).

### Keltainen (keskitaso) — harvinainen

Ilmiöjutut ilman suoraa hyötyä · IT-häiriöt ja tietoturvatapaukset ·
urheiluoikeudelliset tapaukset · isäntäpaikkapäätökset muualla maailmassa.

### Vihreä (matala)

Nimitykset, palkinnot, juhlavuodet, relevantiksi jääneet arkijutut,
Suomi-kytköksiset kilpauutiset.

### Pois kokonaan (relevant=false)

Kilpailutulokset, sarjatilanteet, lähtöajat, karsinnat, osallistujalistat,
joukkuevalinnat (myös Suomen mitalit) · tapahtumatiedotteet, -ennakot ja
kisaseuranta · kilpailun pelaaminen tai esittely ("154. Open pelataan
Royal Birkdalessa") · yksittäiset turnaukset ja muistokilpailut · seurojen
pelaajarekry, leirit, harjoitusvuorot · tavanomaiset valmentaja- ja
tuomarikoulutukset · ilmoittautumiset ja järjestäjähaut · kenttälistaukset ja
golfmatkailu · lehden uusi numero · navigaatio ja mainokset.

**Kalibrointitapa:** kun käyttäjä sanoo "tämä oli väärässä laatikossa", lisää
kyseinen otsikko esimerkkinä oikean tason listaan promptissa. Poista samalla
ristiriitaiset vanhat säännöt — päällekkäisyydet sekoittavat mallia.

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
  joskus vanhalle jutulle tuoreen päiväyksen.

## Julkaisu

`run.sh` salaa raportin (`REPORT_PASSWORD` .env:stä) ja pushaa `docs/index.html`.
Jos salaus epäonnistuu, julkaisu ohitetaan — salaamatonta ei koskaan pushata.
Osoite: https://nulvador.github.io/mediaseuranta/

## Muuta

- `.env` ei koskaan versionhallintaan (API-avain, salasana, SMTP).
- Testit: `python -m pytest tests/ -q`
- Kieli: kaikki käyttäjälle näkyvä ja kommentit suomeksi.
