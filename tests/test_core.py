"""Perus-yksikkötestit: otsikon siivous, päivämäärät, dedup, migraatio.

Ajo:  python -m pytest tests/ -q     (pip install pytest)
"""
import datetime
import json
import sqlite3

import pytest

from src import config, store
from src.fetch import clean_title, parse_date
from src.sources import load_sources


# ---------------------------------------------------------------- fetch
def test_clean_title_whitespace():
    assert clean_title("  Uutinen \n  golfista  ") == "Uutinen golfista"


def test_clean_title_google_news_suffix():
    assert clean_title("Golfliitto uudistaa strategiansa - Yle Urheilu",
                       google_news=True) == "Golfliitto uudistaa strategiansa"


def test_clean_title_keeps_hyphenated_names():
    # Suffiksi poistetaan vain kun se näyttää lähteeltä (ympäröivät välilyönnit)
    assert clean_title("Golf-kausi alkaa", google_news=True) == "Golf-kausi alkaa"


def test_parse_date_iso():
    assert parse_date("2026-07-03") == datetime.date(2026, 7, 3)


def test_parse_date_finnish_format():
    assert parse_date("3.7.2026") == datetime.date(2026, 7, 3)


def test_parse_date_garbage():
    assert parse_date("ei ole päivämäärä") is None
    assert parse_date("") is None


def test_parse_date_localised_months():
    # Lähteiden kielten kuukaudennimet. Ilman käännöstä dateutil täytti
    # tunnistamattoman kuukauden nykyhetkestä: "5. juli 2026" -> 2026-05-27,
    # jolloin vanha juttu näytti tuoreelta.
    assert parse_date("5. juli 2026") == datetime.date(2026, 7, 5)          # no
    assert parse_date("16 maj 2025") == datetime.date(2025, 5, 16)          # sv
    assert parse_date("26 Luglio 2026") == datetime.date(2026, 7, 26)       # it
    assert parse_date("5 de julio de 2026") == datetime.date(2026, 7, 5)    # es
    assert parse_date("12. ágúst 2026") == datetime.date(2026, 8, 12)       # is
    assert parse_date("27. Juli 2026") == datetime.date(2026, 7, 27)        # de
    assert parse_date("8 lipca 2026") == datetime.date(2026, 7, 8)          # pl


def test_parse_date_iso_not_dayfirst():
    # dayfirst=True sai dateutilin kääntämään ISO-päivämäärän kuukausi/päivä
    assert parse_date("2026-07-03") == datetime.date(2026, 7, 3)
    assert parse_date("2025-05-16 08:00:00Z") == datetime.date(2025, 5, 16)


def test_parse_date_danish_slash_dash():
    # Dansk Golf Union käyttää muotoa 19/06-2026
    assert parse_date("19/06-2026") == datetime.date(2026, 6, 19)


# ---------------------------------------------------------------- store
@pytest.fixture()
def conn(tmp_path):
    c = store.connect(tmp_path / "test.db")
    yield c
    c.close()


def _art(url="https://x.fi/a", title="Testiotsikko pitkä kyllä"):
    # Päivämäärä suhteessa tähän päivään: pending_articles rajaa ANALYZE_DAYS-ikkunaan,
    # joten kovakoodattu päivä vanhenee ikkunan ulkopuolelle ja kaataa testit.
    published = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    return {"source_id": "s1", "source_name": "Lähde", "tab": "golfliitot",
            "country": "Suomi", "language": "fi", "title": title,
            "url": url, "published": published, "summary": "Ingressi"}


