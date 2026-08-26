# Golf Media Monitor — käyttöohje viestintäpäällikölle

Tämä työkalu kerää kahdesti viikossa uutiset ulkomaisilta golfliitoilta ja
suomalaisilta lajiliitoilta, suodattaa Golfliiton kannalta kiinnostavat,
suomentaa ne ja julkaisee salatun raportin verkkoon.

**Raportti:** https://mediaseuranta.vercel.app
**Salasana:** kysy edelliseltä ylläpitäjältä (ei ole kirjattu tähän tiedostoon)

Raportti päivittyy automaattisesti **tiistaisin ja perjantaisin**. Sinun ei
tarvitse tehdä mitään — avaa vain linkki.

---

## 1. Raportin lukeminen

Kaksi välilehteä: **Golfliitot maailmalla** ja **Suomalaiset lajiliitot**.

| Väri | Merkitys |
|---|---|
| 🔴 Punainen | Aitoa substanssia: sääntömuutos, tutkimus, iso kumppanuus, kriisi, kopioitava malli, majorit ja kilpailut joissa suomalaisia |
| 🟡 Keltainen | Kiinnostava ilmiö, ei suoraan sovellettavissa |
| 🟢 Vihreä | Hyvä tietää: nimitykset, palkinnot, arkijutut |

Suodattimet: prioriteetti, teema, maa, vapaa haku ja "näytä vain uudet".
Artikkeli näkyy raportissa **5 päivää** julkaisustaan.

**Tärkeää:** käännökset ja tiivistelmät ovat tekoälyn tekemiä luonnoksia.
Tarkista faktat alkuperäislähteestä ennen kuin käytät sisältöä julkisesti.

---

## 2. Kun jokin menee pieleen

Kaikki ylläpito onnistuu **Clauden avulla** — sinun ei tarvitse osata koodata.
Avaa Claude, liitä alla oleva kehote ja kerro mitä havaitsit.

### Raportti ei ole päivittynyt

1. Mene osoitteeseen https://github.com/Suomen-Golfliitto-ry/mediaseuranta
2. Valitse ylhäältä **Actions** → **Mediaseuranta** (vasemmasta reunasta)
3. Näet listan ajoista. Vihreä ✅ = onnistui, punainen ❌ = epäonnistui.
4. Voit käynnistää ajon käsin: valitse **Run workflow** → **Run workflow**.

Jos ajo on punainen, klikkaa se auki, kopioi virheteksti ja kysy Claudelta:

> Golf Media Monitor -projektin (github.com/Suomen-Golfliitto-ry/mediaseuranta) GitHub
> Actions -ajo epäonnistui. Tässä virheilmoitus: [liitä teksti]. Mikä on vialla
> ja miten korjaan sen?

### Uutiset ovat vääriä tai epäkiinnostavia

Tämä on normaalia ja korjattavissa. Ota kuvakaappaus raportista ja kysy:

> Golf Media Monitor -projektissa (github.com/Suomen-Golfliitto-ry/mediaseuranta) uutisten
> priorisointi meni väärin. Lue projektin CLAUDE.md, jossa on priorisointisäännöt.
> Nämä uutiset olivat väärässä laatikossa: [kerro otsikko ja mikä väri sen
> kuuluisi olla]. Päivitä src/analyze.py:n promptit ja CLAUDE.md.

Muutos vaikuttaa **uusiin** uutisiin automaattisesti seuraavassa ajossa.

### Jokin lähde on hiljentynyt

Raportin alalaidassa on **"Lähteiden tila viimeisimmässä ajossa"**. Jos jokin
liitto näyttää 0 artikkelia monta ajoa peräkkäin ja syy on muu kuin
"liian vanhaa", lähde on todennäköisesti rikki (osoite muuttunut). Kysy:

> Golf Media Monitor -projektin lähde [nimi] ei tuota artikkeleita. Selvitä
> liiton nykyinen uutissivu tai RSS-syöte ja korjaa sources.yaml.

### Haluat lisätä uuden lähteen

> Lisää Golf Media Monitor -projektiin uusi lähde: [liiton nimi ja verkko-osoite].
> Noudata sources.yaml:n rakennetta ja CLAUDE.md:n lähdesääntöjä.

---

## 3. Mitä pitää muistaa ylläpidossa

**Gemini-tekoälyn ilmaiskiintiö on noin 20 kutsua vuorokaudessa.** Normaali ajo
käyttää muutaman. Älä koskaan pyydä Claudea ajamaan `--reanalyze` koko
tietokannalle — se syö koko päivän kiintiön kerralla. Tämä on kirjattu myös
CLAUDE.md-tiedostoon, jonka Claude lukee automaattisesti.

**Salasanat ja avaimet** ovat GitHubin salaisuuksissa (Settings → Secrets and
variables → Actions):

- `GEMINI_API_KEY` — tekoälyn avain (aistudio.google.com/apikey)
- `REPORT_PASSWORD` — raportin salasana

Jos avain lakkaa toimimasta, luo uusi Google AI Studiossa ja päivitä se
GitHubin salaisuuksiin. Salasanan vaihto: päivitä `REPORT_PASSWORD` ja aja
työnkulku käsin — uusi salasana on voimassa seuraavasta raportista.

**Kustannukset:** ei mitään. Gemini ilmaistasolla, GitHub Actions ilmainen
julkisille repoille, GitHub Pages ilmainen.

---

## 4. Jos tarvitset kehittäjää

Projekti on tavallista Python-koodia ja hyvin dokumentoitu:

- `CLAUDE.md` — säännöt ja arkkitehtuuri, jonka Claude lukee automaattisesti
- `README.md` — tekninen kuvaus
- `sources.yaml` — lähteet (yksi lohko per liitto)
- `src/analyze.py` — tekoälyn ohjeet eli priorisointisäännöt
- `src/report.py` — raportin ulkoasu (Suomi Golf -brändi)

Kuka tahansa Pythonia osaava — tai Claude Code — pystyy jatkamaan tästä.

---

## 5. Tiedossa olevat rajoitteet

- Osa liitoista (Ruotsi, Norja, Hollanti, R&A) on JS-sivustoja, joita ei voi
  lukea suoraan. Ne haetaan Google Newsin kautta, mikä on epävarmempaa.
- Google News ei anna artikkeleille kuvia, joten korteissa on golfkenttä-kuvitus.
- Tekoäly tekee joskus luokitteluvirheitä. Korjaus tapahtuu kohdan 2 ohjeella.
- Sähköpostijakelu on koodissa valmiina mutta käyttämättä — vaatii liiton
  SMTP-tunnukset. Claude osaa ottaa sen käyttöön pyydettäessä.
