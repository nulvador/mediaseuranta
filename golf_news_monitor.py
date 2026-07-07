#!/usr/bin/env python3
"""
Golf Federation News Monitor — HTML Scraper
============================================
Kerää kaikki artikkelit suoraan liittojen sivustoilta (ei web search).
Pohjoismaat + Eurooppa, viimeinen 14 päivää.

Käyttö:
    pip install requests beautifulsoup4 lxml python-dateutil
    export ANTHROPIC_API_KEY="sk-ant-..."
    python3 golf_news_monitor.py

Tuottaa:
    output/golf_digest_YYYY-MM-DD.json   → dashboardille
    output/golf_digest_YYYY-MM-DD.html   → sähköpostiin / selaimeen
"""

import json
import hashlib
import datetime
import os
import sys
import time
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse

try:
    import requests
    from bs4 import BeautifulSoup
    from dateutil import parser as dateparser
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install",
                           "requests", "beautifulsoup4", "lxml",
                           "python-dateutil", "-q"])
    import requests
    from bs4 import BeautifulSoup
    from dateutil import parser as dateparser

# ============================================================
# CONFIG
# ============================================================
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL   = "claude-sonnet-4-20250514"
LOOKBACK_DAYS     = 14
OUTPUT_DIR        = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; GolfFederationMonitor/2.0; "
        "+https://golf.fi; media monitoring for Suomen Golfliitto)"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en,fi,sv,no,da,de,fr,es,nl,is",
}

# ============================================================
# SOURCE MODEL
# ============================================================
@dataclass
class NewsSource:
    id:          str
    name:        str
    country:     str
    region:      str        # "nordic" | "europe"
    news_url:    str        # direct URL to news listing page
    language:    str
    # CSS selectors — tried in order, first match wins
    sel_container: list     # wraps one article item
    sel_title:     list     # article title
    sel_link:      list     # <a> tag (may be same as container)
    sel_date:      list     # date element
    sel_summary:   list     # teaser/excerpt text
    # Optional RSS fallback
    rss_url:       str = ""