def test_parse_date_iso_timestamp_not_swapped():
    """ISO-aikaleiman päivä ja kuukausi eivät saa vaihtaa paikkaa.

    "2026-07-11T19:00:00" tulkittiin päiväksi 7.11.2026, koska ISO-regexin \\b ei
    osunut "11":n ja "T":n väliin ja dateutil sai sen dayfirst=True:llä."""
    import datetime as dt
    from src.fetch import parse_date
    assert parse_date("2026-07-11T19:00:00") == dt.date(2026, 7, 11)
    assert parse_date("2026-01-02T00:00:00Z") == dt.date(2026, 1, 2)
    assert parse_date("2026-12-31T23:59:59+03:00") == dt.date(2026, 12, 31)
    # Yksiselitteiset muodot eivät muutu
    assert parse_date("2026-07-03") == dt.date(2026, 7, 3)
    assert parse_date("28 Jul 2026") == dt.date(2026, 7, 28)
    assert parse_date("5. juli 2026") == dt.date(2026, 7, 5)


def test_pick_containers_skips_empty_shells():
    """Tyhjät rungot eivät saa varjostaa toimivaa selektoria.

    EGA:n Drupal-sivulla oletuslistan 'article' osui 18 kuvaelementtiin,
    joten oikeaa '.views-row'-selektoria ei kokeiltu koskaan."""
    from bs4 import BeautifulSoup
    from src.fetch import _pick_containers
    html = """
      <article class="media"><img src="a.jpg"></article>
      <article class="media"><img src="b.jpg"></article>
      <div class="views-row"><h2>Oikea uutisotsikko tässä</h2>
        <a href="/uutinen">lue</a></div>
    """
    soup = BeautifulSoup(html, "lxml")
    sel = {"container": ["article", ".views-row"], "title": ["h2", "h3"]}
    picked = _pick_containers(soup, sel)
    assert len(picked) == 1
    assert "views-row" in picked[0].get("class")

    # Jos mikään ei tuota käyttökelpoisia, palautetaan ensimmäinen osuma niin
    # että diagnostiikka kertoo "N puutteellista" eikä "selektorit eivät osu".
    soup2 = BeautifulSoup('<article class="media"><img src="a.jpg"></article>', "lxml")
    assert len(_pick_containers(soup2, sel)) == 1


def test_repair_link():
    from src.fetch import repair_link
    # NGF:n syöte: skeema ilman kaksoispistettä -> feedparser liimasi base-URLin
    assert (repair_link("http://www.ngf.nlhttps//www.ngf.nl/nieuws/juttu")
            == "https://www.ngf.nl/nieuws/juttu")
    # Kunnolliset URLit eivät saa muuttua
    for url in ("https://x.fi/a", "http://y.fi/b?q=1", "https://golf.fi/uutiset/x"):
        assert repair_link(url) == url
    assert repair_link("") == ""


def test_insert_dedup(conn):
    assert store.insert_new(conn, [_art()]) == 1
    assert store.insert_new(conn, [_art()]) == 0          # sama url -> ei duplikaattia
    assert store.insert_new(conn, [_art(url="https://x.fi/b",
                                        title="Eri otsikko kokonaan")]) == 1


def test_insert_dedup_same_title_other_route(conn):
    """Google News -redirect ja suora URL antavat eri url_hashin samasta
    jutusta — otsikkoavain estää parin päätymisen raporttiin kahdesti."""
    assert store.insert_new(conn, [_art(url="https://news.google.com/rss/CBMiOPAQ")]) == 1
    assert store.insert_new(conn, [_art(url="https://x.fi/kanoninen")]) == 0
    # Välimerkit ja kirjainkoko eivät saa erottaa samaa otsikkoa
    assert store.insert_new(conn, [_art(url="https://x.fi/c",
                                        title="TESTIOTSIKKO, pitkä kyllä!")]) == 0
    # Eri lähde samasta asiasta on aito oma juttu
    other = _art(url="https://y.fi/a")
    other["source_id"] = "s2"
    assert store.insert_new(conn, [other]) == 1


