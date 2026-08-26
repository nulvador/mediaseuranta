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

**Raakalista ("Näytä kaikki löydetyt uutiset")** on raportin lopussa napin
takana ja näyttää *kaikki* kerätyt jutut statuksesta riippumatta — myös
`irrelevant`- ja `expired`-tilaiset. Ilman sitä karsittu juttu katosi
näkyvistä kokonaan eikä suodatusta voinut tarkistaa. Lista on tarkoituksella
karu (päivä, lähde, otsikko alkukielellä): ei prioriteettia, ei käännöstä, ei
Gemini-kutsuja. Se noudattaa valittua välilehteä ja hakukenttää, ja merkitsee
"katsauksessa" ne jutut jotka näkyvät jo yläpuolella.

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

Kolme ikkunaa, kaikki artikkelin julkaisusta — tai havaitsemisesta, jos
julkaisupäivää ei tiedetä (`_EFF_DATE`):

| vakio | pv | ohjaa |
|---|---|---|
| `ANALYZE_DAYS` | 5 | mitä analysoidaan (`pending_articles`, `expire_old_pending`, `reset_analysis`) |
| `REPORT_DAYS` | 7 | mitä näkyy katsauksessa (`report_articles`) |
| `RAW_DAYS` | 7 | mitä näkyy raakalistassa (`raw_articles`) |
| `RETENTION_DAYS` | 90 | dedup-historia, jottei vanha uutinen palaa uutena |

**Analyysi-ikkuna on lyhyempi kuin katsausikkuna, eikä niitä saa yhdistää.**
`REPORT_DAYS` ohjasi 8/2026 asti myös analyysiä, joten näkyvyyden pidentäminen
olisi samalla laajentanut analysoitavien joukkoa — kalleinta mitä tässä voi
tehdä. Nyt näkyvyyttä voi venyttää ilman yhtään lisäkutsua: 6–7 pv vanha juttu
näkyy sillä arviolla, joka sille tehtiin tuoreena.

Seuraus, joka pitää muistaa: **katsauksessa on juttuja, joita ei enää voi
uudelleenanalysoida.** `--reanalyze` rajaa `ANALYZE_DAYS`-ikkunaan, joten 6–7 pv
vanhan jutun arvio jää vanhalla promptilla tehdyksi kunnes se poistuu näkyvistä.
Tämä on tarkoituksellista: merkitseminen ei tuottaisi uutta arviota, vain
hukkaisi vanhan `expired`-tilaan.

Miksi 7 eikä 5 (20.8.2026): Golf Irelandin 6 M€ infrastruktuuriohjelma oli
oikein `korkea`, mutta putosi katsauksesta kahden raportin jälkeen puhtaasti
ikäsäännön takia. Kahdella ajolla viikossa 5 pv jättää kärkijutulle liian vähän
näkyvyyttä. Hinta: katsaus on pidempi ja samat kärkijutut toistuvat useammassa
peräkkäisessä raportissa.

Raakalista ei ole enää katsausta pidempi. Alkuperäinen perustelu (karsittuihin
juttuihin pitää ehtiä palata edellisen ajon jälkeen) täyttyy silti: 7 pv kattaa
ti+pe-rytmin 3–4 pv välin. Jos katsausikkunaa kasvatetaan vielä, kasvata
`RAW_DAYS` mukana — raakalista on suodatuksen tarkistusväline, joten se ei saa
loppua ennen katsausta.

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

### Lajiliitoilla korkea vaatii testilauseen (kalibrointi 8/2026)

Punainen oli lajiliitoilla magneetti: 14.8. ajossa jakauma oli **12 punaista,
0 keltaista, 7 vihreää** — keskitaso jäi kokonaan käyttämättä ja punaiseen
päätyi TV-näkyvyystiedote ja leirin jälkiraportti. Syy oli luettelomainen
punainen: kymmenen kohtaa, joista malli löysi aina jonkin osuman.

