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


def _cap(source: Source) -> int:
    """Montako artikkelia lähteestä otetaan. Lähdekohtainen katto ohittaa
    globaalin: laaja hakulause ("golf") tuottaa satoja osumia, kun taas yhden
    liiton uutissivulta 15 riittää aina."""
    return source.max_articles or config.MAX_PER_SOURCE
_GN_SUFFIX = re.compile(r"\s+[-–|]\s+[^-–|]{2,40}$")

# Skeema ilman kaksoispistettä keskellä linkkiä: "…nlhttps//www…"
_BROKEN_SCHEME = re.compile(r"https?//")


def repair_link(link: str) -> str:
    """Korjaa syötteen rikkinäinen absoluuttinen linkki.

    Osa julkaisujärjestelmistä kirjoittaa <link>-kenttään skeeman ilman
    kaksoispistettä ("https//www.ngf.nl/uutinen"). feedparser tulkitsee sen
    silloin relatiiviseksi ja liimaa base-URLin eteen, jolloin syntyy
    "http://www.ngf.nlhttps//www.ngf.nl/uutinen" — linkki näyttää kelvolliselta
    mutta ei avaudu. Otetaan viimeinen skeema ja palautetaan kaksoispiste.

    Kunnollinen URL ei osu tähän: "https://x.fi" ei täsmää, koska skeeman ja
    kautusviivojen välissä on kaksoispiste.
    """
    hits = list(_BROKEN_SCHEME.finditer(link))
    if not hits:
        return link
    return link[hits[-1].start():].replace("//", "://", 1)

# Kuukaudennimet lähteiden kielillä. dateutil tuntee vain englannin, ja fuzzy=True
# täyttää tunnistamattoman kuukauden NYKYHETKESTÄ: "5. juli 2026" tulkittiin
# päiväksi 2026-05-27. Väärä tuore päivämäärä nostaa vanhan jutun raporttiin,
# joten kuukaudet käännetään numeroiksi ennen dateutilia.
_MONTH_NAMES = {
    1: ["tammikuu", "januari", "januar", "janúar", "january", "jänner", "janvier",
        "enero", "gennaio", "styczeń", "styczen", "stycznia", "jaanuar"],
    2: ["helmikuu", "februari", "februar", "febrúar", "february", "février", "fevrier",
        "febrero", "febbraio", "luty", "lutego", "veebruar"],
    3: ["maaliskuu", "mars", "marts", "march", "märz", "marz", "maart", "marzo",
        "marzec", "marca", "märts"],
    4: ["huhtikuu", "april", "apríl", "avril", "abril", "aprile", "kwiecień",
        "kwiecien", "kwietnia", "aprill"],
    5: ["toukokuu", "maj", "mai", "may", "maí", "mei", "mayo", "maggio", "maja"],
    6: ["kesäkuu", "kesakuu", "juni", "june", "júní", "juin", "junio", "giugno",
        "czerwiec", "czerwca"],
    7: ["heinäkuu", "heinakuu", "juli", "july", "júlí", "juillet", "julio", "luglio",
        "lipiec", "lipca"],
    8: ["elokuu", "augusti", "august", "ágúst", "août", "aout", "agosto", "augustus",
        "sierpień", "sierpien", "sierpnia"],
    9: ["syyskuu", "september", "septembra", "septembre", "septiembre", "settembre",
        "wrzesień", "wrzesien", "września", "wrzesnia"],
    10: ["lokakuu", "oktober", "október", "octobre", "octubre", "ottobre",
         "październik", "pazdziernik", "października", "pazdziernika"],
    11: ["marraskuu", "november", "nóvember", "novembre", "noviembre", "listopad",
         "listopada"],
    12: ["joulukuu", "december", "desember", "dezember", "décembre",
         "decembre", "diciembre", "dicembre", "grudzień", "grudzien", "grudnia"],
}
# nimi -> kuukausinumero; myös 3-merkkiset lyhenteet (esim. "jul", "des", "okt")
_MONTH_LOOKUP: dict[str, int] = {}
for _num, _names in _MONTH_NAMES.items():
    for _n in _names:
        _MONTH_LOOKUP.setdefault(_n, _num)
        _MONTH_LOOKUP.setdefault(_n[:3], _num)