def test_dedupe_by_title_keeps_analyzed(conn):
    """Vanhat parit siivotaan niin, että analysoitu rivi jää ja raportti säilyy."""
    gn = _art(url="https://news.google.com/rss/CBMiOPAQ")
    conn.execute("INSERT INTO articles (url_hash, url, source_id, source_name, tab, "
                 "title, published, fetched_at, status, title_key) "
                 "VALUES (?,?,?,?,?,?,?,?,'irrelevant',?)",
                 (store.url_hash(gn), gn["url"], gn["source_id"], gn["source_name"],
                  gn["tab"], gn["title"], gn["published"], gn["published"],
                  store.title_key(gn)))
    conn.commit()
    direct = _art(url="https://x.fi/kanoninen")
    conn.execute("INSERT INTO articles (url_hash, url, source_id, source_name, tab, "
                 "title, published, fetched_at, status, title_fi, title_key) "
                 "VALUES (?,?,?,?,?,?,?,?,'analyzed','Suomennos',?)",
                 (store.url_hash(direct), direct["url"], direct["source_id"],
                  direct["source_name"], direct["tab"], direct["title"],
                  direct["published"], direct["published"], store.title_key(direct)))
    conn.commit()

    assert store.dedupe_by_title(conn) == 1
    rows = conn.execute("SELECT url, status FROM articles").fetchall()
    assert len(rows) == 1
    assert rows[0]["status"] == "analyzed"          # analysoitu työ säilyi
    assert "news.google.com" not in rows[0]["url"]  # suora linkki säilyi
    assert store.dedupe_by_title(conn) == 0         # idempotentti


def test_analysis_checkpoint_lifecycle(conn):
    store.insert_new(conn, [_art()])
    pending = store.pending_articles(conn)
    assert len(pending) == 1

    store.save_analysis(conn, [{
        "article_id": pending[0]["id"], "relevant": True,
        "title_fi": "Suomennos", "summary_fi": "Tiivistelmä",
        "category": "muu", "priority": "korkea", "themes": ["juniorit"],
    }])
    assert store.pending_articles(conn) == []
    arts = store.report_articles(conn, days=3650)
    assert arts[0]["title_fi"] == "Suomennos"
    assert arts[0]["themes"] == ["juniorit"]


def test_irrelevant_hidden_from_report(conn):
    store.insert_new(conn, [_art()])
    pending = store.pending_articles(conn)
    store.save_analysis(conn, [{"article_id": pending[0]["id"], "relevant": False,
                                "title_fi": "", "summary_fi": "", "category": "muu",
                                "priority": "matala", "themes": []}])
    assert store.report_articles(conn, days=3650) == []


def test_raw_list_keeps_filtered_out_articles(conn):
    """Raakalista näyttää myös karsitut — katsaus näyttää vain läpi menneet."""
    store.insert_new(conn, [_art(url="https://x.fi/a", title="Karsittu juttu"),
                            _art(url="https://x.fi/b", title="Relevantti juttu")])
    pending = {a["title"]: a["id"] for a in store.pending_articles(conn)}
    store.save_analysis(conn, [
        {"article_id": pending["Karsittu juttu"], "relevant": False,
         "title_fi": "", "summary_fi": "", "category": "muu",
         "priority": "matala", "themes": []},
        {"article_id": pending["Relevantti juttu"], "relevant": True,
         "title_fi": "Suomennos", "summary_fi": "Tiivistelmä", "category": "muu",
         "priority": "korkea", "themes": []},
    ])

    raw = store.raw_articles(conn, days=3650)
    assert {r["title"] for r in raw} == {"Karsittu juttu", "Relevantti juttu"}
    assert {r["title"] for r in store.report_articles(conn, days=3650)} == {"Relevantti juttu"}
    # eff_date on olemassa myös ilman julkaisupäivää (havaitsemispäivä)
    assert all(r["eff_date"] for r in raw)


def test_raw_list_respects_window(conn):
    old = _art(url="https://x.fi/vanha", title="Viikkoa vanhempi juttu")
    old["published"] = (datetime.date.today() - datetime.timedelta(days=9)).isoformat()
    store.insert_new(conn, [old])
    assert store.raw_articles(conn, days=7) == []
    assert len(store.raw_articles(conn, days=30)) == 1


