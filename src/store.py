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
import re
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

-- Ihmisen tekemät prioriteettikorjaukset. Oma taulu, ei sarake articles-taulussa,
-- kahdesta syystä: korjaus säilyy vaikka artikkeli poistuisi RETENTION_DAYS-purgessa
-- (kalibrointiaineisto ei saa kadota), ja mallin oma arvio jää talteen vierelle
-- (was_priority), jotta katselmuksessa näkee mistä mihin arvio muuttui.
CREATE TABLE IF NOT EXISTS corrections (
    id           INTEGER PRIMARY KEY,
    url_hash     TEXT UNIQUE NOT NULL,   -- kohdeartikkeli
    title_key    TEXT,                   -- vara-avain, jos rivi hävisi dedupissa
    tab          TEXT,
    source_name  TEXT,
    url          TEXT,
    title        TEXT,                   -- alkukielinen otsikko (katselmusta varten)
    title_fi     TEXT,
    verdict      TEXT,                   -- priority | exclude | include
    priority     TEXT,                   -- ihmisen taso, jos verdict=priority
    was_priority TEXT,                   -- mallin taso korjaushetkellä
    was_status   TEXT,
    reason       TEXT,                   -- vapaa perustelu; katselmuksen tärkein kenttä
    created_at   TEXT,
    reviewed_at  TEXT                    -- asetettu, kun erä on käyty kalibroinnissa
);
CREATE INDEX IF NOT EXISTS idx_corrections_reviewed ON corrections(reviewed_at);
CREATE INDEX IF NOT EXISTS idx_corrections_title_key ON corrections(title_key);
"""


def url_hash(article: dict) -> str:
    key = article.get("url") or (article.get("source_id", "") + article.get("title", ""))
    return hashlib.md5(key.encode("utf-8")).hexdigest()


def title_key(article: dict) -> str:
    """Toinen dedup-avain: lähde + normalisoitu otsikko.

    Sama juttu saapuu joskus kahta reittiä: Google News antaa opaakin
    redirect-URLin ja suora RSS kanonisen URLin, joten url_hash eroaa ja
    juttu päätyy raporttiin kahdesti. Otsikko on näissä tapauksissa
    identtinen, joten se tunnistaa parin.

    Normalisointi pidetään tarkoituksella suppeana (pienet kirjaimet,
    välimerkit pois, välit tiivistetään): lähdenimen tai muun päätteen
    katkaisu yhdistäisi myös aidosti eri juttuja, joilla on sama alku.
    Avain on lähdekohtainen — kahden eri liiton uutinen samasta asiasta on
    kaksi eri juttua, ja niistä promptti valitsee yhden relevantiksi.

    POIKKEUS: media-välilehti. Siellä sama STT-/uutistoimistojuttu ilmestyy
    sellaisenaan Iltalehteen, Ilta-Sanomiin ja HS:ään, ja sama juttu osuu usein
    myös kahteen eri hakusanaan. Lähdekohtainen avain päästäisi ne kaikki läpi
    erillisinä riveinä. Siksi media-välilehdellä avain lasketaan PELKÄSTÄ
    otsikosta: siellä sama otsikko tarkoittaa aina samaa juttua, koska
    "lähde" ei ole julkaisija vaan hakulause.
    """
    title = (article.get("title") or "").casefold()
    title = re.sub(r"[^\w\s]", " ", title)
    title = re.sub(r"\s+", " ", title).strip()
    if not title:
        return ""
    scope = "" if article.get("tab") == config.MEDIA_TAB else article.get("source_id", "")
    return hashlib.md5(f"{scope}|{title}".encode("utf-8")).hexdigest()


def connect(db_path: Path = None) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path or config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(_SCHEMA)
    # Migraatiot vanhoille tietokannoille
    try:
        conn.execute("ALTER TABLE articles ADD COLUMN image TEXT DEFAULT ''")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # sarake on jo olemassa
    try:
        conn.execute("ALTER TABLE articles ADD COLUMN title_key TEXT DEFAULT ''")
        # Avain lasketaan myös vanhoille riveille, jotta dedup-historia
        # kattaa jo kerätyt jutut heti ensimmäisestä ajosta lähtien.
        for row in conn.execute("SELECT id, source_id, title FROM articles").fetchall():
            conn.execute("UPDATE articles SET title_key=? WHERE id=?",
                         (title_key(dict(row)), row["id"]))
        conn.commit()
    except sqlite3.OperationalError:
        pass  # sarake on jo olemassa
    conn.execute("CREATE INDEX IF NOT EXISTS idx_articles_title_key "
                 "ON articles(title_key)")
    conn.commit()
    return conn


def insert_new(conn: sqlite3.Connection, articles: list[dict]) -> int:
    """Lisää vain aiemmin näkemättömät. Palauttaa lisättyjen määrän.

    Dedup kahdella avaimella: url_hash (sama linkki) ja title_key (sama juttu
    eri reittiä). Toinen tarkistus tehdään kyselyllä eikä UNIQUE-rajoitteella,
    koska vanhoissa kannoissa on jo ennen korjausta syntyneitä pareja."""
    now = datetime.datetime.now().isoformat(timespec="seconds")
    inserted = 0
    for a in articles:
        tkey = title_key(a)
        if tkey and conn.execute(
                "SELECT 1 FROM articles WHERE title_key=? LIMIT 1", (tkey,)).fetchone():
            continue          # sama otsikko samasta lähteestä jo kannassa
        cur = conn.execute(
            """INSERT OR IGNORE INTO articles
               (url_hash, url, source_id, source_name, tab, country, language,
                title, summary, published, fetched_at, status, image, title_key)
               VALUES (?,?,?,?,?,?,?,?,?,?,?, 'new', ?,?)""",
            (url_hash(a), a.get("url"), a["source_id"], a["source_name"], a["tab"],
             a.get("country"), a.get("language"), a["title"], a.get("summary"),
             a.get("published"), now, a.get("image", ""), tkey),
        )
        inserted += cur.rowcount
    conn.commit()
    return inserted


# Artikkelin "tehollinen päivä": julkaisupäivä, tai jos sitä ei tiedetä,
# havaitsemispäivä. Tätä vasten mitataan sekä näkyvyys että vanheneminen.
_EFF_DATE = "COALESCE(NULLIF(published,''), substr(fetched_at,1,10))"


def _cutoff(days: int) -> str:
    return (datetime.date.today() - datetime.timedelta(days=days)).isoformat()


def expire_old_pending(conn: sqlite3.Connection, days: int) -> int:
    """Merkitse analyysi-ikkunaa vanhemmat analysoimattomat 'expired'-tilaan.

    Näitä ei näytetä eikä analysoida — säästää Gemini-kutsut tuoreille
    uutisille.

    Sama ikkuna kaikilla välilehdillä, media mukaan lukien."""
    cur = conn.execute(
        f"UPDATE articles SET status='expired' "
        f"WHERE status IN ('new','stale') AND {_EFF_DATE} < ?", (_cutoff(days),))
    conn.commit()
    return cur.rowcount


def pending_articles(conn: sqlite3.Connection) -> list[dict]:
    # 'new' = ei koskaan analysoitu, 'stale' = analysoitu mutta prompti muuttunut.
    # Vain ANALYZE_DAYS-ikkunan sisällä olevat: vanhempia ei kannata analysoida.
    # Huom. ikkuna on lyhyempi kuin katsauksen (REPORT_DAYS), eli katsauksessa
    # voi näkyä juttuja joita ei enää analysoida uudelleen. Sama kaikilla
    # välilehdillä, media mukaan lukien.
    # Huom. ikkuna on lyhyempi kuin katsauksen (REPORT_DAYS), eli katsauksessa
    # voi näkyä juttuja joita ei enää analysoida uudelleen.
    # Uudet ensin (tuoreimmat), sitten uudelleenarvioitavat.
    rows = conn.execute(
        f"SELECT * FROM articles WHERE status IN ('new','stale') "
        f"AND {_EFF_DATE} >= ? "
        f"ORDER BY CASE status WHEN 'new' THEN 0 ELSE 1 END, {_EFF_DATE} DESC, id",
        (_cutoff(config.ANALYZE_DAYS),),
    ).fetchall()
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
    # 'stale' näytetään edelleen vanhalla arviolla, kunnes uusi ehtii —
    # näin uudelleenanalyysi ei koskaan tyhjennä raporttia.
    rows = conn.execute(
        f"""SELECT * FROM articles
           WHERE status IN ('analyzed','stale')
             AND {_EFF_DATE} >= ?
           ORDER BY {_EFF_DATE} DESC, id DESC""",
        (_cutoff(days),),
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


def raw_articles(conn: sqlite3.Connection, days: int) -> list[dict]:
    """Kaikki löydetyt jutut raakalistaa varten — myös karsitut ja analysoimattomat.

    Raportti näyttää vain sen, minkä prompti päästi läpi. Raakalista näyttää
    mitä lähteistä ylipäänsä tuli, ilman priorisointia ja käännöksiä: näin
    suodatuksen ohi mennyt juttu on yhä löydettävissä. Statukset ovat mukana
    vain sen merkitsemiseen, mikä on jo katsauksessa.

    Kentät pidetään suppeina, koska koko lista upotetaan HTML-tiedostoon.
    Poikkeus: url_hash, title_key ja mallin priority ovat mukana, koska
    raakalistalta voi merkitä karsitun jutun kuuluvaksi katsaukseen — korjaus
    tarvitsee avaimen, ja katselmus tarvitsee tiedon siitä mitä malli arvioi.
    Näytettävät sarakkeet eivät muutu: lista pysyy karuna.

    Sama ikkuna kaikilla välilehdillä, media mukaan lukien.
    """
    rows = conn.execute(
        f"""SELECT source_name, country, tab, title, url, status, published,
                   url_hash, title_key, priority,
                   {_EFF_DATE} AS eff_date
           FROM articles
           WHERE {_EFF_DATE} >= ?
           ORDER BY eff_date DESC, source_name COLLATE NOCASE, id DESC""",
        (_cutoff(days),),
    ).fetchall()
    return [dict(r) for r in rows]


def last_run_finished_at(conn: sqlite3.Connection) -> str | None:
    """Edellisen (ennen tätä ajoa valmistuneen) ajon lopetusaika, raportin uutuusmerkintää varten."""
    row = conn.execute("SELECT finished_at FROM runs ORDER BY id DESC LIMIT 1").fetchone()
    return row["finished_at"] if row else None


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


def purge_missing_sources(conn: sqlite3.Connection, sources) -> int:
    """Poista artikkelit, joiden lähde ei ole enää sources.yamlissa."""
    ids = [s.id for s in sources]
    placeholders = ",".join("?" * len(ids))
    cur = conn.execute(
        f"DELETE FROM articles WHERE source_id NOT IN ({placeholders})", ids)
    conn.commit()
    return cur.rowcount


def purge_source(conn: sqlite3.Connection, source_id: str) -> int:
    """Poista lähteen kaikki artikkelit (esim. kun lähteen hakutapa on muuttunut)."""
    cur = conn.execute("DELETE FROM articles WHERE source_id=?", (source_id,))
    conn.commit()
    return cur.rowcount


def reset_analysis(conn: sqlite3.Connection, tab: str = None,
                   days: int = None) -> int:
    """Merkitse artikkelit uudelleenanalysoitaviksi promptin muututtua.

    analyzed -> stale: pysyy raportissa vanhalla arviolla, kunnes uusi ehtii
                       (raportti ei tyhjene).
    irrelevant -> new: arvioidaan uudelleen (ei näy ennen sitä).
    tab: jos annettu, vain kyseinen välilehti (säästää Gemini-kutsuja).

    Rajaus ANALYZE_DAYS-ikkunaan on tarkoituksellinen: pending_articles ei
    kuitenkaan poimi ikkunan ulkopuolisia, joten niiden merkitseminen ei
    tuottaisi uutta arviota — se vain veisi ne expire_old_pending-kierroksella
    'expired'-tilaan ja hukkaisi vanhan arvion turhaan. Ikkuna on siksi
    analyysi-, ei katsausikkuna: 6-7 pv vanhaa katsauksen juttua ei voi
    uudelleenanalysoida, ja sen merkitseminen vain tuhoaisi vanhan arvion."""
    cutoff = _cutoff(days if days is not None else config.ANALYZE_DAYS)
    where = f" AND {_EFF_DATE} >= ?"
    params: tuple = (cutoff,)
    if tab:
        where += " AND tab=?"
        params += (tab,)
    conn.execute(f"UPDATE articles SET status='stale' WHERE status='analyzed'{where}", params)
    cur = conn.execute(f"UPDATE articles SET status='new' WHERE status='irrelevant'{where}", params)
    conn.commit()
    # Palauta uudelleenarvioitavien kokonaismäärä
    q = f"SELECT COUNT(*) FROM articles WHERE status IN ('new','stale'){where}"
    return conn.execute(q, params).fetchone()[0]


def restore_stale(conn: sqlite3.Connection) -> int:
    """Palauta 'new'-tilaan jääneet, jo kertaalleen analysoidut artikkelit
    näkyviin (stale). Korjaa tilanteen, jossa reanalyze jätti raportin vajaaksi."""
    cur = conn.execute(
        "UPDATE articles SET status='stale' "
        "WHERE status='new' AND COALESCE(title_fi,'') != ''")
    conn.commit()
    return cur.rowcount


def dedupe_by_title(conn: sqlite3.Connection) -> int:
    """Siivoa ennen title_key-korjausta syntyneet kaksoiskappaleet.

    Samasta jutusta on kannassa useita rivejä, kun lähde on tarjonnut sen sekä
    Google News -redirectinä että suorana linkkinä. Kustakin ryhmästä jää yksi:

      1. elinkaaressa pisimmällä oleva (analysoitu työ ei mene hukkaan)
      2. tasatilanteessa suora linkki ennen Google News -redirectiä
      3. viimeisenä pienin id

    Palauttaa poistettujen rivien määrän. Turvallinen ajaa uudelleen."""
    order = {"analyzed": 0, "stale": 1, "irrelevant": 2, "new": 3, "expired": 4}
    groups: dict[str, list[sqlite3.Row]] = {}
    for row in conn.execute(
            "SELECT id, title_key, status, url FROM articles WHERE title_key != ''"):
        groups.setdefault(row["title_key"], []).append(row)

    removed = 0
    for rows in groups.values():
        if len(rows) < 2:
            continue
        rows.sort(key=lambda r: (order.get(r["status"], 9),
                                 "news.google.com" in (r["url"] or ""),
                                 r["id"]))
        for r in rows[1:]:
            conn.execute("DELETE FROM articles WHERE id=?", (r["id"],))
            removed += 1
    conn.commit()
    return removed


def purge_old(conn: sqlite3.Connection, days: int) -> int:
    """Poista hyvin vanhat artikkelit kannasta kokonaan. Dedup-historia
    säilyy RETENTION_DAYS-ikkunan ajan, jottei vanha uutinen palaa uutena."""
    cur = conn.execute(
        "DELETE FROM articles WHERE fetched_at < ?", (_cutoff(days),))
    conn.commit()
    return cur.rowcount


# ------------------------------------------------------- ihmisen korjaukset
# Kolme korjaustyyppiä. Kaikki ovat DETERMINISTISIÄ: ne eivät kutsu Geminiä
# eivätkä muuta promptia, vaan pakottavat yhden artikkelin arvion. Promptin ja
# porttien päivitys on erillinen, käsin tehtävä kalibrointikierros — sitä varten
# korjaukset kertyvät tähän tauluun (ks. pending_corrections).
#
#   priority  ihmisen taso voittaa mallin tason
#   exclude   "ei kuulu katsaukseen"  -> irrelevant
#   include   "olisi pitänyt olla mukana" (raakalistalta) -> analyzed
_VERDICTS = ("priority", "exclude", "include")
_PRIORITIES = ("korkea", "keskitaso", "matala")

_CORRECTION_FIELDS = (
    "url_hash", "title_key", "tab", "source_name", "url", "title", "title_fi",
    "verdict", "priority", "was_priority", "was_status", "reason",
)


def save_corrections(conn: sqlite3.Connection, items: list[dict]) -> tuple[int, int]:
    """Tallenna raportista viedyt korjaukset. Palauttaa (uusia, päivitettyjä).

    Avain on url_hash: saman jutun uusi korjaus korvaa vanhan, koska viimeinen
    arvio on aina se joka on voimassa. Korvaus nollaa reviewed_at:n — muuten
    jo katselmoidun jutun uusi korjaus jäisi seuraavan kierroksen ulkopuolelle.
    """
    now = datetime.datetime.now().isoformat(timespec="seconds")
    added = updated = 0
    for it in items:
        h = (it.get("url_hash") or "").strip()
        verdict = (it.get("verdict") or "").strip()
        if not h or verdict not in _VERDICTS:
            log.warning("Ohitettu korjaus: puutteellinen url_hash tai verdict (%r)", verdict)
            continue
        prio = (it.get("priority") or "").strip()
        if prio and prio not in _PRIORITIES:
            log.warning("Ohitettu korjaus %s: tuntematon prioriteetti %r", h[:8], prio)
            continue
        vals = {k: (it.get(k) or "") for k in _CORRECTION_FIELDS}
        vals["url_hash"], vals["verdict"], vals["priority"] = h, verdict, prio
        existed = conn.execute(
            "SELECT 1 FROM corrections WHERE url_hash=?", (h,)).fetchone() is not None
        cols = ", ".join(_CORRECTION_FIELDS)
        marks = ", ".join("?" * len(_CORRECTION_FIELDS))
        conn.execute(
            f"""INSERT INTO corrections ({cols}, created_at, reviewed_at)
                VALUES ({marks}, ?, NULL)
                ON CONFLICT(url_hash) DO UPDATE SET
                    verdict=excluded.verdict, priority=excluded.priority,
                    reason=excluded.reason, was_priority=excluded.was_priority,
                    was_status=excluded.was_status, title_key=excluded.title_key,
                    created_at=excluded.created_at, reviewed_at=NULL""",
            tuple(vals[k] for k in _CORRECTION_FIELDS) + (it.get("created_at") or now,),
        )
        updated += existed
        added += not existed
    conn.commit()
    return added, updated


def apply_corrections(conn: sqlite3.Connection) -> int:
    """Pakota ihmisen korjaukset artikkeleihin. Palauttaa muuttuneiden rivien määrän.

    Ajetaan ANALYYSIN JÄLKEEN joka ajossa, ei kertaluontoisena UPDATEna: muuten
    tuore Gemini-arvio (tai --reanalyze) kirjoittaisi korjauksen yli heti
    seuraavassa ajossa. Idempotentti — turvallinen ajaa kuinka usein tahansa.

    Kohde etsitään ensin url_hashilla ja sitten title_keyllä: dedup jättää
    parista vain toisen rivin, joten korjattu rivi voi hävitä ja sen kaksonen
    jäädä eloon.
    """
    changed = 0
    for c in conn.execute("SELECT * FROM corrections").fetchall():
        row = conn.execute(
            "SELECT id, status, priority, COALESCE(title_fi,'') AS title_fi "
            "FROM articles WHERE url_hash=?", (c["url_hash"],)).fetchone()
        if row is None and c["title_key"]:
            row = conn.execute(
                "SELECT id, status, priority, COALESCE(title_fi,'') AS title_fi "
                "FROM articles WHERE title_key=? ORDER BY id LIMIT 1",
                (c["title_key"],)).fetchone()
        if row is None:
            continue                      # juttu on purgattu tai poistettu lähteen mukana

        status, priority = row["status"], row["priority"]
        if c["verdict"] == "exclude":
            if status in ("analyzed", "stale", "new"):
                status = "irrelevant"
        elif c["verdict"] in ("priority", "include"):
            if c["priority"]:
                priority = c["priority"]
            # Käännös puuttuu vain jos juttua ei ole koskaan analysoitu. Silloin
            # status jätetään ennalleen: juttu analysoidaan seuraavassa ajossa ja
            # tämä sama korjaus nostaa sen mukaan analyysin jälkeen.
            if status in ("irrelevant", "expired") and row["title_fi"]:
                status = "analyzed"

        if (status, priority) != (row["status"], row["priority"]):
            conn.execute("UPDATE articles SET status=?, priority=? WHERE id=?",
                         (status, priority, row["id"]))
            changed += 1
    conn.commit()
    return changed


def pending_corrections(conn: sqlite3.Connection) -> list[dict]:
    """Katselmoimattomat korjaukset, vanhin ensin — kalibrointikierroksen aineisto."""
    rows = conn.execute(
        "SELECT * FROM corrections WHERE reviewed_at IS NULL "
        "ORDER BY created_at, id").fetchall()
    return [dict(r) for r in rows]


def mark_corrections_reviewed(conn: sqlite3.Connection) -> int:
    """Merkitse katselmoimattomat käsitellyiksi promptin päivityksen jälkeen.

    Rivit jäävät kantaan: sama erä on promptimuutoksen jälkeen se testiaineisto,
    jota vasten muutoksen osuvuuden voi mitata."""
    now = datetime.datetime.now().isoformat(timespec="seconds")
    cur = conn.execute(
        "UPDATE corrections SET reviewed_at=? WHERE reviewed_at IS NULL", (now,))
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
                title_fi, summary_fi, category, priority, themes, title_key)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (url_hash(row), row["url"], row["source_id"],
             a.get("source_name") or a.get("source") or "", tab,
             a.get("country") or "", a.get("language") or "",
             row["title"], a.get("summary") or "",
             a.get("published") or a.get("date") or "", now, status,
             title_fi, a.get("summary_fi") or "", a.get("category") or "",
             a.get("priority") or "",
             json.dumps(a.get("themes") or [], ensure_ascii=False),
             title_key(row)),
        )
        imported += cur.rowcount
    conn.commit()
    log.info("Tuotu %d artikkelia tiedostosta %s", imported, path)
    return imported
