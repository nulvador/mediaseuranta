"""Artikkelien keruu: RSS → HTML → Google News, rinnakkain, per-lähde-timeout.

Jokainen lähde palauttaa (artikkelit, health-dict). Yhden lähteen virhe ei
koskaan kaada ajoa — se näkyy vain lähdeterveysraportissa.
"""
import concurrent.futures
import datetime
import logging
import re
from typing import Optional
from urllib.parse import urljoin, urlparse

import feedparser
import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateparser

from . import config
from .sources import Source

log = logging.getLogger(__name__)

MIN_TITLE_LEN = 12
_GN_SUFFIX = re.compile(r"\s+[-–|]\s+[^-–|]{2,40}$")


# ---------------------------------------------------------------- helpers
def clean_title(title: str, google_news: bool = False) -> str:
    """Siivoa otsikko: whitespace + Google Newsin ' - Lähde' -suffiksi."""
    title = re.sub(r"\s+", " ", title or "").strip()
    if google_news:
        title = _GN_SUFFIX.sub("", title)
    return title


def parse_date(text: str) -> Optional[datetime.date]:
    if not text:
        return None
    text = text.strip()
    try:
        return dateparser.parse(text, fuzzy=True, dayfirst=True).date()
    except (ValueError, OverflowError, TypeError):
        return None


def _http_get(url: str) -> Optional[requests.Response]:
    try:
        r = requests.get(url, headers=config.HTTP_HEADERS,
                         timeout=config.FETCH_TIMEOUT, allow_redirects=True)
        r.raise_for_status()
        return r
    except requests.RequestException as e:
        log.debug("fetch failed %s: %s", url, e)
        return None


def _article(source: Source, title: str, url: str, date_str: str, summary: str) -> dict:
    return {
        "source_id": source.id,
        "source_name": source.name,
        "tab": source.tab,
        "country": source.country,
        "language": source.language,
        "title": title,
        "url": url,
        "published": date_str,
        "summary": (summary or "")[:400],
    }


# ---------------------------------------------------------------- RSS
def fetch_rss(source: Source, url: str, since: datetime.date,
              google_news: bool = False) -> tuple[list[dict], int]:
    """Palauttaa (ikkunaan osuvat artikkelit, syötteen merkintöjen kokonaismäärä)."""
    resp = _http_get(url)
    if resp is None:
        return [], -1          # -1 = syöte ei vastannut
    feed = feedparser.parse(resp.content)
    total = len(feed.entries)
    articles = []
    for entry in feed.entries[: config.MAX_PER_SOURCE * 3]:
        title = clean_title(entry.get("title", ""), google_news=google_news)
        link = (entry.get("link") or "").strip()
        if not title or len(title) < MIN_TITLE_LEN or not link:
            continue

        # Google News site:-haku kattaa myös alidomainit (esim.
        # performance.golf.at) -> hyväksy vain pääsivusto ja www.
        if google_news and source.google_news:
            src_href = (entry.get("source") or {}).get("href") or ""
            host = urlparse(src_href).netloc.lower()
            dom = source.google_news.lower()
            if host and host not in (dom, f"www.{dom}"):
                continue

        date_obj = None
        for key in ("published_parsed", "updated_parsed"):
            t = entry.get(key)
            if t:
                date_obj = datetime.date(t.tm_year, t.tm_mon, t.tm_mday)
                break
        if date_obj is None:
            date_obj = parse_date(entry.get("published") or entry.get("updated") or "")
        if date_obj is None or date_obj < since:
            continue

        summary = ""
        if entry.get("summary"):
            summary = BeautifulSoup(entry["summary"], "html.parser").get_text(" ", strip=True)

        articles.append(_article(source, title, link, date_obj.isoformat(), summary))
        if len(articles) >= config.MAX_PER_SOURCE:
            break
    return articles, total


# ---------------------------------------------------------------- HTML
def _select_first(el, selectors: list):
    for sel in selectors or []:
        found = el.select_one(sel)
        if found:
            return found
    return None