# "5. juli 2026", "16 maj 2025", "5 de julio de 2026", "26. juni 2026"
_DMY_RE = re.compile(
    r"\b(\d{1,2})\.?\s+(?:de\s+)?([^\W\d_]{3,12})\.?,?\s+(?:de\s+|del\s+)?(\d{4})\b",
    re.UNICODE)
# "juli 5, 2026", "July 5 2026"
_MDY_RE = re.compile(
    r"\b([^\W\d_]{3,12})\.?\s+(\d{1,2})\.?,?\s+(\d{4})\b", re.UNICODE)
# ISO-muoto on aina vuosi-kuukausi-päivä. dayfirst=True sai dateutilin kääntämään
# sen ("2026-07-03" -> 3.3.2026), joten ISO tunnistetaan ennen dateutilia.
# Loppuraja on (?!\d) eikä \b: aikaleimassa "2026-07-11T19:00:00" ei ole
# sananrajaa "11":n ja "T":n välillä, joten \b ei osunut ja koko aikaleima valui
# dateutilille -> dayfirst käänsi sen päiväksi 7.11.2026. Vika koski kaikkia
# lähteitä, joilla päivä tulee <time datetime="...">-attribuutista tai
# JSON-rajapinnasta, ja se osui aina kun päivä oli 1-12.
_ISO_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})(?!\d)")


# ---------------------------------------------------------------- helpers
def clean_title(title: str, google_news: bool = False) -> str:
    """Siivoa otsikko: whitespace + Google Newsin ' - Lähde' -suffiksi."""
    title = re.sub(r"\s+", " ", title or "").strip()
    if google_news:
        title = _GN_SUFFIX.sub("", title)
    return title


def _localised_date(text: str) -> Optional[datetime.date]:
    """Tunnista 'päivä kuukaudennimi vuosi' lähteiden kielillä."""
    low = text.lower()
    for rx, order in ((_DMY_RE, "dmy"), (_MDY_RE, "mdy")):
        for m in rx.finditer(low):
            if order == "dmy":
                day, name, year = m.group(1), m.group(2), m.group(3)
            else:
                name, day, year = m.group(1), m.group(2), m.group(3)
            month = _MONTH_LOOKUP.get(name) or _MONTH_LOOKUP.get(name[:3])
            if not month:
                continue
            try:
                return datetime.date(int(year), month, int(day))
            except ValueError:
                continue
    return None


def parse_date(text: str) -> Optional[datetime.date]:
    if not text:
        return None
    text = text.strip()
    iso = _ISO_RE.search(text)
    if iso:
        try:
            return datetime.date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
        except ValueError:
            pass
    localised = _localised_date(text)
    if localised is not None:
        return localised
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


def _article(source: Source, title: str, url: str, date_str: str, summary: str,
             image: str = "") -> dict:
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
        "image": image or "",
    }


def _entry_image(entry) -> str:
    """Poimi artikkelin kuva RSS-merkinnästä (media-tagit, enclosure tai sisällön <img>)."""
    for key in ("media_content", "media_thumbnail"):
        for m in entry.get(key) or []:
            url = (m or {}).get("url") or ""
            if url.startswith("http"):
                return url
    for lnk in entry.get("links") or []:
        if lnk.get("rel") == "enclosure" and str(lnk.get("type", "")).startswith("image"):
            href = lnk.get("href") or ""
            if href.startswith("http"):
                return href
    html = ""
    if entry.get("content"):
        html = (entry["content"][0] or {}).get("value", "")
    html = html or entry.get("summary", "")
    m = re.search(r'<img[^>]+src=["\'](https?://[^"\']+)', html or "")
    return m.group(1) if m else ""