# ============================================================
# SOURCE REGISTRY — Pohjoismaat + Eurooppa
# ============================================================
SOURCES = [
    # ── POHJOISMAAT ────────────────────────────────────────
    NewsSource(
        id="sgf_sweden", name="Svenska Golfförbundet (SGF)",
        country="Ruotsi", region="nordic",
        news_url="https://golf.se/forbundet/nyheter/",
        language="sv",
        sel_container=["article.news-item", ".news-list__item", ".article-card", "article", ".list-item--news"],
        sel_title=["h2", "h3", ".news-item__title", ".article-card__title", ".title"],
        sel_link=["a"],
        sel_date=["time", ".news-item__date", ".meta__date", ".date"],
        sel_summary=[".news-item__preamble", ".article-card__text", "p"],
        rss_url="https://golf.se/feed/",
    ),
    NewsSource(
        id="dgu_denmark", name="Dansk Golf Union (DGU)",
        country="Tanska", region="nordic",
        news_url="https://www.danskgolfunion.dk/golf-klub-danmark-nyheder",
        language="da",
        sel_container=[".field--name-field-news-items .field__item", "article", ".news-item", ".card", ".teaser"],
        sel_title=["h2", "h3", ".card-title", ".teaser__title"],
        sel_link=["a"],
        sel_date=["time", ".date", ".teaser__date"],
        sel_summary=[".teaser__body", ".card-text", "p"],
    ),
    NewsSource(
        id="dgu_press", name="Dansk Golf Union – Pressemeddelelser",
        country="Tanska", region="nordic",
        news_url="https://www.danskgolfunion.dk/pressemeddelelser",
        language="da",
        sel_container=["article", ".news-item", ".card", ".teaser", ".list-item"],
        sel_title=["h2", "h3", ".card-title"],
        sel_link=["a"],
        sel_date=["time", ".date"],
        sel_summary=["p", ".excerpt"],
    ),
    NewsSource(
        id="ngf_norway", name="Norges Golfforbund (NGF)",
        country="Norja", region="nordic",
        news_url="https://www.golfforbundet.no/ngf-nytt/",
        language="no",
        sel_container=["article", ".article-list-item", ".news-card", ".list-item"],
        sel_title=["h2", "h3", "h4", ".article-title", ".title"],
        sel_link=["a"],
        sel_date=["time", ".date", ".publish-date", ".meta-date"],
        sel_summary=[".ingress", ".excerpt", "p"],
        rss_url="https://www.golfforbundet.no/feed/",
    ),
    NewsSource(
        id="ngf_press", name="Norges Golfforbund – Pressemeldinger",
        country="Norja", region="nordic",
        news_url="https://www.golfforbundet.no/pressemeldinger/",
        language="no",
        sel_container=["article", ".article-list-item", ".list-item"],
        sel_title=["h2", "h3", "h4", ".title"],
        sel_link=["a"],
        sel_date=["time", ".date", ".publish-date"],
        sel_summary=[".ingress", ".excerpt", "p"],
    ),
    NewsSource(
        id="gsi_iceland", name="Golf Sambands Íslands (GSÍ)",
        country="Islanti", region="nordic",
        news_url="https://www.golf.is/frettir/",
        language="is",
        sel_container=["article", ".news-item", ".frettir-item", ".card"],
        sel_title=["h2", "h3", ".title"],
        sel_link=["a"],
        sel_date=["time", ".date"],
        sel_summary=["p", ".excerpt"],
    ),
    NewsSource(
        id="sterf", name="STERF (Scandinavian Turfgrass Research)",
        country="Pohjoismaat", region="nordic",
        news_url="https://sterf.org/news/",
        language="en",
        sel_container=["article", ".post", ".entry", ".news-item"],
        sel_title=["h2", "h3", ".entry-title", ".post-title"],
        sel_link=["a"],
        sel_date=["time", ".entry-date", ".post-date", ".date"],
        sel_summary=[".entry-summary", ".excerpt", "p"],
        rss_url="https://sterf.org/feed/",
    ),

    # ── EUROOPPA ───────────────────────────────────────────
    NewsSource(
        id="ega", name="European Golf Association (EGA)",
        country="Eurooppa", region="europe",
        news_url="https://www.ega-golf.ch/news-and-media",
        language="en",
        sel_container=[".views-row", "article", ".news-item", ".card"],
        sel_title=["h2", "h3", ".field--name-title", ".card-title"],
        sel_link=["a"],
        sel_date=["time", ".field--name-field-date", ".date"],
        sel_summary=[".field--name-body", ".card-text", "p"],
    ),
    NewsSource(
        id="england_golf", name="England Golf",
        country="Englanti", region="europe",
        news_url="https://www.englandgolf.org/news/",
        language="en",
        sel_container=["article", ".news-card", ".news-item", ".card"],
        sel_title=["h2", "h3", ".news-card__title", ".card-title"],
        sel_link=["a"],
        sel_date=["time", ".news-card__date", ".date"],
        sel_summary=[".news-card__excerpt", ".card-text", "p"],
        rss_url="https://www.englandgolf.org/feed/",
    ),
    NewsSource(
        id="scottish_golf", name="Scottish Golf",
        country="Skotlanti", region="europe",
        news_url="https://www.scottishgolf.org/news/",
        language="en",
        sel_container=["article", ".news-item", ".card", ".post"],
        sel_title=["h2", "h3", ".entry-title"],
        sel_link=["a"],
        sel_date=["time", ".entry-date", ".date"],
        sel_summary=[".entry-summary", "p"],
        rss_url="https://www.scottishgolf.org/feed/",
    ),
    NewsSource(
        id="golf_ireland", name="Golf Ireland",
        country="Irlanti", region="europe",
        news_url="https://www.golfireland.ie/news",
        language="en",
        sel_container=["article", ".news-item", ".card", ".media-item"],
        sel_title=["h2", "h3", ".card-title"],
        sel_link=["a"],
        sel_date=["time", ".date"],
        sel_summary=["p", ".excerpt"],
        rss_url="https://www.golfireland.ie/feed",
    ),
    NewsSource(
        id="dgv_germany", name="Deutscher Golf Verband (DGV)",
        country="Saksa", region="europe",
        news_url="https://www.golf.de/publish/dgv-aktuell/",
        language="de",
        sel_container=["article", ".teaser", ".news-item", ".card"],
        sel_title=["h2", "h3", ".teaser-title", ".card-title"],
        sel_link=["a"],
        sel_date=["time", ".date", ".teaser-date"],
        sel_summary=[".teaser-text", ".card-text", "p"],
    ),
    NewsSource(
        id="ffgolf", name="Fédération française de golf (FFGolf)",
        country="Ranska", region="europe",
        news_url="https://www.ffgolf.org/Actus",
        language="fr",
        sel_container=["article", ".actu-item", ".news-item", ".card"],
        sel_title=["h2", "h3", ".actu-title", ".card-title"],
        sel_link=["a"],
        sel_date=["time", ".date", ".actu-date"],
        sel_summary=[".actu-text", "p"],
    ),
    NewsSource(
        id="ngf_netherlands", name="Nederlandse Golf Federatie (NGF)",
        country="Hollanti", region="europe",
        news_url="https://www.ngf.nl/nieuws/",
        language="nl",
        sel_container=["article", ".news-item", ".card", ".nieuws-item"],
        sel_title=["h2", "h3", ".card-title"],
        sel_link=["a"],
        sel_date=["time", ".date"],
        sel_summary=["p", ".excerpt"],
        rss_url="https://www.ngf.nl/feed/",
    ),
    NewsSource(
        id="rfeg_spain", name="Real Federación Española de Golf (RFEG)",
        country="Espanja", region="europe",
        news_url="https://www.rfegolf.es/Noticias",
        language="es",
        sel_container=["article", ".news-item", ".card", ".noticia"],
        sel_title=["h2", "h3", ".card-title"],
        sel_link=["a"],
        sel_date=["time", ".date"],
        sel_summary=["p", ".excerpt"],
    ),
    NewsSource(
        id="fig_italy", name="Federazione Italiana Golf (FIG)",
        country="Italia", region="europe",
        news_url="https://www.federgolf.it/news/",
        language="it",
        sel_container=["article", ".news-item", ".card", ".notizia"],
        sel_title=["h2", "h3", ".card-title"],
        sel_link=["a"],
        sel_date=["time", ".date"],
        sel_summary=["p", ".excerpt"],
    ),
    NewsSource(
        id="ogv_austria", name="Österreichischer Golf-Verband (ÖGV)",
        country="Itävalta", region="europe",
        news_url="https://www.golf.at/news/",
        language="de",
        sel_container=["article", ".news-item", ".card"],
        sel_title=["h2", "h3", ".card-title"],
        sel_link=["a"],
        sel_date=["time", ".date"],
        sel_summary=["p", ".excerpt"],
        rss_url="https://www.golf.at/feed/",
    ),
    NewsSource(
        id="swiss_golf", name="Swiss Golf",
        country="Sveitsi", region="europe",
        news_url="https://www.swissgolf.ch/en/news/",
        language="en",
        sel_container=["article", ".news-item", ".card"],
        sel_title=["h2", "h3", ".card-title"],
        sel_link=["a"],
        sel_date=["time", ".date"],
        sel_summary=["p", ".excerpt"],
    ),
    NewsSource(
        id="estonian_golf", name="Estonian Golf Union (EGL)",
        country="Viro", region="europe",
        news_url="https://golf.ee/uudised/",
        language="et",
        sel_container=["article", ".news-item", ".card", ".post"],
        sel_title=["h2", "h3", ".entry-title"],
        sel_link=["a"],
        sel_date=["time", ".entry-date", ".date"],
        sel_summary=[".entry-summary", "p"],
    ),
    NewsSource(
        id="pzg_poland", name="Polski Związek Golfa (PZG)",
        country="Puola", region="europe",
        news_url="https://www.pzgolf.pl/aktualnosci/",
        language="pl",
        sel_container=["article", ".news-item", ".card", ".post"],
        sel_title=["h2", "h3", ".entry-title"],
        sel_link=["a"],
        sel_date=["time", ".entry-date", ".date"],
        sel_summary=[".entry-summary", "p"],
    ),
]

