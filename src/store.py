"""SQLite-tallennus: dedup, tila-checkpointit, migraatio vanhasta articles.json:sta.

Artikkelin status-elinkaari:
    new        kerätty, ei vielä analysoitu   (keskeytynyt ajo -> jatkuu seuraavassa)
    analyzed   Gemini-analyysi tallennettu
    irrelevant Gemini totesi epärelevantiksi (ei näytetä raportissa)
"""
import datetime
import hashlib
import json
import logging
import sqlite3
from pathlib import Path

from . import config

log = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
    id          INTEGER PRIMARY KEY,
    url_hash    TEXT UNIQUE NOT NULL,
    url         TEXT,
    source_id   TEXT,
    source_name TEXT,
    tab         TEXT,
    country     TEXT,
    language    TEXT,
    title       TEXT,
    summary     TEXT,
    published   TEXT,
    fetched_at  TEXT,
    status      TEXT DEFAULT 'new',
    title_fi    TEXT,
    summary_fi  TEXT,
    category    TEXT,
    priority    TEXT,
    themes      TEXT
);
CREATE INDEX IF NOT EXISTS idx_articles_status ON articles(status);
CREATE INDEX IF NOT EXISTS idx_articles_published ON articles(published);

CREATE TABLE IF NOT EXISTS runs (
    id            INTEGER PRIMARY KEY,
    started_at    TEXT,
    finished_at   TEXT,
    new_articles  INTEGER,
    analyzed      INTEGER,
    failed_batches INTEGER,
    health_json   TEXT
);
"""


def url_hash(article: dict) -> str:
    key = article.get("url") or (article.get("source_id", "") + article.get("title", ""))
    return hashlib.md5(key.encode("utf-8")).hexdigest()


def connect(db_path: Path = None) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path or config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(_SCHEMA)
    return conn


def insert_new(conn: sqlite3.Connection, articles: list[dict]) -> int:
    """Lisää vain aiemmin näkemättömät. Palauttaa lisättyjen määrän."""
    now = datetime.datetime.now().isoformat(timespec="seconds")
    inserted = 0
    for a in articles:
        cur = conn.execute(
            """INSERT OR IGNORE INTO articles
               (url_hash, url, source_id, source_name, tab, country, language,
                title, summary, published, fetched_at, status)
               VALUES (?,?,?,?,?,?,?,?,?,?,?, 'new')""",
            (url_hash(a), a.get("url"), a["source_id"], a["source_name"], a["tab"],
             a.get("country"), a.get("language"), a["title"], a.get("summary"),
             a.get("published"), now),
        )
        inserted += cur.rowcount
    conn.commit()
    return inserted


def pending_articles(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT * FROM articles WHERE status='new' ORDER BY tab, id").fetchall()
    return [dict(r) for r in rows]


def save_analysis(conn: sqlite3.Connection, results: list[dict]) -> None:
    """Checkpoint: tallenna yhden erän analyysitulokset heti."""
    for r in results:
        status = "analyzed" if r.get("relevant", True) else "irrelevant"
        conn.execute(
            """UPDATE articles SET status=?, title_fi=?, summary_fi=?,
               category=?, priority=?, themes=? WHERE id=?""",
            (status, r.get("title_fi"), r.get("summary_fi"), r.get("category"),
             r.get("priority"), json.dumps(r.get("themes") or [], ensure_ascii=False),
             r["article_id"]),
        )
    conn.commit()


def report_articles(conn: sqlite3.Connection, days: int) -> list[dict]:
    cutoff = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
    rows = conn.execute(
        """SELECT * FROM articles
           WHERE status='analyzed'
             AND (published >= ? OR published IS NULL OR published = '')
           ORDER BY published DESC, id DESC""",
        (cutoff,),
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["themes"] = json.loads(d.get("themes") or "[]")
        except json.JSONDecodeError:
            d["themes"] = []
        out.append(d)
    return out


def log_run(conn, started_at, new_articles, analyzed, failed_batches, healths) -> None:
    conn.execute(
        """INSERT INTO runs (started_at, finished_at, new_articles, analyzed,
                             failed_batches, health_json)
           VALUES (?,?,?,?,?,?)""",
        (started_at, datetime.datetime.now().isoformat(timespec="seconds"),
         new_articles, analyzed, failed_batches, json.dumps(healths, ensure_ascii=False)),
    )
    conn.commit()


def sync_tabs(conn: sqlite3.Connection, sources) -> int:
    """Päivitä vanhojen artikkelien tab vastaamaan sources.yamlin nykytilaa."""
    changed = 0
    for s in sources:
        cur = conn.execute(
            "UPDATE articles SET tab=? WHERE source_id=? AND tab != ?",
            (s.tab, s.id, s.tab))
        changed += cur.rowcount
    conn.commit()
    return changed


def reset_analysis(conn: sqlite3.Connection) -> int:
    """Palauta kaikki analysoidut/hylätyt 'new'-tilaan uudelleenanalyysiä varten."""
    cur = conn.execute(
        "UPDATE articles SET status='new' WHERE status IN ('analyzed','irrelevant')")
    conn.commit()
    return cur.rowcount


# ---------------------------------------------------------------- migraatio
def import_legacy_json(conn: sqlite3.Connection, path: Path) -> int:
    """Tuo vanhan projektin articles.json (lista tai {all_articles: [...]}).

    Tunnistaa sekä vanhan Gemini-version että golf_news_monitor.py:n kentät.
    Tuodut merkitään suoraan 'analyzed' jos niillä on suomennos, muuten 'new'.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("all_articles") or data.get("articles") or []
    if not isinstance(data, list):
        raise ValueError("Tuntematon JSON-rakenne")

    now = datetime.datetime.now().isoformat(timespec="seconds")
    imported = 0
    for a in data:
        title_fi = a.get("title_fi") or ""
        status = "analyzed" if title_fi else "new"
        tab = a.get("tab") or ("golfliitot" if a.get("region") else a.get("tab", "golfliitot"))
        row = {
            "url": a.get("url") or a.get("link"),
            "source_id": a.get("source_id") or a.get("source") or "legacy",
            "title": a.get("title") or "",
        }
        cur = conn.execute(
            """INSERT OR IGNORE INTO articles
               (url_hash, url, source_id, source_name, tab, country, language,
                title, summary, published, fetched_at, status,
                title_fi, summary_fi, category, priority, themes)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (url_hash(row), row["url"], row["source_id"],
             a.get("source_name") or a.get("source") or "", tab,
             a.get("country") or "", a.get("language") or "",
             row["title"], a.get("summary") or "",
             a.get("published") or a.get("date") or "", now, status,
             title_fi, a.get("summary_fi") or "", a.get("category") or "",
             a.get("priority") or "",
             json.dumps(a.get("themes") or [], ensure_ascii=False)),
        )
        imported += cur.rowcount
    conn.commit()
    log.info("Tuotu %d artikkelia tiedostosta %s", imported, path)
    return imported