# ---------------------------------------------------------------- RSS
def fetch_rss(source: Source, url: str, since: datetime.date,
              google_news: bool = False) -> tuple[list[dict], dict]:
    """Palauttaa (ikkunaan osuvat artikkelit, diagnostiikka).

    Diagnostiikka kertoo MIKSI merkintöjä karsiutui: väärä domain (Google News
    palautti muiden medioiden juttuja), liian vanha, vai puuttuva otsikko/linkki.
    """
    resp = _http_get(url)
    if resp is None:
        return [], {"total": -1}
    feed = feedparser.parse(resp.content)
    diag = {"total": len(feed.entries), "domain": 0, "old": 0, "bad": 0, "nodate": 0}
    articles = []
    # Selaa syöte laajasti: Google News ei aina järjestä tuloksia päivämäärän
    # mukaan, joten tuoreet voivat olla vasta listan loppupuolella.
    for entry in feed.entries[:120]:
        title = clean_title(entry.get("title", ""), google_news=google_news)
        link = repair_link((entry.get("link") or "").strip())
        if not title or len(title) < MIN_TITLE_LEN or not link:
            diag["bad"] += 1
            continue

        # Google News site:-haku kattaa myös alidomainit (esim.
        # performance.golf.at) ja palauttaa joskus muiden medioiden juttuja
        # -> hyväksy vain pääsivusto ja www.
        if google_news and source.google_news:
            src_href = (entry.get("source") or {}).get("href") or ""
            host = urlparse(src_href).netloc.lower()
            dom = source.google_news.lower()
            if host and host not in (dom, f"www.{dom}"):
                diag["domain"] += 1
                continue

        date_obj = None
        for key in ("published_parsed", "updated_parsed"):
            t = entry.get(key)
            if t:
                date_obj = datetime.date(t.tm_year, t.tm_mon, t.tm_mday)
                break
        if date_obj is None:
            date_obj = parse_date(entry.get("published") or entry.get("updated") or "")
        # Päivämäärätön merkintä SÄILYTETÄÄN ja päivätään havaitsemispäivällä:
        # store jättää published-kentän tyhjäksi ja _EFF_DATE käyttää fetched_at.
        # Sama sääntö kaikilla reiteillä (HTML toimi näin jo ennen). Laskuri
        # pidetään, koska kokonaan päivämäärätön syöte on silti epäilyttävä ja
        # siitä varoitetaan lokissa erikseen.
        if date_obj is None:
            diag["nodate"] += 1
        elif date_obj < since:
            diag["old"] += 1
            continue

        summary = ""
        if entry.get("summary"):
            summary = BeautifulSoup(entry["summary"], "html.parser").get_text(" ", strip=True)

        image = "" if google_news else _entry_image(entry)
        date_str = date_obj.isoformat() if date_obj else ""
        art = _article(source, title, link, date_str, summary, image)
        # Vapaassa hakulauseessa yksi "lähde" on oikeasti kymmeniä medioita, joten
        # lähteen oma nimi ei kerro mitään. Google News antaa julkaisijan erikseen
        # (<source>-tagi) — ilman tätä listalla lukisi joka rivillä sama nimi.
        # site:-haussa julkaisija on jo tiedossa, joten sitä ei ylikirjoiteta.
        if google_news and not source.google_news:
            publisher = ((entry.get("source") or {}).get("title") or "").strip()
            if publisher:
                art["source_name"] = publisher
        articles.append(art)
        if len(articles) >= _cap(source):
            break
    return articles, diag


# ---------------------------------------------------------------- JSON-API
def _dig(obj, path: str):
    """Hae sisäkkäinen arvo pistepolulla ("data.items"). Tyhjä polku = obj."""
    for part in (path or "").split("."):
        if not part:
            continue
        if not isinstance(obj, dict):
            return None
        obj = obj.get(part)
    return obj


