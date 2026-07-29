"""Perus-yksikkötestit: otsikon siivous, päivämäärät, dedup, migraatio.

Ajo:  python -m pytest tests/ -q     (pip install pytest)
"""
import datetime
import json
import sqlite3

import pytest

from src import store
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
    # Päivämäärä suhteessa tähän päivään: pending_articles rajaa REPORT_DAYS-ikkunaan,
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
    assert {s.tab for s in sources} == {"golfliitot", "urheilu_liitot"}
    # jokaisella lähteellä vähintään yksi hakutapa
    for s in sources:
        assert s.rss or s.html_url or s.google_news, f"{s.id}: ei hakutapaa"
    # google news -URL muodostuu oikein
    gn = next(s for s in sources if s.google_news)
    assert "news.google.com/rss/search" in gn.google_news_rss