def test_analyze_window_is_shorter_than_report_window():
    """Katsaus näkyy pidempään kuin analyysi kestää — ikkunoita ei saa yhdistää.

    Jos ANALYZE_DAYS kasvaa REPORT_DAYS:n mukana, näkyvyyden pidentäminen
    laajentaa samalla analysoitavien joukkoa ja syö Gemini-kiintiötä."""
    assert config.ANALYZE_DAYS <= config.REPORT_DAYS


def test_article_between_windows_stays_visible_but_is_not_reanalyzed(conn):
    """6 pv vanha analysoitu juttu näkyy katsauksessa mutta ei palaa jonoon.

    Irlannin 6 M€ infrastruktuuriohjelma (14.8.2026) oli oikein 'korkea',
    mutta putosi katsauksesta 5 pv ikkunan takia. Ikkunan pidentäminen ei saa
    tuoda sitä takaisin analysoitavaksi: arvio on jo tehty tuoreena."""
    mid = _art(url="https://x.fi/valissa", title="Ikkunoiden valissa oleva juttu")
    mid["published"] = (datetime.date.today() - datetime.timedelta(days=6)).isoformat()
    store.insert_new(conn, [mid])

    # Analyysi-ikkunan ulkopuolella: ei poimita jonoon eikä uudelleenanalyysiin
    assert store.pending_articles(conn) == []
    assert store.reset_analysis(conn) == 0

    # ...mutta tuoreena tehty arvio näkyy katsauksessa yhä
    conn.execute("UPDATE articles SET status='analyzed', title_fi='Suomennos', "
                 "priority='korkea' WHERE url=?", (mid["url"],))
    conn.commit()
    titles = {a["title"] for a in store.report_articles(conn, config.REPORT_DAYS)}
    assert "Ikkunoiden valissa oleva juttu" in titles
    assert store.report_articles(conn, config.ANALYZE_DAYS) == []


def test_expire_old_pending_uses_analyze_window(conn):
    """Analysoimaton juttu vanhenee analyysi-ikkunan, ei katsausikkunan mukaan."""
    mid = _art(url="https://x.fi/vanhentuva", title="Analysoimaton ja liian vanha")
    mid["published"] = (datetime.date.today() - datetime.timedelta(days=6)).isoformat()
    store.insert_new(conn, [mid])
    assert store.expire_old_pending(conn, config.ANALYZE_DAYS) == 1
    status = conn.execute("SELECT status FROM articles WHERE url=?",
                          (mid["url"],)).fetchone()[0]
    assert status == "expired"
    # expired ei näy katsauksessa, vaikka olisi REPORT_DAYS-ikkunan sisällä
    assert store.report_articles(conn, config.REPORT_DAYS) == []


def test_import_legacy_json(conn, tmp_path):
    legacy = tmp_path / "articles.json"
    legacy.write_text(json.dumps([
        {"url": "https://old.fi/1", "title": "Vanha uutinen", "title_fi": "Vanha uutinen fi",
         "source_name": "Vanha lähde", "tab": "golfliitot", "date": "2026-06-01"},
        {"url": "https://old.fi/2", "title": "Ilman suomennosta"},
    ], ensure_ascii=False), encoding="utf-8")
    assert store.import_legacy_json(conn, legacy) == 2
    # suomennettu -> analyzed, muu -> new
    assert len(store.pending_articles(conn)) == 1


# ---------------------------------------------------------------- sources
def test_sources_yaml_loads():
    sources, defaults = load_sources()
    assert len(sources) >= 30
    assert {s.tab for s in sources} == {"golfliitot", "urheilu_liitot", "media"}
    # jokaisella lähteellä vähintään yksi hakutapa (json_api/sitemap/vapaa GN-haku
    # mukaan lukien — media-lähteillä on vain google_news_query)
    for s in sources:
        assert (s.rss or s.html_url or s.json_api or s.sitemap
                or s.google_news_rss), f"{s.id}: ei hakutapaa"
    # google news -URL muodostuu oikein
    gn = next(s for s in sources if s.google_news)
    assert "news.google.com/rss/search" in gn.google_news_rss