def fetch_json_api(source: Source, since: datetime.date) -> tuple[list[dict], dict]:
    """Hae artikkelit sivuston omasta JSON-rajapinnasta.

    Osa liitoista ajaa uutislistauksen JS-sovelluksena, joten HTML:stä ei löydy
    otsikoita eikä Google News indeksoi niiden pääsivustoa. Sovellus hakee
    datansa rajapinnasta, jota voi kutsua suoraan — se on näille lähteille ainoa
    reitti, jolla saa oikeat päivämäärät ja linkit.

    Konfiguraatio (sources.yaml):
      url            rajapinnan osoite
      method         GET tai POST (oletus POST)
      payload        POST-runko sellaisenaan
      items_key      pistepolku listaan, jos vastaus ei ole suoraan lista
      fields         kenttäkartta: title / date / summary / image
      link_template  artikkelin osoite, muotoiltuna API:n omilla kentillä
    """
    cfg = source.json_api
    url = cfg.get("url")
    if not url:
        return [], {"total": 0}

    headers = dict(config.HTTP_HEADERS)
    headers.update({"Content-Type": "application/json", "Accept": "application/json"})
    try:
        if str(cfg.get("method", "POST")).upper() == "GET":
            resp = requests.get(url, headers=headers, params=cfg.get("payload") or {},
                                timeout=config.FETCH_TIMEOUT)
        else:
            resp = requests.post(url, headers=headers, json=cfg.get("payload") or {},
                                 timeout=config.FETCH_TIMEOUT)
        resp.raise_for_status()
        payload = resp.json()
    except (requests.RequestException, ValueError) as e:
        log.debug("json_api failed %s: %s", url, e)
        return [], {"total": -1}

    items = _dig(payload, cfg.get("items_key", "")) if cfg.get("items_key") else payload
    if not isinstance(items, list):
        return [], {"total": 0}

    fields = cfg.get("fields") or {}
    f_title = fields.get("title", "Title")
    f_date = fields.get("date", "PublishDate")
    f_summary = fields.get("summary", "")
    f_image = fields.get("image", "")
    template = cfg.get("link_template", "")

    diag = {"total": len(items), "domain": 0, "old": 0, "bad": 0, "nodate": 0}
    articles = []
    for it in items:
        if not isinstance(it, dict):
            diag["bad"] += 1
            continue
        title = clean_title(str(it.get(f_title) or ""))
        try:
            link = template.format(**it) if template else str(it.get("url") or "")
        except (KeyError, IndexError):
            link = ""
        if len(title) < MIN_TITLE_LEN or not link:
            diag["bad"] += 1
            continue

        # Päivämäärätön säilytetään ja päivätään havaitsemispäivällä (ks. fetch_rss)
        date_obj = parse_date(str(it.get(f_date) or ""))
        if date_obj is None:
            diag["nodate"] += 1
        elif date_obj < since:
            diag["old"] += 1
            continue

        summary = ""
        if f_summary and it.get(f_summary):
            summary = BeautifulSoup(str(it[f_summary]), "html.parser").get_text(" ", strip=True)
        image = ""
        if f_image and it.get(f_image):
            image = urljoin(url, str(it[f_image]))

        date_str = date_obj.isoformat() if date_obj else ""
        articles.append(_article(source, title, link, date_str, summary, image))
        if len(articles) >= _cap(source):
            break
    return articles, diag


# ---------------------------------------------------------------- sitemap
_SITEMAP_URL_RE = re.compile(
    r"<url>\s*<loc>(.*?)</loc>\s*(?:<lastmod>(.*?)</lastmod>)?", re.S)


def _meta(soup, *names: str) -> str:
    """Poimi ensimmäinen löytyvä og:/name-metatieto."""
    for n in names:
        el = soup.find("meta", attrs={"property": n}) or soup.find("meta", attrs={"name": n})
        if el is not None and el.get("content"):
            return el["content"].strip()
    return ""


