# Golf Media Monitor — käyttöohje viestintäpäällikölle

Tämä työkalu kerää kahdesti viikossa uutiset ulkomaisilta golfliitoilta,
suomalaisilta lajiliitoilta ja suomalaisesta mediasta, suodattaa Golfliiton
kannalta kiinnostavat, suomentaa ne ja julkaisee salatun raportin verkkoon.

**Raportti:** https://mediaseuranta.vercel.app
**Salasana:** kysy edelliseltä ylläpitäjältä (ei ole kirjattu tähän tiedostoon)

Raportti päivittyy automaattisesti **tiistaisin ja perjantaisin**. Sinun ei
tarvitse tehdä mitään — avaa vain linkki.

---

## 1. Raportin lukeminen

Kolme välilehteä: **Golfliitot maailmalla**, **Suomalaiset lajiliitot** ja
**Suomalainen media**.

Kahdella ensimmäisellä värit vastaavat kysymykseen *voiko Golfliitto tehdä
tälle jotain:*

| Väri | Merkitys |
|---|---|
| 🔴 Punainen | Sääntö- tai tasoitusmuutos, julkaistu tutkimus, käyttöön otettu malli tai digipalvelu, liittotason kumppanuus tai rahoitus, kriisi, safeguarding, suomalaisten osallistuminen ja menestys |
| 🟡 Keltainen | Pitää tietää, vaikka ei voi soveltaa: aikomus ilman päätöstä, ilmiöt ja trendit, isäntäpaikkapäätökset muualla maailmassa |
| 🟢 Vihreä | Hyvä tietää: nimitykset, palkinnot, juhlavuodet, arkijutut |

**Media-välilehdellä kysymys on toinen:** *puhutaanko meistä, ja pitääkö
reagoida?* Siellä 🔴 koskee Suomen golfin rakennetta, päätöstä tai mainetta,
🟡 suomalaista pelaajaa, kotimaista kilpailua ja lajin näkyvyyttä, 🟢 muuta
hyvä tietää -tavaraa.

Kilpailutulokset ja sijoitukset karsiutuvat liittovälilehdiltä tarkoituksella —
myös majoreista, jos suomalaisia ei ole mukana.

Suodattimet: prioriteetti, teema, maa, vapaa haku ja "näytä vain uudet".
Artikkeli näkyy raportissa **7 päivää** julkaisustaan (tai havaitsemisestaan,
jos julkaisupäivää ei tiedetä).

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

Tämä on normaalia. Korjaus tehdään kahdessa vaiheessa: ensin napista raportissa,
ja vasta kun korjauksia on kertynyt, promptiin.

**Vaihe 1 — korjaa suoraan raportissa.** Jokaisen kortin alalaidassa on neljä
nappia:

| Nappi | Mitä tekee |
|---|---|
| 🔴 🟡 🟢 | Vaihtaa jutun prioriteetin. Kortti siirtyy heti oikealle paikalle. |
| ✕ | "Ei kuulu katsaukseen." Kortti himmenee ja valuu listan loppuun. |
| peru | Poistaa korjauksen. |

Jos portti karsi jutun jonka olisi pitänyt olla mukana, avaa **"Näytä kaikki
löydetyt uutiset"** ja paina rivin "+ katsaukseen".

Kirjoita napin viereen lyhyt perustelu jos ehdit ("yksittäinen turnaus", "vain
aikomus, ei päätöstä"). Se on myöhemmin tärkeämpi kuin otsikko: otsikko kertoo
mikä meni väärin, perustelu kertoo miksi — ja vain siitä syntyy uusi sääntö.

Korjaus näkyy heti ja säilyy **tässä selaimessa**. Se ei vielä siirry
järjestelmään: avaa raportin lopussa **"Omat korjaukset"**, paina *Kopioi
leikepöydälle* ja anna teksti Claudelle:

> Golf Media Monitor -projektissa (github.com/Suomen-Golfliitto-ry/mediaseuranta) tein
> raportissa prioriteettikorjauksia. Tässä korjaus-JSON: [liitä]. Vie ne kantaan
> ja generoi raportti uudelleen.

Tämän jälkeen korjaus pitää paikkansa myös seuraavissa ajoissa. **Prompti ei
muutu vielä tässä vaiheessa** — korjaus koskee vain sitä yhtä juttua.

**Vaihe 2 — päivitä prompti, kun sama virhe toistuu.** Kun huomaat korjaavasi
samaa asiaa kolmatta kertaa, tai kun korjauksia on kertynyt parikymmentä, kysy:

> Golf Media Monitor -projektissa (github.com/Suomen-Golfliitto-ry/mediaseuranta) uutisten
> priorisointi menee toistuvasti väärin. Lue projektin CLAUDE.md, jossa on
> priorisointisäännöt, ja aja `python -m src.main --list-corrections` nähdäksesi
> tekemäni korjaukset. Päivitä src/analyze.py:n promptit ja CLAUDE.md.

Promptimuutos vaikuttaa **uusiin** uutisiin automaattisesti seuraavassa ajossa.
Jo kerätyissä jutuissa se näkyy vasta kun ne uudelleenanalysoidaan — sen Claude
osaa tehdä yhdelle välilehdelle kerrallaan.

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
julkisille repoille, Vercelin hobby-taso ilmainen. Julkaisu on Vercelissä
(osoite mediaseuranta.vercel.app), ei GitHub Pagesissa.

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

- Osa lähteistä haetaan Google Newsin kautta, koska sivustolta ei saa suoraa
  syötettä (mm. Scottish Golf, The Open, USGA ja useat lajiliitot). Se on
  epävarmempaa: päivämäärä voi olla väärä ja linkki on uudelleenohjaus. Ruotsi
  ja Hollanti luetaan nykyään suoraan RSS-syötteestä, Norja sivun HTML:stä ja
  R&A sivukartasta.
- Google News ei anna artikkeleille kuvia, joten korteissa on golfkenttä-kuvitus.
- Tekoäly tekee joskus luokitteluvirheitä. Korjaus tapahtuu kohdan 2 ohjeella.
- Sähköpostijakelu on koodissa valmiina mutta käyttämättä — vaatii liiton
  SMTP-tunnukset. Claude osaa ottaa sen käyttöön pyydettäessä.
