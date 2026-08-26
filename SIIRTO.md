# Mediakatsauksen julkaisu — Vercel

Julkaisun tila ja ylläpito-ohje. Import Verceliin on **tehty 26.8.2026**, ja
Vercel on nyt raportin virallinen osoite.

- **Osoite: https://mediaseuranta.vercel.app**
- Repo: `github.com/Suomen-Golfliitto-ry/mediaseuranta`
- Julkaistava tiedosto: **`docs/index.html`** (n. 280 kt)

## Tila

- Repo siirretty henkilökohtaiselta tililtä organisaatioon
  `Suomen-Golfliitto-ry` (25.8.2026).
- Ajo siirretty pilveen: **GitHub Actions**
  (`.github/workflows/monitor.yml`), ti + pe. Ei riipu kenenkään koneesta.
  Avaimet ovat GitHubin repo-salaisuuksina (`GEMINI_API_KEY`,
  `REPORT_PASSWORD`).
- Vercel-import tehty ja todettu toimivaksi: Vercel ja vanha Pages-osoite
  palvelivat tavulleen samaa tiedostoa.
- **Tekemättä: GitHub Pages pitää ottaa pois käytöstä** (ks. alla).

Ketju on: Actions-ajo → commit `docs/index.html` → Vercel deploy. Vercel on
pelkkä staattinen tiedostojakelu; keruu, Gemini-analyysi ja SQLite-kanta eivät
kuulu sille lainkaan.

## Vercel-projektin asetukset

| Asetus | Arvo |
|---|---|
| Framework Preset | **Other** |
| Root Directory | **`docs`** |
| Build Command | *tyhjä* |
| Install Command | *tyhjä* |
| Output Directory | *tyhjä* |
| Environment Variables | *ei mitään* |
| Production Branch | `main` |

GitHub App -oikeudet on rajattu: **Only select repositories** → `mediaseuranta`.
Älä laajenna "All repositories" -tasolle — Vercelin ei tarvitse nähdä liiton
muita repoja.

## Mitä julkaistaan

Yksi tiedosto: `docs/index.html`.

- Täysin omavarainen: ei yhtään ulkoista `src`- tai `href`-viittausta, ei
  fontteja, ei CDN:ää, ei API-kutsuja.
- Sisältö on **AES-256-GCM-salattu**. Avain johdetaan salasanasta PBKDF2:lla
  (600 000 kierrosta) ja purku tapahtuu selaimessa WebCryptolla. Salasana ei
  siis kulje palvelimen kautta eikä ole palautettavissa tiedostosta.
- Sivulla on `<meta name="robots" content="noindex, nofollow">`.

## GitHub Pagesin lopetus

Pages jäi Vercelin rinnalle rinnakkaiseksi julkaisuksi. Se lopetetaan, koska
Vercel on pääasiallinen hostaus:

**Settings → Pages → Source: None** repossa `Suomen-Golfliitto-ry/mediaseuranta`.

Kaksi asiaa, jotka on hyvä tietää ennen kuin painaa:

1. **`docs/`-kansiota ei poisteta.** Se on Vercelin Root Directory, ei Pagesin
   jäänne. Pagesin lopetus on pelkkä GitHubin asetus, ei repomuutos — mikään
   koodissa ei viittaa Pagesiin.
2. **Vanha osoite kuolee.** `suomen-golfliitto-ry.github.io/mediaseuranta`
   lakkaa toimimasta. Jos osoite on jaettu jollekulle, kerro uusi. Käyttöohje
   (`KAYTTOOHJE.md`) ja `CLAUDE.md` osoittavat jo Verceliin.

## Toimivuuden testi

1. Osoite avautuu salasanakyselyyn ("🔒 Golfliiton mediakatsaus").
2. Salasanalla raportti avautuu ja välilehdet (golfliitot / lajiliitot / media)
   toimivat.

Salasana: pyydä viestintäpäälliköltä. Sitä ei ole tässä dokumentissa eikä
Vercelissä.

Muuta testattavaa ei ole — sivu on täysin staattinen eikä kutsu mitään ulkoista.

## Kaksi asiaa, jotka tarvitsevat vielä kannanoton

**1. Vercelin preview-deploymentit ovat oletuksena julkisia osoitteita.**
Sivun oma salasanasuojaus riittää suojaksi, mutta jos halutaan vyö ja henkselit,
Deployment Protection kannattaa kytkeä päälle.
*Älä korvaa sivun omaa salausta Vercelin password protectionilla:* se on
tilaukseen sidottu ominaisuus, sivun oma salaus ei ole. Jos tilaus päättyy,
salaus jää voimaan.

**2. Kokeilutilauksen sopimustilanne (DPA / henkilötietojen käsittely).**
Sisältö siirtyy Vercelin palvelimille ja CDN:ään. Riski on tässä pieni —
aineisto on julkisista uutisista koostettu ja siirtyy salattuna — mutta Vercel
näkee kävijöiden IP-osoitteet ja käyttötiedot. Tämä on syytä olla tiedossa ennen
kuin osoite jaetaan liiton väelle.

## Repon näkyvyys — este poistui

Repo on **julkinen**, eli `CLAUDE.md`, `sources.yaml` ja `src/analyze.py` — koko
mediaseurannan priorisointilogiikka ja kalibrointihistoria — ovat kenen tahansa
luettavissa. Salattu raportti on suojattu, lähdekoodi ei.

Kun Pages on pois päältä, reposta voi tehdä yksityisen ja sivu toimii silti:
**yksityinen repo + GitHub Pages olisi vaatinut maksullisen GitHub Team -tason,
Vercel ei.** Aiempi valinta oli "yksityinen repo ja vain Vercel" tai "julkinen
repo ja Pages rinnalla" — Pagesin lopetus tekee ensimmäisestä mahdollisen.
Huomaa, että yksityinen repo ei vaikuta Actions-ajoon eikä Vercelin deployhin.

## Yhteystiedot

Raportin sisältö, ajo ja salasana: Nuutti Laitila, viestintä
(nuutti.laitila@golf.fi)
