# Mediakatsauksen julkaisu Verceliin

Ohje digipäällikölle. Tavoite: julkaista mediakatsausraportti Vercelissä.

Repo on jo siirretty liiton organisaatioon, joten tarvittava työ on yksi import
Vercelissä. **Ei buildia, ei riippuvuuksia, ei ympäristömuuttujia.**

- Repo: `github.com/Suomen-Golfliitto-ry/mediaseuranta`
- Nykyinen osoite (GitHub Pages): https://suomen-golfliitto-ry.github.io/mediaseuranta/
- Julkaistava tiedosto: **`docs/index.html`** (n. 270 kt)

## Mikä on jo tehty

- Repo siirretty henkilökohtaiselta tililtä organisaatioon
  `Suomen-Golfliitto-ry` (25.8.2026).
- Paikallinen remote päivitetty ja push-oikeus varmistettu toimivaksi.
- GitHub Pages toimii uudessa osoitteessa.

## Mitä julkaistaan

Yksi tiedosto: `docs/index.html`.

- Täysin omavarainen: ei yhtään ulkoista `src`- tai `href`-viittausta, ei
  fontteja, ei CDN:ää, ei API-kutsuja.
- Sisältö on **AES-256-GCM-salattu**. Avain johdetaan salasanasta PBKDF2:lla
  (600 000 kierrosta) ja purku tapahtuu selaimessa WebCryptolla. Salasana ei
  siis kulje palvelimen kautta eikä ole palautettavissa tiedostosta.
- Sivulla on `<meta name="robots" content="noindex, nofollow">`.

Muu projekti (uutisten keruu, Gemini-analyysi, SQLite-kanta) ajetaan
viestintäpäällikön koneella launchd-ajastuksella tiistaisin ja perjantaisin klo
10:15, ja se pushaa valmiin raportin repoon. **Se ei kuulu Verceliin lainkaan.**
Vercel on pelkkä staattinen tiedostojakelu.

## Tee tämä — import Verceliin

Olet organisaation owner, joten hyväksyntäkierroksia ei tarvita.

1. Vercel → **Add New → Project → Import Git Repository**.
2. Jos organisaation repot eivät näy listassa: **Adjust GitHub App Permissions**
   → valitse organisaatio `Suomen-Golfliitto-ry` → **Only select repositories** →
   `mediaseuranta` → **Install**.
   Älä valitse "All repositories" — Vercelin ei tarvitse nähdä liiton muita
   repoja.
3. Projektin asetukset:

   | Asetus | Arvo |
   |---|---|
   | Framework Preset | **Other** |
   | Root Directory | **`docs`** |
   | Build Command | *tyhjä* |
   | Install Command | *tyhjä* |
   | Output Directory | *tyhjä* |
   | Environment Variables | *ei mitään* |

4. **Deploy.** Production Branch on `main` (oletus).

Tämän jälkeen jokainen ajo (ti ja pe klo 10:15) julkaisee raportin
automaattisesti. Ajoskriptiin ei tarvita muutoksia.

## Toimivuuden testi

1. Vercelin antama osoite avautuu salasanakyselyyn
   ("🔒 Golfliiton mediakatsaus").
2. Salasanalla raportti avautuu ja välilehdet (golfliitot / lajiliitot / media)
   toimivat.

Salasana: pyydä viestintäpäälliköltä. Sitä ei ole tässä dokumentissa eikä
Vercelissä.

Muuta testattavaa ei ole — sivu on täysin staattinen eikä kutsu mitään ulkoista.

## Kolme asiaa, jotka tarvitsevat kannanoton

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

**3. Repon näkyvyys.** Repo on nyt **julkinen**, eli `CLAUDE.md`, `sources.yaml`
ja `src/analyze.py` — koko mediaseurannan priorisointilogiikka ja
kalibrointihistoria — ovat kenen tahansa luettavissa. Salattu raportti on
suojattu, lähdekoodi ei.

Kun Vercel julkaisee sivun, reposta voi tehdä yksityisen ja sivu toimii silti.
Ehto: **yksityinen repo + GitHub Pages vaatii maksullisen GitHub Team -tason,
Vercel ei.** Valinta on siis "yksityinen repo ja vain Vercel" tai "julkinen repo
ja Pages rinnalla".

## Yhteystiedot

Raportin sisältö, ajo ja salasana: Nuutti Laitila, viestintä
(nuutti.laitila@golf.fi)