def fetch_html(source: Source, since: datetime.date) -> tuple[list[dict], int]:
    """Palauttaa (ikkunaan osuvat artikkelit, löytyneiden konttien määrä)."""
    resp = _http_get(source.html_url)
    if resp is None:
        return [], -1          # -1 = sivu ei vastannut
    resp.encoding = resp.apparent_encoding or "utf-8"
    soup = BeautifulSoup(resp.text, "lxml")
    for tag in soup.select("nav, header, footer, aside, .sidebar, .menu, .navigation, script, style"):
        tag.decompose()

    sel = source.html_selectors
    containers = []
    for s in sel.get("container", []):
        containers = soup.select(s)
        if containers:
            break
    if not containers:
        return [], 0           # sivu vastasi, mutta selektorit eivät osuneet

    articles = []
    for c in containers:
        title_el = _select_first(c, sel.get("title", []))
        if title_el is None:
            continue
        title = clean_title(title_el.get_text())
        if len(title) < MIN_TITLE_LEN:
            continue

        link_el = c.find("a", href=True) or (title_el.find("a", href=True) if hasattr(title_el, "find") else None)
        if link_el is None and c.name == "a" and c.get("href"):
            link_el = c
        if link_el is None:
            continue
        url = urljoin(source.html_url, link_el["href"])

        date_obj = None
        date_el = _select_first(c, sel.get("date", []))
        if date_el is not None:
            for attr in ("datetime", "data-date", "content"):
                if date_el.get(attr):
                    date_obj = parse_date(date_el[attr])
                    if date_obj:
                        break
            if date_obj is None:
                date_obj = parse_date(date_el.get_text())
        if date_obj is not None and date_obj < since:
            continue
        date_str = date_obj.isoformat() if date_obj else ""

        summary_el = _select_first(c, sel.get("summary", []))
        summary = summary_el.get_text(" ", strip=True) if summary_el else ""

        articles.append(_article(source, title, url, date_str, summary))
        if len(articles) >= config.MAX_PER_SOURCE:
            break
    return articles, len(containers)


# ---------------------------------------------------------------- orchestration
def fetch_source(source: Source, since: datetime.date) -> tuple[list[dict], dict]:
    """Kokeile hakutapoja järjestyksessä. Palauta (artikkelit, health)."""
    health = {"source_id": source.id, "source_name": source.name, "tab": source.tab,
              "method": None, "count": 0, "error": ""}
    methods = []
    if source.rss:
        methods.append(("rss", lambda: fetch_rss(source, source.rss, since)))
    if source.html_url:
        methods.append(("html", lambda: fetch_html(source, since)))
    if source.google_news_rss:
        methods.append(("google_news",
                        lambda: fetch_rss(source, source.google_news_rss, since, google_news=True)))

    notes = []
    for name, fn in methods:
        try:
            articles, total = fn()
        except Exception as e:  # noqa: BLE001 — yksittäinen lähde ei saa kaataa ajoa
            notes.append(f"{name}: virhe ({e})")
            log.warning("%s %s epäonnistui: %s", source.id, name, e)
            continue
        if articles:
            health.update(method=name, count=len(articles))
            return articles, health
        if total == -1:
            notes.append(f"{name}: ei vastausta")
        elif total == 0:
            notes.append(f"{name}: tyhjä (rikki tai ei sisältöä)")
        else:
            notes.append(f"{name}: OK, {total} merkintää mutta ei yhtään keruuikkunassa")

    health["error"] = "; ".join(notes) or "ei hakutapoja"
    return [], health


def fetch_all(sources: list[Source], since: datetime.date) -> tuple[list[dict], list[dict]]:
    """Hae kaikki lähteet rinnakkain. Palauta (artikkelit, health-lista)."""
    all_articles: list[dict] = []
    healths: list[dict] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=config.MAX_WORKERS) as ex:
        futures = {ex.submit(fetch_source, s, since): s for s in sources}
        for fut in concurrent.futures.as_completed(futures):
            src = futures[fut]
            try:
                articles, health = fut.result()
            except Exception as e:  # noqa: BLE001
                articles, health = [], {"source_id": src.id, "source_name": src.name,
                                        "tab": src.tab, "method": None, "count": 0,
                                        "error": str(e)}
            healths.append(health)
            all_articles.extend(articles)
            status = f"{health['count']} kpl ({health['method']})" if health["count"] else f"0 kpl — {health['error']}"
            log.info("  %-22s %s", src.id, status)

    healths.sort(key=lambda h: h["source_id"])
    return all_articles, healths