# ============================================================
# FETCH HELPERS
# ============================================================
def fetch_page(url: str, timeout: int = 20) -> Optional[str]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        r.raise_for_status()
        r.encoding = r.apparent_encoding or "utf-8"
        return r.text
    except Exception as e:
        print(f"    ⚠ fetch failed ({url}): {e}")
        return None

def try_selector(soup, selectors: list):
    """Try CSS selectors in order, return first match."""
    for sel in selectors:
        found = soup.select(sel)
        if found:
            return found
    return []

def try_selector_one(el, selectors: list):
    """Try selectors on a single element, return first text match."""
    for sel in selectors:
        found = el.select_one(sel)
        if found:
            return found
    return None

def parse_date(text: str) -> Optional[datetime.date]:
    """Try to parse a date string, return date or None."""
    if not text:
        return None
    text = text.strip()
    try:
        return dateparser.parse(text, fuzzy=True).date()
    except Exception:
        # Try to find date patterns manually
        patterns = [
            r'(\d{4}-\d{2}-\d{2})',
            r'(\d{1,2})[./](\d{1,2})[./](\d{4})',
            r'(\d{1,2})\s+\w+\s+(\d{4})',
        ]
        for pat in patterns:
            m = re.search(pat, text)
            if m:
                try:
                    return dateparser.parse(m.group(0), fuzzy=True).date()
                except Exception:
                    pass
    return None