def fetch_sitemap(source: Source, since: datetime.date) -> tuple[list[dict], dict]:
    """Hae artikkelit sitemapista ja täydennä otsikko artikkelisivun metatiedoista.

    Viimeinen keino sivustolle, jolla uutislistaus on JS-sovellus eikä
    listausrajapintaa löydy (R&A: Next.js, jonka __NEXT_DATA__ sisältää vain
    hero-artikkelin). Sitemap antaa osoitteet ja lastmodin, artikkelisivun
    og-metatiedot otsikon, ingressin ja kuvan.

    HUOM päivämäärä: lastmod on sivun muokkausaika, ei julkaisuaika. R&A:lla ne
    vastaavat toisiaan päivän tarkkuudella (tarkistettu 7/2026), mutta jos lähde
    muokkaa vanhoja sivuja, ne nousevat tuoreina. Siksi ikkuna rajataan
    lastmodilla ENNEN artikkelisivujen hakua — muuten haettaisiin satoja sivuja.

    Konfiguraatio: url, include (polun osa), exclude (valinnainen).
    """
    cfg = source.sitemap
    url = cfg.get("url")
    if not url:
        return [], {"total": 0}
    resp = _http_get(url)
    if resp is None:
        return [], {"total": -1}

    include = cfg.get("include") or ""
    exclude = cfg.get("exclude") or ""
    entries = []
    for loc, lastmod in _SITEMAP_URL_RE.findall(resp.content.decode("utf-8", "ignore")):
        loc = loc.strip()
        if include and include not in loc:
            continue
        if exclude and exclude in loc:
            continue
        entries.append((loc, parse_date((lastmod or "").strip())))

    diag = {"total": len(entries), "domain": 0, "old": 0, "bad": 0, "nodate": 0}
    fresh = []
    for loc, d in entries:
        if d is None:
            diag["nodate"] += 1          # päivätään havaitsemishetkellä
        elif d < since:
            diag["old"] += 1
            continue
        fresh.append((loc, d))
    # Tuoreimmat ensin, jotta kiintiö menee uusimpiin jos raja tulee vastaan
    fresh.sort(key=lambda t: (t[1] is not None, t[1]), reverse=True)

    articles = []
    for loc, d in fresh[:_cap(source)]:
        page = _http_get(loc)
        if page is None:
            diag["bad"] += 1
            continue
        page.encoding = page.apparent_encoding or "utf-8"
        soup = BeautifulSoup(page.text, "lxml")
        title = clean_title(_meta(soup, "og:title", "twitter:title")
                            or (soup.title.get_text(" ", strip=True) if soup.title else ""))
        if len(title) < MIN_TITLE_LEN:
            diag["bad"] += 1
            continue
        summary = _meta(soup, "og:description", "description")
        image = _meta(soup, "og:image")
        articles.append(_article(source, title, loc,
                                 d.isoformat() if d else "", summary, image))
    return articles, diag


# ---------------------------------------------------------------- HTML
def _select_first(el, selectors: list):
    for sel in selectors or []:
        found = el.select_one(sel)
        if found:
            return found
    return None


def _looks_like_article(c, sel: dict) -> bool:
    """Onko containerissa sekä käyttökelpoinen otsikko että linkki?"""
    title_el = _select_first(c, sel.get("title", []))
    title = clean_title(title_el.get_text(" ", strip=True)) if title_el is not None else ""
    if len(title) < MIN_TITLE_LEN:
        cands = [clean_title(a.get_text()) for a in c.find_all("a")]
        cands = [t for t in cands if len(t) >= MIN_TITLE_LEN]
        title = max(cands, key=len) if cands else ""
    if len(title) < MIN_TITLE_LEN:
        return False
    return bool(c.find("a", href=True) or (c.name == "a" and c.get("href")))


def _pick_containers(soup, sel: dict) -> list:
    """Valitse container-selektori, joka tuottaa eniten käyttökelpoisia osumia.

    Ennen tässä otettiin ensimmäinen selektori joka osui mihinkään. Se meni
    pieleen Drupal-sivustoilla: oletuslistan 'article' osuu EGA:lla 18
    kuvaelementtiin (media--type-image), joten oikeaa '.views-row'-selektoria ei
    kokeiltu koskaan ja loki näytti "18 puutteellista". Nyt selektori kelpaa
    vain, jos sen osumista löytyy otsikko ja linkki — tyhjät rungot eivät enää
    varjosta toimivaa selektoria.

    Jos yksikään ei tuota käyttökelpoisia, palautetaan ensimmäinen osuma, jotta
    diagnostiikka kertoo edelleen "N puutteellista" eikä "selektorit eivät osu".
    """
    first_match = []
    for s in sel.get("container", []):
        found = soup.select(s)
        if not found:
            continue
        if not first_match:
            first_match = found
        if any(_looks_like_article(c, sel) for c in found):
            return found
    return first_match


