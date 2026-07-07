"""Lähteiden lataus sources.yaml-tiedostosta."""
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import quote_plus

import yaml

from . import config


# Google News -haku toimii kunnolla vain lähteen omalla lokaalilla:
# suomalaisella hl/gl:llä ulkomaiset domainit antavat usein 0 osumaa.
_GN_LOCALE = {
    "fi": "hl=fi&gl=FI&ceid=FI:fi",
    "sv": "hl=sv&gl=SE&ceid=SE:sv",
    "no": "hl=no&gl=NO&ceid=NO:no",
    "da": "hl=da&gl=DK&ceid=DK:da",
    "is": "hl=is-IS&gl=IS&ceid=IS:is",
    "en": "hl=en-US&gl=US&ceid=US:en",
    "de": "hl=de&gl=DE&ceid=DE:de",
    "de-ch": "hl=de-CH&gl=CH&ceid=CH:de",
    "fr": "hl=fr&gl=FR&ceid=FR:fr",
    "es": "hl=es&gl=ES&ceid=ES:es",
    "it": "hl=it&gl=IT&ceid=IT:it",
    "nl": "hl=nl&gl=NL&ceid=NL:nl",
    "et": "hl=et-EE&gl=EE&ceid=EE:et",
    "pl": "hl=pl&gl=PL&ceid=PL:pl",
}


@dataclass
class Source:
    id: str
    name: str
    tab: str                    # "golfliitot" | "urheilu_liitot"
    country: str
    language: str
    rss: Optional[str] = None
    html_url: Optional[str] = None
    html_selectors: dict = field(default_factory=dict)
    google_news: Optional[str] = None          # domain -> site:-haku
    google_news_query: Optional[str] = None    # vapaa hakulause (esim. JS-sivustot, joita GN ei indeksoi)

    @property
    def google_news_rss(self) -> Optional[str]:
        if self.google_news_query:
            q = quote_plus(self.google_news_query)
        elif self.google_news:
            q = f"site:{self.google_news}"
        else:
            return None
        locale = _GN_LOCALE.get(self.language, _GN_LOCALE["en"])
        return f"https://news.google.com/rss/search?q={q}&{locale}"


def load_sources(path=None) -> tuple[list[Source], dict]:
    """Palauttaa (lähteet, oletusselektorit)."""
    path = path or config.SOURCES_PATH
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    defaults = (raw.get("defaults") or {}).get("html_selectors") or {}
    sources = []
    for item in raw.get("sources", []):
        html = item.get("html") or {}
        selectors = dict(defaults)
        selectors.update(html.get("selectors") or {})
        sources.append(Source(
            id=str(item["id"]),
            name=item["name"],
            tab=item["tab"],
            country=item.get("country", ""),
            language=str(item.get("language", "en")),
            rss=item.get("rss"),
            html_url=html.get("url"),
            html_selectors=selectors,
            google_news=item.get("google_news"),
            google_news_query=item.get("google_news_query"),
        ))

    ids = [s.id for s in sources]
    if len(ids) != len(set(ids)):
        dupes = {i for i in ids if ids.count(i) > 1}
        raise ValueError(f"Duplikaatti-id:t sources.yaml:ssa: {dupes}")
    return sources, defaults
