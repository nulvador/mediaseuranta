"""Valinnainen sähköpostilähetys: lyhyt kooste rungossa, report.html liitteenä.

Ohitetaan hiljaisesti jos SMTP_HOST tai EMAIL_TO puuttuu .env:stä.
"""
import datetime
import logging
import smtplib
from email.message import EmailMessage
from pathlib import Path

from . import config
from .report import PRIO_EMOJI

log = logging.getLogger(__name__)


def _digest_text(articles: list[dict], run_summary: dict) -> str:
    top = [a for a in articles if a.get("priority") == "korkea"][:8]
    mid = [a for a in articles if a.get("priority") == "keskitaso"][:5]

    lines = [
        f"Golfliiton mediakatsaus {datetime.date.today().strftime('%d.%m.%Y')}",
        f"Uusia artikkeleita tässä ajossa: {run_summary.get('new_articles', 0)}",
        "",
        "Huom: AI-käännökset ja -tiivistelmät ovat luonnoksia — tarkista faktat",
        "ennen kuin sisältöä käytetään julkisesti.",
        "",
    ]
    if top:
        lines.append("KORKEA PRIORITEETTI:")
        for a in top:
            lines.append(f"  {PRIO_EMOJI['korkea']} {a.get('title_fi') or a.get('title')}")
            lines.append(f"     {a.get('source_name','')} · {a.get('published','')} · {a.get('url','')}")
        lines.append("")
    if mid:
        lines.append("KESKITASO:")
        for a in mid:
            lines.append(f"  {PRIO_EMOJI['keskitaso']} {a.get('title_fi') or a.get('title')}")
            lines.append(f"     {a.get('source_name','')} · {a.get('url','')}")
        lines.append("")
    lines.append("Koko selattava raportti liitteenä (report.html).")
    return "\n".join(lines)


def send_report(articles: list[dict], run_summary: dict, report_path: str) -> bool:
    if not config.SMTP_HOST or not config.EMAIL_TO:
        log.info("Sähköpostia ei konfiguroitu (SMTP_HOST/EMAIL_TO puuttuu) — ohitetaan")
        return False

    msg = EmailMessage()
    msg["Subject"] = f"Golfliiton mediakatsaus {datetime.date.today().strftime('%d.%m.%Y')}"
    msg["From"] = config.EMAIL_FROM
    msg["To"] = ", ".join(config.EMAIL_TO)
    msg.set_content(_digest_text(articles, run_summary))
    msg.add_attachment(
        Path(report_path).read_bytes(),
        maintype="text", subtype="html",
        filename="golfkatsaus.html",
    )

    try:
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=30) as s:
            s.starttls()
            if config.SMTP_USER:
                s.login(config.SMTP_USER, config.SMTP_PASS)
            s.send_message(msg)
        log.info("Raportti lähetetty: %s", ", ".join(config.EMAIL_TO))
        return True
    except Exception as e:  # noqa: BLE001 — sähköpostivirhe ei saa kaataa ajoa
        log.error("Sähköpostin lähetys epäonnistui: %s", e)
        return False