Korjaus ei ollut uusi luetelmakohta vaan **testilause kohdan 5 alussa**:
kirjoita mielessäsi "Golfliitto voisi tehdä saman: ___". Jos lause vaatii
venytystä tai jää yleiseksi ("saisi lisää näkyvyyttä", "hyvä esimerkki
muille"), taso on keltainen. Lisäksi promptissa lukee, että **korkea on
harvinainen**.

Rajat on kirjattu vastakkainasetteluina, ei erillisinä sääntöinä:

| Punainen | Keltainen tai vihreä |
|---|---|
| Tehty rahoituspäätös | Avoin hakuilmoitus ja määräaika (vihreä) |
| Julkaistu tutkimus tai mitattu luku | Kyselyn tai selvityksen käynnistäminen |
| Digipalvelu, jolle on golfvastine | Oman lajin erityispiirteeseen sidottu järjestelmä |
| Harrastajahankintamalli tuloksineen | Yhden tapahtuman onnistuminen |
| Liittotason päätös | Yhden seuran hyvä käytäntö, jonka liitto nostaa esiin |

Huippu-urheilun valmennuskeskus- ja organisaatiojärjestelyt ovat keltaisia:
ne eivät kosketa harrastajapohjaa, josta golf on kiinnostunut.

Kuiva-ajo samalla 61 artikkelin aineistolla: **10 punaista → 3**, keskitaso
otettiin käyttöön (5), ja portti B alkoi purra myös koulutustarjontaan, joka
oli vuotanut vihreään. Jäljelle jääneet punaiset olivat Minimäkikiertue,
Apollo Sports -kumppanuus ja Ikiliike-pilotit — kaikissa on käyttöön otettu
malli ja tulokset.

### Portti B:n näkyvyyspoikkeus

Näkyvyys- ja kohderyhmäuutiset (naisurheilun pääsy suoratoistopalveluihin,
tyttöjunioreiden leiri) kuuluvat viestintäpäällikölle **keltaisina**, vaikka ne
muuten olisivat portti B:n tapahtumaviestintää. Siksi portissa B on poikkeus:
se ei sulje pois juttua, joka kertoo lajin pääsystä valtakunnalliseen mediaan
tai kaupalliseen suoratoistopalveluun, tai aliedustetun kohderyhmän
tavoittamisesta uutena harrastajajoukkona.

Poikkeus vuoti kahdesti kuiva-ajossa, ja molemmat rajaukset ovat pakollisia:

1. **Liiton oma kanava ei ole valtakunnallista mediaa.** Ilman rajausta
   "Huipputurnaukset jatkuvat SalibandyTV:ssä – katso myös älytelevisiosta"
   nousi keltaiseksi. Kyse on katsomiskehotuksesta, ei mediasopimuksesta.
2. **Poikkeus ei ohita porttia A.** Ilman rajausta "Nämä pelaajat kutsuttiin
   Naisleijonien testileirille" nousi keltaiseksi — sana "naiset" riitti
   ohittamaan koko kilpailusuoritusportin.

Yleisempi oppi: portin poikkeus periytyy herkästi muihin portteihin, ja
kohderyhmäsana ("naiset", "tytöt") on mallille vahva nostosignaali. Kirjoita
poikkeuksen rajat auki heti, älä vasta kun vuoto näkyy.

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

## Ihmisen korjaukset raportissa

Viestintäpäällikkö voi korjata yksittäisen jutun arvion suoraan raportissa:
kortin alalaidassa on kolme tasonappia ja ✕ ("ei kuulu katsaukseen"), ja
raakalistalla "+ katsaukseen". Korjaus vaikuttaa heti näkymään ja siirtyy
kantaan `--apply-corrections`-ajolla.

**Prompti ja portit EIVÄT päivity automaattisesti — tämä on suunnittelupäätös,
ei puuttuva ominaisuus.** Esimerkkien liimaaminen promptiin ilman ihmisen
päätöstä siitä, kuuluuko sääntö porttiin vai kohtaan 5, on juuri se virhe joka
tuotti kolme peräkkäistä virhekierrosta 7/2026. Korjaukset kertyvät siksi
`corrections`-tauluun, ja prompti päivitetään käsin kalibrointikierroksella.

### Kolme korjaustyyppiä, kaikki deterministisiä

| verdict | mistä | vaikutus | Gemini-kutsuja |
|---|---|---|---|
| `priority` | kortin tasonappi | ihmisen taso voittaa mallin tason | 0 |
| `exclude` | kortin ✕ | status → `irrelevant` | 0 |
| `include` | raakalistan "+ katsaukseen" | status → `analyzed` | 0 |

`include` on ilmainen, koska **karsituilla riveillä on jo käännös kannassa**:
`save_analysis` tallentaa `title_fi`/`summary_fi`/`priority` myös
`relevant=false`-riveille. Poikkeus on juttu jota ei ole koskaan analysoitu
(`new`/`expired`, ei käännöstä): silloin status jätetään ennalleen, juttu
analysoidaan normaalisti ja sama korjaus nostaa sen mukaan analyysin jälkeen.

### apply_corrections ajetaan JOKA ajossa, analyysin jälkeen

Ei kertaluontoisena UPDATEna. Tuore Gemini-arvio — tai `--reanalyze` — pyyhkisi
muuten korjauksen heti seuraavassa ajossa. Sijainti `main.py`:ssä on siksi
analyysin jälkeen ja raportin edellä, ja funktio on idempotentti. Testi
`test_correction_survives_reanalysis` lukitsee tämän.

Kohde etsitään ensin `url_hash`illa ja sitten `title_key`llä: dedup jättää
parista vain toisen rivin, joten korjattu rivi voi hävitä ja kaksonen jäädä.

### Kaksi kerrosta, koska raportti on staattinen tiedosto

Julkaistu raportti on salattu HTML Vercelissä ilman backendiä, joten selain ei
voi kirjoittaa kantaan. Siksi korjaus elää kahdessa paikassa:

1. **`localStorage`** (avain `golfkatsaus.korjaukset`, per selain) — korjaus
   näkyy heti ja säilyy myös seuraavan ajon uudessa HTML-tiedostossa, koska
   avain on `url_hash`. Kaikki kutsut ovat try/catchissa: yksityinen
   selainikkuna heittää poikkeuksen, eikä raportti saa kaatua siihen.
2. **`corrections`-taulu** — kun JSON on viety `--apply-corrections`-ajolla.
   Sen jälkeen sama arvo tulee jo upotetussa datassa ja kerros 1 muuttuu
   tyhjäkäynniksi.

Siirto on käsityö (kopioi JSON → tiedosto → aja komento). Automaattinen reitti
olisi Vercel Function + GitHub-token tai valmiiksi täytetty GitHub-issue;
kumpaakaan ei ole tehty, koska kumpikin lisää salaisuuden tai julkisen
kirjoitusendpointin ylläpidettäväksi.

### Mitä korjaus EI tee

- **Ei anna jutulle lisäaikaa.** Korjaus näkyy niin kauan kuin juttu on
  `REPORT_DAYS`-ikkunassa. 5 pv vanha korjattu juttu näkyy enää kaksi päivää.
- **Ei yleisty uusiin juttuihin.** Avain on tietyn jutun `url_hash`.
- **Ei kirjaa vahvistusta.** Mallin oman tason painaminen poistaa korjauksen
  sen sijaan että kirjaisi muutoksen — muuten aineistoon kertyisi tyhjiä rivejä.
- **Ei piilota ✕:llä merkittyä heti.** Kortti jää näkyviin himmeänä listan
  loppuun, jotta vahinkopainallus näkyy ja on peruttavissa. Se katoaa vasta
  seuraavassa generoinnissa.

### Korjaukset ovat kalibrointiaineistoa — ja ne ovat vinoja

`corrections` on oma taulu eikä sarake `articles`-taulussa kahdesta syystä:
korjaus säilyy vaikka artikkeli poistuisi `RETENTION_DAYS`-purgessa, ja mallin
oma arvio jää talteen vierelle (`was_priority`), jotta katselmuksessa näkee
mistä mihin arvio muuttui. `reason` on katselmuksen tärkein kenttä: otsikko
kertoo *mikä* korjattiin, perustelu *miksi* — ja vain jälkimmäisestä syntyy
promptisääntö.

**Aineisto painottuu väistämättä laskuihin.** Ylinosto näkyy punaisena kortin
kärjessä; portin karsintavirhe näkyy vain raakalistasta. Jos promptia viritetään
pelkällä korjauslistalla, koko jakauma valuu alaspäin. Siksi
`--list-corrections` tulostaa jakauman suunnittain — lue se ennen kuin muutat
promptia, ja käy raakalista välillä läpi vaikkei mikään ärsyttäisi.

**Laukaisin on toisto, ei kappalemäärä.** Sama sääntö korjattuna 3 kertaa →
korjaa heti (kapea muutos yhteen paikkaan). 30–40 korjausta → varsinainen
kalibrointikierros, jossa prompti luetaan kokonaisuutena ja muutos kuiva-ajetaan
tätä aineistoa vasten. Kahdella ajolla viikossa pelkkä kappalemäärä tarkoittaisi
3–4 kuukauden odotusta systemaattisen porttivuodon kanssa.

`--mark-reviewed` merkitsee erän käsitellyksi. Rivit jäävät kantaan, koska sama
erä on promptimuutoksen jälkeen se testiaineisto, jota vasten osuvuuden voi
mitata. Uusi korjaus samaan juttuun korvaa vanhan ja nollaa `reviewed_at`:n.

Komennot:

```
--apply-corrections PATH   vie raportista kopioitu JSON kantaan
--list-corrections         katselmoimattomat + jakauma suunnittain
--mark-reviewed            merkitse erä käsitellyksi kalibroinnin jälkeen
```

Yksikään näistä ei kuluta Gemini-kutsuja. `--reanalyze` on ainoa tapa nähdä
promptimuutos jo kerätyissä jutuissa, ja se rajataan yhteen välilehteen.

## Arkkitehtuuri

```
sources.yaml       lähteet (RSS → json_api → sitemap → HTML → Google News,
                   ensimmäinen osuma voittaa)
src/config.py      polut, .env, vakiot
src/sources.py     YAML-lataus, Google News -lokaalit per kieli
src/fetch.py       rinnakkainen keruu, 15 s timeout, alidomain-suodatus
src/store.py       SQLite: dedup, statukset, ikäsäännöt, korjaukset, migraatiot
src/analyze.py     Gemini structured output; 3 promptia (golf/lajiliitot/media)
src/report.py      HTML-raportti (3 välilehteä; media on oma näkymänsä)
src/encrypt.py     AES-GCM-salaus web-julkaisuun
src/emailer.py     valinnainen SMTP (odottaa tunnuksia)
src/main.py        pääohjelma
run.sh             ajo + salaus + git push (Vercel julkaisee docs/index.html)
deploy/            launchd-ajastus paikalliseen ajoon (ti + pe klo 10:15);
                   tuotannon ajastus on GitHub Actionsissa
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
- **Päivämäärätön artikkeli tallennetaan havaitsemispäivällä.** Sääntö on sama
  kaikilla reiteillä: jos päivää ei löydy, `published` jää tyhjäksi ja
  `_EFF_DATE` käyttää `fetched_at`-päivää. Juttua ei siis koskaan hylätä
  päivämäärän puutteen takia. Hinta on että vanha juttu näyttää tuoreelta, joten
  `fetch_source` **varoittaa lokissa** jos lähde tuottaa päivämäärättömiä
  artikkeleita — tarkista silloin selektori. Näin kävi Islannille, Italialle ja
  Tanskalle (7/2026).
- **Tarkista aina HTML-lähteen päivämääräselektori.** Oletuslistan selektorit
  eivät osu kaikkialle: EGA:lla luokka on `news-page-item__small-date`, ei
  `date`.
- **`json_api` — sivuston oma rajapinta.** Kun uutislistaus on JS-sovellus,
  se hakee datansa rajapinnasta jota voi kutsua suoraan. Näin toimivat England
  Golf ja Golf Ireland (sama alusta, `POST /api/news/GetNewsArticles`, erona
  `clubWebsiteId`). Rajapinta antaa myös oikean ingressin, mikä parantaa
  arvioita. Nämä ovat dokumentoimattomia rajapintoja → jätä Google News
  varareitiksi.
- **`sitemap` — viimeinen keino.** Kun listausrajapintaa ei löydy (R&A: Next.js,
  jonka `__NEXT_DATA__` sisältää vain hero-artikkelin), sitemap antaa osoitteet
  ja `lastmod`-päivän, ja artikkelisivun og-metatiedot otsikon, ingressin ja
  kuvan. Huomaa: `lastmod` on muokkausaika, ei julkaisuaika — R&A:lla ne
  vastaavat päivän tarkkuudella, mutta jos lähde muokkaa vanhoja sivuja, ne
  nousevat tuoreina. Ikkuna rajataan `lastmod`illa ennen artikkelisivujen
  hakua, ettei haeta satoja sivuja.
- Templaattisivustot (Knockout, Vue) näyttävät toimivilta: kortteja löytyy, mutta
  ne ovat tyhjiä runkoja, joissa linkki on `#!` ja otsikoksi valikoituu CMS:n
  painike ("Edit Article"). `fetch.py` hylkää nyt listaussivulle itseensä
  osoittavat linkit — jos lähde tuottaa outoja otsikoita, epäile templaattia.
- **Nollalähde ei ole aina rikki.** Erottele: "N liian vanhaa" = lähde toimii,
  julkaisee harvoin (esim. STERF, SGF, OKM). "muun median juttua" tai
  "puutteellista" = reitti on väärä ja se kannattaa korjata.

## Media-välilehti (suomalainen media)

Kolmas välilehti: suomalaisen median golf-osumat, oma prompti
(`_PROMPT_MEDIA`), kerätty hakusanoilla eikä lähdelistalla.

**Ikkunat ovat samat kuin muilla välilehdillä** — `ANALYZE_DAYS` 5,
`REPORT_DAYS` 7, `RAW_DAYS` 7. Erillisiä `MEDIA_DAYS`-vakioita EI ole, eikä
niitä pidä palauttaa: ne haaruttivat storen (`CASE WHEN tab = 'media'`) neljässä
funktiossa ilman että kukaan hyötyi pidemmästä ikkunasta. Testi
`test_media_uses_the_same_windows_as_other_tabs` lukitsee tämän.

Median erityispiirteitä on siis enää kolme: oma prompti, oma dedup-avain
(otsikko ilman lähdettä) ja oma saateteksti raportissa.

**Kysymys on tässä toinen kuin liittovälilehdillä.** Siellä kysytään *"voiko
Golfliitto kopioida tämän mallin"*. Medialla kysytään **"puhutaanko meistä, ja
pitääkö reagoida"** — julkisuuskuva, kotimaisen golfin toimintaedellytykset,
lajin näkyvyys. Älä yritä yhdistää näitä yhdeksi promptiksi.

| taso | media | vrt. liitot |
|---|---|---|
| korkea | Suomen golfin **rakenne, päätös tai maine**: liiton päätös tai järjestelmähäiriö, kotimaisen kentän kaavoitus tai sertifiointi, kotimaisen kiertueen kalenterimuutos, häirintätapaus | "voiko kopioida" |
| keskitaso | suomalainen pelaaja, kotimainen kilpailu, lajin näkyvyys ja kohut | "pitääkö tietää" |
| matala | kansainvälinen toimialauutinen, pehmeä lukijajuttu | "miten toinen liitto toimii" |

Portit ovat myös eri: **A** = golf ei ole jutun aihe (hakusana osui tekstin
sisään), **B** = ei ole uutinen (palstailmoitus, vedonlyöntivihje, ohjelmatieto),
**C** = ulkomainen ilman kytköstä Suomeen.

Kaksi rajaa, jotka on kirjoitettava auki tai ne vuotavat:
- **Vedonlyöntivihje karsiutuu, vaikka kilpailu olisi kotimainen** — juttu ei
  kerro kilpailusta vaan kertoimista ("Golf-vihjeet: Vierumäki Finnish
  Challenge").
- **Ulkomaisuus ei yksin karsi.** Portti C päästää läpi uutisen, joka muuttaa
  golfin rahavirtoja (LIV/Saudi = matala) tai nousee laajaksi puheenaiheeksi
  pelikulttuurista (Trump = keskitaso). Perusteena on uutisen kantavuus koko
  lajille, EI henkilön kuuluisuus — ilman tätä rajausta jokainen tunnetun
  pelaajan juttu nousisi.

### Kalibrointi 8/2026: 32/33 viestintäpäällikön omaa luokittelua vasten

Prompti kirjoitettiin 33 käsin luokitellusta jutusta ja kuiva-ajettiin samalla
aineistolla. Ainoa ero oli juttu, jonka otsikossa ei lue sanaakaan golfista
("Tämä mainos poistettiin alta aikayksikön: naista kohdeltiin törkeästi
kameroiden edessä"). **Sitä ei saa lisätä korkean esimerkkilistaan** — se
opettaisi mallille, että golfiton otsikko voi olla korkea, ja rikkoisi portti
A:n kokonaan. Juttu näkyy joka tapauksessa raakalistassa.

Muista: 32/33 mittaa johdonmukaisuutta, ei yleistyskykyä, koska esimerkit ovat
samasta aineistosta. Oikea koe on seuraava erä.

### Vain otsikko käytettävissä

Google News **ei anna ingressiä**: 71/81 media-jutussa `summary` on pelkkä
otsikko uudestaan, ja kaikki linkit ovat opaakkeja `news.google.com`-redirectejä.
Prompti sanoo tämän ääneen ja kieltää keksimästä sisältöä. Tämä on median
laatukatto — liittovälilehdillä RSS ja `json_api` antavat oikean ingressin, ja
arviot ovat siksi parempia. Jos median laatua halutaan nostaa, oikea korjaus on
hakea artikkelisivun og-metatiedot, ei promptin kiristäminen.

### Lajimedia karsitaan ehdollisesti

`Golfpiste.com` on **ehdollisessa** karsinnassa (`exclude_publishers_unless`):
julkaisija pudotetaan, paitsi jos otsikko osuu pelastuslistaan (`golfliit`,
`liitto`, `liito`, `team finland`). Perustelu: sen virta on pääosin
kiertuetuloksia, varusteita ja palstailmoituksia, ja painopiste on kansallisissa
ja maakuntamedioissa. Liittoa itseään koskeva juttu — myös liiton toiminnan
kritiikki — jää mukaan.

Karsinta tehdään **keruussa eikä promptissa** kahdesta syystä: karsitut eivät
kuluta Gemini-kutsuja, ja sääntö näkyy lokista rivinä "N ehdollisesti
karsittua julkaisijan juttua". Prompti ei myöskään voisi soveltaa
julkaisijakohtaista sääntöä luotettavasti, koska media-jutuista on käytössä
vain otsikko.

**Astevaihtelu on tässä oikea ansa.** Fraasit ovat osamerkkijonoja, ja suomen
heikko aste katkaisee osuman: `liitto` **ei** osu muotoihin *liiton* tai
*liitolta*, koska toinen t katoaa — ja juuri ne muodot esiintyvät kritiikissä.
Siksi listalla on molemmat vartalot, `liitto` ja `liito`. Testi
`test_conditional_publisher_exclusion` lukitsee tämän. Jos lisäät fraaseja,
tarkista taivutusmuodot.

Hinta on kirjattava: sääntö pudotti 21 jo kerättyä Golfpiste-riviä, joista 10
oli katsauksessa — mm. Samoojan, Lindellin ja Välimäen kisajutut. Samat pelaajat
uutisoidaan myös Ylessä, HS:ssä ja maakuntalehdissä, joten menetys on pieni,
mutta jos suomalaispelaajien kisaseuranta ohenee, tämä sääntö on ensimmäinen
paikka tarkistaa.

### Liiton omat kanavat eivät ole mediaseurantaa

`golf.fi` / "Suomen Golfliitto" on julkaisijasuodattimessa: oman tiedotteen
näkeminen mediaseurannassa ei kerro mitään. **Poiminta sen sijaan kertoo** — kun
Paraurheilu.fi julkaisee saman uutisen, julkaisija on Paraurheilu.fi ja juttu
jää listalle. Painopiste on kansallisissa ja maakuntamedioissa.

### Hakusäännöt on mitattu — älä muuta ilman uutta mittausta

| Sääntö | Mittaus (8/2026) |
|---|---|
| `when:` on **pakollinen** | `golf` → 39 osumaa ilman, **100** kanssa |
| `when:`-ikkuna = näkyvyysikkuna | `when:30d` → 100 merkintää, joista vain **41** ≤7 pv; `when:7d` → **54**, kaikki ikkunassa |
| Hae **yhdellä sanalla** | `golf` → 30, `golf (Suomi OR Golfliitto OR golfseura)` → **1** |
| Kahden sanan AND on yhtä paha | `golfkenttä kunta` → **0** |
| **Älä** hae medioittain (`site:`) | `site:is.fi golf when:7d` palautti juttuja vuodelta **2021** |

Syy on sama kaikissa: Google News järjestää tulokset relevanssin, ei
päivämäärän mukaan, ja syöte katkeaa 100 merkintään. `when:` pakottaa tuoreuden;
`site:` ohittaa sen. Ja koska budjetti on 100 merkintää, **liian pitkä `when:`
hukkaa tuoreita**: se täyttää budjetin jutuilla, jotka karsiutuvat silti iän
takia. Jos näkyvyysikkunaa muutetaan, muuta `when:` mukana. Laaja hakusana tavoittaa isot lehdet ilman `site:`-rajausta
ja lisäksi maakuntalehdet, joita ei tulisi listanneeksi (ensimmäisessä ajossa
osumia tuli 28 julkaisijalta: Viiskunta, Kaleva, Lapin Kansa, Uutisvuoksi,
Järviseudun sanomat, Aamuposti…).

**Nollaosuma ei ole vika.** Nimihaut osuvat harvoin mutta arvokkaasti:
`"antti tiitola"` antoi 0 osumaa 30 pv:ltä mutta 180 pv:ltä juuri sen jutun jota
haetaan (*"Muut lehdet: Golfliiton puheenjohtajan mukaan golf on päässyt eroon
'vanhojen herrojen lajin' maineesta"*). Siksi media-lähteet on rajattu pois
"LÄHTEET ILMAN ARTIKKELEITA" -varoituksesta ja lokitetaan omalla rivillään.

**Yleinen nimi on pakko sitoa golfiin.** `"juha korhonen"` yksinään palautti
metsästysseuran puheenjohtajan, kirjastojutun ja Seiska-juttuja;
`"juha korhonen" golf` palauttaa vain golfin. Harvinainen nimi
(`"antti tiitola"`) toimii sellaisenaan.

### Kolme mekanismia, jotka media-välilehti tarvitsi

- **`title_key` ilman lähdettä.** Liittovälilehdillä avain on lähdekohtainen,
  koska kahden liiton uutinen samasta asiasta on kaksi eri juttua. Medialla se
  on päinvastoin: sama STT-juttu on Iltalehdessä ja IS:ssä, ja sama juttu osuu
  kahteen hakusanaan. "Lähde" ei ole julkaisija vaan hakulause, joten avain
  lasketaan pelkästä otsikosta. Ensimmäisessä ajossa tämä yhdisti 102 osumaa
  81 riviksi.
- **Julkaisijan nimi Google Newsin `<source>`-tagista.** Ilman tätä listalla
  lukisi joka rivillä hakulauseen nimi. Ylikirjoitus tehdään vain vapaassa
  haussa — `site:`-haussa julkaisija on jo tiedossa.
- **`max_articles` per lähde.** Globaali `MAX_PER_SOURCE = 15` katkaisisi laajan
  `golf`-haun (100 osumaa) kuudesosaan. Liittolähteille 15 riittää yhä.

### Hylkylistat pidetään lyhyinä

`exclude` (osuma otsikkoon) ja `exclude_publishers` (julkaisijan nimi) ovat
**vain toistuvaa roskaa varten** — TV-ohjelmatiedot ("ohjelman aikataulut") ja
väärän maan julkaisijat, jotka laaja hakusana raahaa mukanaan joka ajossa.
Aiheen rajaaminen ei kuulu näihin: media-välilehden koko idea on, että
relevanssin ratkaisee ihminen. Jos lista alkaa kasvaa, kysy ensin onko oikea
korjaus hakusanassa.

## Julkaisu

`run.sh` salaa raportin (`REPORT_PASSWORD` .env:stä) ja pushaa `docs/index.html`.
Jos salaus epäonnistuu, julkaisu ohitetaan — salaamatonta ei koskaan pushata.
Osoite: https://mediaseuranta.vercel.app
Repo: https://github.com/Suomen-Golfliitto-ry/mediaseuranta
Ajastus: GitHub Actions (.github/workflows/monitor.yml), ti+pe.
Avaimet: GitHubin repo-salaisuudet GEMINI_API_KEY ja REPORT_PASSWORD.

**Hostaus on Vercel**, ei GitHub Pages (26.8.2026). Vercel-projektin Root
Directory on `docs`, ei buildia eikä ympäristömuuttujia: se julkaisee
`docs/index.html`-tiedoston sellaisenaan jokaisesta `main`-pushista. Ketju on
siis Actions-ajo → commit `docs/index.html` → Vercel deploy.

**`docs/`-kansiota ei saa poistaa** vaikka Pages on lopetettu — se on Vercelin
lähde, ei Pagesin jäänne. Pagesin lopetus on pelkkä GitHubin asetus
(Settings → Pages → Source: None), ei repomuutos, joten mikään koodissa ei
viittaa siihen. Ainoa jälki oli `run.sh`:n kommentti, joka on korjattu.

Vanha Pages-osoite (`suomen-golfliitto-ry.github.io/mediaseuranta`) lakkaa
toimimasta kun asetus otetaan pois. Jos joku raportoi kuolleen linkin, se on
todennäköisesti tämä — ohjaa Vercel-osoitteeseen.

## Muuta

- `.env` ei koskaan versionhallintaan (API-avain, salasana, SMTP).
- Testit: `python -m pytest tests/ -q`
- Kieli: kaikki käyttäjälle näkyvä ja kommentit suomeksi.