def fetch_html(source: Source, since: datetime.date) -> tuple[list[dict], dict]:
    """Palauttaa (ikkunaan osuvat artikkelit, diagnostiikka)."""
    resp = _http_get(source.html_url)
    if resp is None:
        return [], {"total": -1}
    resp.encoding = resp.apparent_encoding or "utf-8"
    soup = BeautifulSoup(resp.text, "lxml")
    for tag in soup.select("nav, header, footer, aside, .sidebar, .menu, .navigation, script, style"):
        tag.decompose()

    sel = source.html_selectors
    containers = _pick_containers(soup, sel)
    if not containers:
        return [], {"total": 0}   # sivu vastasi, mutta selektorit eivät osuneet

    diag = {"total": len(containers), "domain": 0, "old": 0, "bad": 0}
    articles = []
    for c in containers:
        title_el = _select_first(c, sel.get("title", []))
        title = clean_title(title_el.get_text(" ", strip=True)) if title_el is not None else ""
        if len(title) < MIN_TITLE_LEN:
            # Varasuunnitelma: monella sivustolla otsikko on suoraan linkissä
            # eikä h2/h3-elementissä. Valitse pisin järkevä linkkiteksti.
            candidates = [clean_title(a.get_text(" ", strip=True)) for a in c.find_all("a")]
            candidates = [t for t in candidates if len(t) >= MIN_TITLE_LEN]
            title = max(candidates, key=len) if candidates else ""
        if len(title) < MIN_TITLE_LEN:
            diag["bad"] += 1
            continue

        link_el = c.find("a", href=True) or (title_el.find("a", href=True) if hasattr(title_el, "find") else None)
        if link_el is None and c.name == "a" and c.get("href"):
            link_el = c
        if link_el is None:
            diag["bad"] += 1
            continue
        url = urljoin(source.html_url, link_el["href"])
        # Templaattisivustoilla (Knockout, Vue) kortit ovat tyhjiä runkoja: linkki on
        # "#!" ja sisältö haetaan JS:llä. Silloin osoite osoittaa listaussivulle
        # itseensä ja otsikoksi valikoituu CMS:n painike ("Edit Article").
        # Tällaiset eivät ole artikkeleita.
        if url.split("#")[0].rstrip("/") == source.html_url.split("#")[0].rstrip("/"):
            diag["bad"] += 1
            continue

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
            diag["old"] += 1
            continue
        date_str = date_obj.isoformat() if date_obj else ""

        summary_el = _select_first(c, sel.get("summary", []))
        summary = summary_el.get_text(" ", strip=True) if summary_el else ""

        image = ""
        img_el = c.find("img")
        if img_el is not None:
            src = img_el.get("src") or img_el.get("data-src") or ""
            if src and not src.startswith("data:"):
                image = urljoin(source.html_url, src)

        articles.append(_article(source, title, url, date_str, summary, image))
        if len(articles) >= _cap(source):
            break
    return articles, diag


# ---------------------------------------------------------------- orchestration
def _drop_excluded(source: Source,
                   articles: list[dict]) -> tuple[list[dict], int, int]:
    """Pudota lähteen hylkyfraaseihin osuvat otsikot.

    Kolme mekanismia:
      `exclude`                   — fraasi osuu otsikkoon
      `exclude_publishers`        — julkaisijan nimi täsmää (ehdoton)
      `exclude_publishers_unless` — julkaisija karsitaan PAITSI jos otsikko
                                    osuu pelastusfraasiin (ehdollinen)

    Julkaisijasuodattimet toimivat vain Google News -haussa, jossa julkaisija
    poimitaan syötteestä.

    Ehdollinen karsinta on tarkoitettu julkaisijaan, jonka virta on pääosin
    epäolennaista mutta joka silti julkaisee säännöllisesti yhden kiinnostavan
    aiheen. Se tehdään tässä eikä promptissa kahdesta syystä: karsitut eivät
    kuluta Gemini-kutsuja, ja sääntö on jäljitettävissä lokista. Prompti ei
    myöskään voisi tunnistaa julkaisijakohtaista sääntöä luotettavasti, koska
    media-jutuista on käytössä vain otsikko.

    Palauttaa (jäljelle jääneet, ehdoton karsinta, ehdollinen karsinta).
    """
    if not (source.exclude or source.exclude_publishers
            or source.exclude_publishers_unless):
        return articles, 0, 0

    kept, hylatty, ehdollinen = [], 0, 0
    for a in articles:
        title = a["title"].casefold()
        publisher = a["source_name"].casefold()
        if any(x in title for x in source.exclude) or publisher in source.exclude_publishers:
            hylatty += 1
            continue
        pelastavat = source.exclude_publishers_unless.get(publisher)
        if pelastavat is not None and not any(x in title for x in pelastavat):
            ehdollinen += 1
            continue
        kept.append(a)
    return kept, hylatty, ehdollinen