# ---------------------------------------------------------------- media-välilehti
def test_media_sources_use_when_operator():
    """when: on pakollinen: ilman sitä Google News järjestää relevanssin mukaan
    ja tuoreet jutut jäävät sadan merkinnän ulkopuolelle."""
    sources, _ = load_sources()
    media = [s for s in sources if s.tab == config.MEDIA_TAB]
    assert media, "media-välilehdellä ei lähteitä"
    for s in media:
        assert s.google_news_query, f"{s.id}: media-lähde ilman hakulausetta"
        assert "when:" in s.google_news_query, f"{s.id}: hakulauseesta puuttuu when:"
        # site:-haku ohittaa when:-operaattorin ja palauttaa vuosien takaisia juttuja
        assert "site:" not in s.google_news_query, f"{s.id}: site:-haku ei toimi when:in kanssa"


def test_media_uses_the_same_windows_as_other_tabs(conn):
    """Medialla EI ole omia ikkunoita: sama ANALYZE_DAYS ja REPORT_DAYS kuin
    muilla. Erillinen MEDIA_DAYS haarautti storen turhaan (CASE WHEN tab),
    joten jos joku palauttaa sen, tämä testi kaatuu."""
    vanha = (datetime.date.today() - datetime.timedelta(days=20)).isoformat()
    media = _art(url="https://media.fi/a", title="Kolme viikkoa vanha mediajuttu")
    media.update(tab=config.MEDIA_TAB, source_id="media_golf", published=vanha)
    liitto = _art(url="https://liitto.fi/b", title="Yhtä vanha liiton juttu")
    liitto["published"] = vanha
    store.insert_new(conn, [media, liitto])

    # Kumpikaan ei mahdu analyysi-ikkunaan, eikä media saa poikkeusta
    assert store.pending_articles(conn) == []

    store.expire_old_pending(conn, days=config.ANALYZE_DAYS)
    tilat = {r["title"]: r["status"] for r in store.raw_articles(conn, days=3650)}
    assert tilat["Kolme viikkoa vanha mediajuttu"] == "expired"
    assert tilat["Yhtä vanha liiton juttu"] == "expired"


def test_media_article_visible_for_report_days(conn):
    """Media-juttu näkyy katsauksessa yhtä pitkään kuin liittojen jutut."""
    def lisaa(paivia, otsikko):
        a = _art(url=f"https://media.fi/{paivia}", title=otsikko)
        a.update(tab=config.MEDIA_TAB, source_id="media_golf",
                 published=(datetime.date.today()
                            - datetime.timedelta(days=paivia)).isoformat())
        store.insert_new(conn, [a])
        aid = next(x["id"] for x in store.pending_articles(conn)
                   if x["title"] == otsikko)
        store.save_analysis(conn, [{"article_id": aid, "relevant": True,
                                    "title_fi": otsikko, "summary_fi": "T",
                                    "category": "muu", "priority": "korkea",
                                    "themes": []}])

    lisaa(3, "Kolme päivää vanha")
    otsikot = [a["title"] for a in store.report_articles(conn, config.REPORT_DAYS)]
    assert "Kolme päivää vanha" in otsikot
    # Katsausikkunan ulkopuolella ei näy
    assert store.report_articles(conn, days=1) == []