def extract_date_from_element(el) -> Optional[datetime.date]:
    """Extract date from time element or datetime attribute."""
    # Try datetime attribute first (most reliable)
    for attr in ["datetime", "data-date", "content"]:
        val = el.get(attr)
        if val:
            d = parse_date(val)
            if d:
                return d
    # Fall back to text content
    return parse_date(el.get_text())

# ============================================================
# RSS SCRAPER
# ============================================================
def scrape_rss(source: NewsSource, since: datetime.date) -> list[dict]:
    """Scrape articles from RSS feed."""
    html = fetch_page(source.rss_url)
    if not html:
        return []
    try:
        soup = BeautifulSoup(html, "xml")
    except Exception:
        soup = BeautifulSoup(html, "lxml")

    articles = []
    for item in soup.find_all("item"):
        title = item.find("title")
        link  = item.find("link")
        pub   = item.find("pubDate") or item.find("dc:date")
        desc  = item.find("description") or item.find("summary")

        if not title or not link:
            continue

        date_obj = None
        if pub:
            date_obj = parse_date(pub.get_text())
        if not date_obj:
            continue
        if date_obj < since:
            continue  # too old

        articles.append({
            "source_id":   source.id,
            "source_name": source.name,
            "country":     source.country,
            "region":      source.region,
            "language":    source.language,
            "title":       title.get_text().strip(),
            "url":         link.get_text().strip(),
            "date":        date_obj.isoformat(),
            "summary":     BeautifulSoup(desc.get_text(), "html.parser").get_text()[:300].strip() if desc else "",
        })

    print(f"    RSS: {len(articles)} articles (since {since})")
    return articles

# ============================================================
# HTML SCRAPER
# ============================================================
def scrape_html(source: NewsSource, since: datetime.date) -> list[dict]:
    """Scrape articles from HTML news listing page."""
    html = fetch_page(source.news_url)
    if not html:
        return []

    soup = BeautifulSoup(html, "lxml")
    base = source.news_url

    # Remove nav, header, footer, sidebar to reduce noise
    for tag in soup.select("nav, header, footer, aside, .sidebar, .menu, .navigation"):
        tag.decompose()

    containers = try_selector(soup, source.sel_container)
    if not containers:
        print(f"    ⚠ No containers found for {source.id} (selectors: {source.sel_container})")
        return []

    articles = []
    for container in containers:
        # Title
        title_el = try_selector_one(container, source.sel_title)
        if not title_el:
            continue
        title = title_el.get_text().strip()
        if not title or len(title) < 5:
            continue

        # Link
        link_el = container.find("a")
        url = ""
        if link_el and link_el.get("href"):
            url = urljoin(base, link_el["href"])

        # Date — try element selectors first, then any <time> tag
        date_obj = None
        date_el = try_selector_one(container, source.sel_date)
        if date_el:
            date_obj = extract_date_from_element(date_el)
        if not date_obj:
            # Try any time element
            for t in container.find_all("time"):
                date_obj = extract_date_from_element(t)
                if date_obj:
                    break
        if not date_obj:
            # Try to find date-like text patterns in the container
            text = container.get_text()
            date_obj = parse_date(text)

        # If still no date — include but flag as unknown
        if not date_obj:
            date_str = "unknown"
        else:
            if date_obj < since:
                continue  # older than lookback window
            date_str = date_obj.isoformat()

        # Summary
        summary_el = try_selector_one(container, source.sel_summary)
        summary = summary_el.get_text().strip()[:300] if summary_el else ""

        # Skip duplicates within this scrape
        if url and any(a["url"] == url for a in articles):
            continue

        articles.append({
            "source_id":   source.id,
            "source_name": source.name,
            "country":     source.country,
            "region":      source.region,
            "language":    source.language,
            "title":       title,
            "url":         url,
            "date":        date_str,
            "summary":     summary,
        })

    print(f"    HTML: {len(articles)} articles (since {since})")
    return articles