def fetch_source(source: Source, since: datetime.date) -> tuple[list[dict], dict]:
    """Kokeile hakutapoja järjestyksessä. Palauta (artikkelit, health)."""
    health = {"source_id": source.id, "source_name": source.name, "tab": source.tab,
              "method": None, "count": 0, "error": ""}
    methods = []
    if source.rss:
        methods.append(("rss", lambda: fetch_rss(source, source.rss, since)))
    if source.json_api:
        methods.append(("json_api", lambda: fetch_json_api(source, since)))
    if source.sitemap:
        methods.append(("sitemap", lambda: fetch_sitemap(source, since)))
    if source.html_url:
        methods.append(("html", lambda: fetch_html(source, since)))
    if source.google_news_rss:
        methods.append(("google_news",
                        lambda: fetch_rss(source, source.google_news_rss, since, google_news=True)))

    notes = []
    for name, fn in methods:
        try:
            articles, diag = fn()
        except Exception as e:  # noqa: BLE001 — yksittäinen lähde ei saa kaataa ajoa
            notes.append(f"{name}: virhe ({e})")
            log.warning("%s %s epäonnistui: %s", source.id, name, e)
            continue
        articles, dropped, conditional = _drop_excluded(source, articles)
        if dropped:
            log.info("%s (%s): %d otsikkoa hylkylistalla", source.id, name, dropped)
        if conditional:
            log.info("%s (%s): %d ehdollisesti karsittua julkaisijan juttua",
                     source.id, name, conditional)
        if articles:
            health.update(method=name, count=len(articles))
            # Päivämäärätön juttu päivätään havaitsemishetkellä, joten vanha juttu
            # näyttää tuoreelta. Se ei estä ajoa, mutta lähde kannattaa korjata.
            nodate = sum(1 for a in articles if not a.get("published"))
            if nodate:
                log.warning("%s (%s): %d/%d artikkelia ilman päivämäärää — "
                            "päivätään havaitsemispäivällä, tarkista selektori",
                            source.id, name, nodate, len(articles))
            return articles, health

        total = diag.get("total", 0)
        if total == -1:
            notes.append(f"{name}: ei vastausta (URL rikki tai sivusto estää)")
        elif total == 0:
            notes.append(f"{name}: tyhjä syöte / selektorit eivät osu")
        else:
            # Kerro tarkka syy: eniten karsineet suodattimet ensin
            reasons = []
            if diag.get("domain"):
                reasons.append(f"{diag['domain']} muun median juttua (ei tätä lähdettä)")
            if diag.get("old"):
                reasons.append(f"{diag['old']} liian vanhaa")
            if diag.get("nodate"):
                nodate = diag["nodate"]
                # Koko syöte ilman päivämääriä = rikki, ei harvoin julkaiseva
                suffix = " — SYÖTE RIKKI" if nodate == total else ""
                reasons.append(f"{nodate} ilman päivämäärää{suffix}")
            if diag.get("bad"):
                reasons.append(f"{diag['bad']} puutteellista")
            notes.append(f"{name}: {total} merkintää — " + ", ".join(reasons or ["ei osumia"]))

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