def test_media_prompt_is_used_for_media_tab():
    """Media-välilehti ei saa valua golf-promptiin: kysymys on eri."""
    from src.analyze import _PROMPT_GOLF, _PROMPT_MEDIA, _PROMPT_SPORTS
    valinta = lambda tab: {"urheilu_liitot": _PROMPT_SPORTS,
                           config.MEDIA_TAB: _PROMPT_MEDIA}.get(tab, _PROMPT_GOLF)
    assert valinta(config.MEDIA_TAB) is _PROMPT_MEDIA
    assert valinta("golfliitot") is _PROMPT_GOLF
    assert valinta("urheilu_liitot") is _PROMPT_SPORTS
    # Portti ei saa mainita tasoa (CLAUDE.md:n rautainen sääntö)
    portit = _PROMPT_MEDIA.split("2. title_fi")[0]
    for taso in ("KORKEA", "KESKITASO", "MATALA"):
        assert taso not in portit, f"porttiosio mainitsee tason {taso}"


def test_media_dedup_ignores_source(conn):
    """Sama juttu eri lehdistä (ja eri hakusanasta) on yksi rivi medialla,
    mutta kaksi eri riviä liittovälilehdillä."""
    def media(src, title):
        a = _art(url=f"https://{src}.fi/{title[:5]}", title=title)
        a.update(tab=config.MEDIA_TAB, source_id=src, source_name=src)
        return a

    store.insert_new(conn, [media("iltalehti", "Golf tuottaa Suomelle 630 miljoonaa"),
                            media("is", "Golf tuottaa Suomelle 630 miljoonaa")])
    raw = store.raw_articles(conn, days=3650)
    assert len(raw) == 1, "sama otsikko eri lehdistä pitäisi yhdistyä medialla"

    # Liittovälilehdillä sama otsikko kahdesta liitosta säilyy kahtena juttuna
    a1 = _art(url="https://x.fi/1", title="Sama otsikko kahdesta liitosta")
    a2 = _art(url="https://y.fi/2", title="Sama otsikko kahdesta liitosta")
    a2["source_id"] = "s2"
    store.insert_new(conn, [a1, a2])
    liitot = [r for r in store.raw_articles(conn, days=3650)
              if r["tab"] == "golfliitot"]
    assert len(liitot) == 2


def test_conditional_publisher_exclusion():
    """Ehdollinen julkaisijakarsinta: pois paitsi jos otsikko pelastaa.

    Karsinta tehdään keruussa eikä promptissa, jotta se ei kuluta
    Gemini-kutsuja ja jotta sääntö näkyy lokista."""
    from src.fetch import _drop_excluded
    from src.sources import Source

    src = Source(id="media_golf", name="Haku: golf", tab=config.MEDIA_TAB,
                 country="Suomi", language="fi",
                 # Molemmat vartalot: suomen heikko aste ("liiton") ei osu
                 # fraasiin "liitto", ja juuri se muoto esiintyy kritiikissä.
                 exclude_publishers_unless={"golfpiste.com":
                                            ["golfliit", "liitto", "liito"]})
    jutut = [
        {"title": "Kalle Samooja palasi kilpailuihin", "source_name": "Golfpiste.com"},
        {"title": "Golfliitto uudistaa tasoitusjärjestelmän", "source_name": "Golfpiste.com"},
        {"title": "Liitolta moitteita kenttien kunnosta", "source_name": "Golfpiste.com"},
        {"title": "Liiton linjaus jakaa seuroja", "source_name": "Golfpiste.com"},
        {"title": "Kalle Samooja palasi kilpailuihin", "source_name": "Ilta-Sanomat"},
    ]
    kept, hylatty, ehdollinen = _drop_excluded(src, jutut)
    otsikot = [a["title"] for a in kept]
    assert "Golfliitto uudistaa tasoitusjärjestelmän" in otsikot
    assert "Liitolta moitteita kenttien kunnosta" in otsikot   # heikko aste
    assert "Liiton linjaus jakaa seuroja" in otsikot           # heikko aste
    # Sama juttu muusta mediasta jää, Golfpisteestä ei
    assert otsikot.count("Kalle Samooja palasi kilpailuihin") == 1
    assert (hylatty, ehdollinen) == (0, 1)
