# Golf Media Monitor v2

Suomen Golfliiton mediamonitorointi: kerää uutiset ~34 lähteestä (ulkomaiset
golfliitot + suomalaiset lajiliitot), suodattaa ja suomentaa ne Geminillä ja
tuottaa selattavan HTML-raportin. Valinnaisesti lähettää raportin sähköpostilla.

## Pikaohje

```bash
cp .env.example .env        # täytä vähintään GEMINI_API_KEY
./run.sh                    # keruu + analyysi + raportti + (sähköposti)
```

Raportti: `output/report.html`. Kaikki data: `data/monitor.db` (SQLite).

### Vanhan projektin datan tuonti

```bash
python -m src.main --import-json /polku/vanhaan/articles.json
```

Tuo vanhat artikkelit tietokantaan, jolloin dedup tunnistaa ne eikä niitä
analysoida uudelleen. Suomennetut merkitään valmiiksi analysoiduiksi.

### Muut ajotavat

```bash
python -m src.main --skip-analysis   # vain keruu (artikkelit jäävät jonoon)
python -m src.main --report-only     # generoi raportti nykyisestä datasta
python -m src.main --no-email        # ilman sähköpostia
```

## Miten v2 eroaa vanhasta

**Haut eivät enää lopu kesken.** Keruu tehdään rinnakkain (8 säiettä,
15 s timeout per pyyntö), joten yksi hidas lähde ei viivästytä muita. Raakadata
tallennetaan tietokantaan heti keruun jälkeen ja jokainen analyysierä
tallennetaan heti valmistuttuaan. Jos ajo keskeytyy, seuraava ajo jatkaa
siitä mihin jäätiin — mitään ei menetetä eikä analysoida kahdesti.

**Käännökset paranivat kolmella muutoksella.** Erät pienenivät 60:stä 12:een,
jolloin vastaukset eivät katkea. Gemini pakotetaan palauttamaan tarkasti
skeeman mukaista JSON:ia (structured output), joten regex-parsinta ja siitä
seuranneet jumit poistuivat kokonaan. Promptit pyytävät toimituksellista
suomea ja antavat ingressin kontekstiksi pelkän otsikon sijaan.

**Lähteet ovat konfiguraatiota, eivät koodia.** `sources.yaml` määrittelee
jokaiselle lähteelle 1–3 hakutapaa, joita kokeillaan järjestyksessä:
suora RSS → HTML-listaussivu → Google News -haku. Uusi lähde on uusi lohko
YAML-tiedostoon.

**Lähdeterveys näkyy.** Jokainen ajo raportoi lähde kerrallaan, montako
artikkelia saatiin ja millä tavalla. Hiljentynyt lähde (rikkoutunut selektori,
muuttunut feed) näkyy heti raportin "Lähteiden tila" -osiossa ja lokissa,
eikä huku hiljaisuuteen.

**SQLite JSON-tiedostojen sijaan.** Dedup, tila-checkpointit, ajohistoria ja
myöhempi trendiseuranta ilman erillisiä seen_articles/articles-tiedostoja,
jotka kasvoivat rajatta ja saattoivat korruptoitua.

## Rakenne

```
sources.yaml       lähteet (muokkaa tätä, älä koodia)
src/config.py      polut, ympäristömuuttujat, vakiot
src/sources.py     sources.yaml-lataus
src/fetch.py       rinnakkainen keruu (RSS/HTML/Google News)
src/store.py       SQLite: dedup, checkpointit, migraatio
src/analyze.py     Gemini structured output, erä-checkpointit
src/report.py      HTML-raportti (tabit, suodattimet, haku, lähdeterveys)
src/emailer.py     valinnainen SMTP-lähetys
src/main.py        pääohjelma
tests/             yksikkötestit (python -m pytest tests/ -q)
```

## Ajastus myöhemmin

Kun ajot todetaan vakaiksi, macOS:llä kannattaa käyttää `launchd`:tä cronin
sijaan — cron ei aja, jos kone nukkuu, launchd ajaa heräämisen jälkeen.
Esimerkki (ti+pe klo 6): tallenna `~/Library/LaunchAgents/fi.golf.monitor.plist`,
jossa `StartCalendarInterval` sisältää `Weekday 2` ja `Weekday 5`, `Hour 6`,
ja ohjelmaksi `run.sh` ympäristömuuttujalla `NO_OPEN=1`.

## Huomioita

- AI-käännökset ja -tiivistelmät ovat luonnoksia. Tarkista faktat, nimet ja
  luvut alkuperäislähteestä ennen kuin sisältöä käytetään julkisesti.
- `sources.yaml`-lähteiden URL-osoitteet ja selektorit kannattaa todentaa
  ensimmäisellä ajolla lähdeterveysraportista: jos lähde antaa 0 artikkelia
  kaikilla tavoilla, tarkista URL selaimessa ja päivitä YAML.
- Gemini free tier voi hetkittäin palauttaa 429/503-virheitä. Epäonnistuneet
  erät jäävät jonoon ja analysoidaan automaattisesti seuraavassa ajossa.
- Ensimmäisen git-commitin jälkeen: commitoi jatkossa muutokset erikseen
  (`sources.yaml`-muutokset omina commiteina, niin lähdehistoria säilyy).
