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


# ---------------------------------------------------------------- store
@pytest.fixture()
def conn(tmp_path):
    c = store.connect(tmp_path / "test.db")
    yield c
    c.close()


def _art(url="https://x.fi/a", title="Testiotsikko pitkä kyllä"):
    return {"source_id": "s1", "source_name": "Lähde", "tab": "golfliitot",
            "country": "Suomi", "language": "fi", "title": title,
            "url": url, "published": "2026-07-01", "summary": "Ingressi"}


def test_insert_dedup(conn):
    assert store.insert_new(conn, [_art()]) == 1
    assert store.insert_new(conn, [_art()]) == 0          # sama url -> ei duplikaattia
    assert store.insert_new(conn, [_art(url="https://x.fi/b")]) == 1


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
    assert {s.tab for s in sources} == {"golfliitot", "golfmediat", "urheilu_liitot"}
    # jokaisella lähteellä vähintään yksi hakutapa
    for s in sources:
        assert s.rss or s.html_url or s.google_news, f"{s.id}: ei hakutapaa"
    # google news -URL muodostuu oikein
    gn = next(s for s in sources if s.google_news)
    assert "news.google.com/rss/search" in gn.google_news_rss