# ============================================================
# SCRAPE ONE SOURCE
# ============================================================
def scrape_source(source: NewsSource, since: datetime.date) -> list[dict]:
    print(f"\n  📰 {source.name} [{source.country}]")
    articles = []

    # Try RSS first (more reliable dates)
    if source.rss_url:
        articles = scrape_rss(source, since)

    # Fall back to HTML if RSS gave nothing
    if not articles:
        articles = scrape_html(source, since)

    # Deduplicate by URL
    seen = set()
    unique = []
    for a in articles:
        key = a.get("url", "") or a.get("title", "")
        if key and key not in seen:
            seen.add(key)
            unique.append(a)

    return unique

# ============================================================
# CLAUDE API
# ============================================================
def call_claude(system: str, prompt: str) -> str:
    if not ANTHROPIC_API_KEY:
        return ""
    import urllib.request
    payload = json.dumps({
        "model": ANTHROPIC_MODEL,
        "max_tokens": 4096,
        "system": system,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
            return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    except Exception as e:
        print(f"  ⚠ Claude API error: {e}")
        return ""

def clean_json(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    s = min((text.find(c) for c in "[{" if text.find(c) >= 0), default=0)
    e = max((text.rfind(c) for c in "]}" if text.rfind(c) >= 0), default=len(text) - 1)
    return text[s:e + 1]

# ============================================================
# ANALYST SYSTEM PROMPT
# ============================================================
ANALYST_SYSTEM = """Olet Suomen Golfliiton mediamonitoroinnin analyytikko.
Saat listan raakoista artikkeleista eurooppalaisilta ja pohjoismaisilta golfliitoilta.

Tehtäväsi on:
1. Kääntää otsikot suomeksi (title_fi)
2. Kirjoittaa lyhyt suomenkielinen tiivistelmä (summary_fi, 2-3 lausetta)
3. Antaa kategoria: tapahtumat | naisten golf | kestävä kehitys | juniorityö | kilpagolf | golfpolitiikka | innovaatiot | seuratoiminta | digitalisaatio | sponsorointi | jäsenmäärät | muu

Palauta JSON-taulukko, jossa jokaisella artikkelilla on KAIKKI alkuperäiset kentät PLUS:
- title_fi: suomenkielinen otsikko
- summary_fi: suomenkielinen tiivistelmä
- category: kategoria

Palauta VAIN JSON-taulukko. Ei markdown-koodiblokeja, ei selitystä."""

CURATOR_SYSTEM = """Olet Suomen Golfliiton viestintäpäällikön strateginen neuvonantaja.
Saat listan eurooppalaisten ja pohjoismaisten golfliittojen tuoreista uutisista.

Valitse noin 10 tärkeintä artikkelia Suomen Golfliiton kannalta ja lisää niihin:
- priority: "🔴" (toimenpide tarpeen, suora benchmarking), "🟡" (kiinnostava trendi), "🟢" (hyvä tietää)
- relevance_analysis: 2-3 lausetta MIKSI tämä on tärkeä Suomen Golfliitol­le
- action_suggestion: Yksi konkreettinen toimenpide-ehdotus suomeksi

Valintakriteerit tärkeysjärjestyksessä:
1. Pohjoismaiset rekrytointi- ja kehitysohjelmat (naiset, juniorit) — benchmarking Suomeen
2. Tapahtumat Suomessa tai suomalaisten pelaajien menestys
3. Digitalisaatio ja jäsenkehitys
4. Kestävä kehitys golfkentillä
5. Eurooppatason kilpailu- tai politiikkamuutokset

Palauta JSON-taulukko valituista ~10 artikkelista, kaikki alkuperäiset kentät mukana.
VAIN JSON. Ei selityksiä."""

# ============================================================
# HTML REPORT GENERATOR
# ============================================================
def generate_html(top_articles: list, all_articles: list) -> str:
    today = datetime.date.today().strftime("%d.%m.%Y")
    prio_order = {"🔴": 0, "🟡": 1, "🟢": 2}
    top_articles.sort(key=lambda a: prio_order.get(a.get("priority", "🟢"), 3))

    def card(a, show_analysis=True):
        prio = a.get("priority", "")
        pcolors = {"🔴": ("#fff5f5", "#c1121f"), "🟡": ("#fffdf5", "#e76f51"), "🟢": ("#f8fffe", "#2a9d8f")}
        bg, border = pcolors.get(prio, ("#fff", "#ccc"))
        action = f'<div style="background:#f0faf5;border:1px solid #b7e4c7;border-radius:6px;padding:8px 12px;margin-top:8px;font-size:0.85rem;color:#1a472a"><strong>💡 Toimenpide:</strong> {a.get("action_suggestion","")}</div>' if show_analysis and a.get("action_suggestion") else ""
        analysis = f'<p style="color:#444;font-size:0.88rem;margin:6px 0 0">{a.get("relevance_analysis", a.get("summary_fi",""))}</p>' if show_analysis else f'<p style="color:#555;font-size:0.85rem;margin:4px 0 0">{a.get("summary_fi","")}</p>'
        url = a.get("url","#")
        return f'''
        <div style="background:{bg};border-left:5px solid {border};border-radius:10px;padding:14px 18px;margin-bottom:10px">
          <div style="font-size:0.72rem;color:#888;margin-bottom:4px">{prio} <strong>{a.get("source_name","")}</strong> · {a.get("country","")} · {a.get("date","")}</div>
          <h3 style="margin:0 0 2px;font-size:0.95rem;color:#1a472a"><a href="{url}" style="color:#1a472a">{a.get("title_fi") or a.get("title","")}</a></h3>
          <p style="margin:0;font-size:0.78rem;color:#999;font-style:italic">{a.get("title","")}</p>
          {analysis}{action}
        </div>'''

    top_html = "".join(card(a, True) for a in top_articles)
    all_html  = "".join(card(a, False) for a in sorted(all_articles, key=lambda x: x.get("date",""), reverse=True))

    return f"""<!DOCTYPE html>
<html lang="fi"><head><meta charset="UTF-8">
<title>Golfkatsaus {today}</title>
<style>body{{font-family:-apple-system,sans-serif;max-width:860px;margin:0 auto;padding:20px;background:#f0f2f0}}
h1{{color:#1a472a}}h2{{color:#1a472a;margin-top:32px}}.badge{{background:#e3f2fd;color:#1565c0;padding:2px 8px;border-radius:12px;font-size:0.75rem;font-weight:600}}</style>
</head><body>
<h1>🏌️ Euroopan & Pohjoismaiden golfkatsaus — {today}</h1>
<p style="color:#666">{len(all_articles)} artikkelia {len(set(a["source_id"] for a in all_articles))} lähteestä · {len(top_articles)} nostoa valittu</p>
<h2>⭐ Nostot — tärkeimmät Suomen Golfliitol­le</h2>
{top_html}
<h2>📋 Kaikki artikkelit ({len(all_articles)}) — kronologinen järjestys</h2>
{all_html}
<hr style="margin-top:40px"><p style="color:#bbb;font-size:0.75rem;text-align:center">Automaattinen mediamonitorointi · Suomen Golfliitto · {today}</p>
</body></html>"""

# ============================================================
# MAIN
# ============================================================
def main():
    print("=" * 60)
    print(f"🏌️  Golf Federation News Monitor")
    print(f"   {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"   Lookback: {LOOKBACK_DAYS} days | Sources: {len(SOURCES)}")
    print("=" * 60)

    if not ANTHROPIC_API_KEY:
        print("⚠  ANTHROPIC_API_KEY not set — will scrape without AI analysis")
        print("   export ANTHROPIC_API_KEY='sk-ant-...'")

    since = datetime.date.today() - datetime.timedelta(days=LOOKBACK_DAYS)
    print(f"\nCollecting articles since {since}...\n")

    # ── Phase 1: Scrape all sources ──────────────────────────
    print("📡 PHASE 1: Scraping sources")
    all_raw = []
    for source in SOURCES:
        try:
            arts = scrape_source(source, since)
            all_raw.extend(arts)
        except Exception as e:
            print(f"    ✗ Error scraping {source.id}: {e}")
        time.sleep(1.5)  # polite delay

    # Global dedup by URL
    seen_urls = set()
    all_raw_unique = []
    for a in all_raw:
        key = a.get("url") or (a["source_id"] + a["title"])
        if key not in seen_urls:
            seen_urls.add(key)
            all_raw_unique.append(a)

    print(f"\n✅ {len(all_raw_unique)} unique articles from {len(SOURCES)} sources")

    if not all_raw_unique:
        print("No articles found. Check network / selectors.")
        sys.exit(0)

    # ── Phase 2: Translate + categorize ─────────────────────
    all_articles = all_raw_unique
    if ANTHROPIC_API_KEY:
        print("\n🤖 PHASE 2: Translating & categorizing with Claude...")
        batch_size = 20
        translated = []
        for i in range(0, len(all_raw_unique), batch_size):
            batch = all_raw_unique[i:i + batch_size]
            print(f"   Batch {i//batch_size + 1} ({len(batch)} articles)...")
            result = call_claude(
                ANALYST_SYSTEM,
                f"Here are {len(batch)} articles to translate and categorize:\n\n{json.dumps(batch, ensure_ascii=False)}"
            )
            if result:
                try:
                    parsed = json.loads(clean_json(result))
                    if isinstance(parsed, list):
                        translated.extend(parsed)
                        continue
                except Exception:
                    pass
            translated.extend(batch)  # fall back to raw
        all_articles = translated

    # Sort chronologically
    all_articles.sort(key=lambda a: a.get("date", ""), reverse=True)

    # ── Phase 3: Curate top picks ────────────────────────────
    top_picks = []
    if ANTHROPIC_API_KEY:
        print("\n🏆 PHASE 3: Curating top picks...")
        result = call_claude(
            CURATOR_SYSTEM,
            f"Select ~10 most relevant from these {len(all_articles)} articles:\n\n{json.dumps(all_articles, ensure_ascii=False)}"
        )
        if result:
            try:
                top_picks = json.loads(clean_json(result))
            except Exception:
                pass
    if not top_picks:
        top_picks = all_articles[:10]  # fallback

    # ── Phase 4: Save outputs ────────────────────────────────
    today_str = datetime.date.today().strftime("%Y-%m-%d")

    json_path = OUTPUT_DIR / f"golf_digest_{today_str}.json"
    json_path.write_text(json.dumps({
        "generated": datetime.datetime.now().isoformat(),
        "lookback_days": LOOKBACK_DAYS,
        "source_count": len(SOURCES),
        "article_count": len(all_articles),
        "top_picks": top_picks,
        "all_articles": all_articles,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    html_path = OUTPUT_DIR / f"golf_digest_{today_str}.html"
    html_path.write_text(generate_html(top_picks, all_articles), encoding="utf-8")

    print(f"\n{'='*60}")
    print(f"✅ Done!")
    print(f"   Articles collected : {len(all_articles)}")
    print(f"   Top picks selected : {len(top_picks)}")
    print(f"   JSON  → {json_path}")
    print(f"   HTML  → {html_path}")
    print(f"\nTop picks:")
    for a in top_picks[:5]:
        print(f"  {a.get('priority','')} {a.get('title_fi') or a.get('title','')}")
        print(f"     {a.get('source_name','')} · {a.get('date','')}")

if __name__ == "__main__":
    main()
