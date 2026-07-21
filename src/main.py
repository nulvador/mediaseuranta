"""Golf Media Monitor v2 — pääohjelma.

Käyttö:
    python -m src.main                     # normaali ajo
    python -m src.main --skip-analysis     # vain keruu + raportti
    python -m src.main --report-only       # generoi raportti nykyisestä datasta
    python -m src.main --import-json PATH  # tuo vanhan projektin articles.json
    python -m src.main --no-email          # älä lähetä sähköpostia
"""
import argparse
import datetime
import logging
import sys

from . import config, store
from .analyze import analyze_pending
from .fetch import fetch_all
from .report import write_report
from .emailer import send_report
from .sources import load_sources


def setup_logging() -> None:
    logfile = config.LOG_DIR / f"monitor_{datetime.date.today():%Y%m%d}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout),
                  logging.FileHandler(logfile, encoding="utf-8")],
    )
    # Hiljennä kirjastojen tekninen kohina (AFC/HTTP-rivit)
    for noisy in ("google_genai", "google_genai.models", "httpx", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def main() -> int:
    parser = argparse.ArgumentParser(description="Golf Media Monitor v2")
    parser.add_argument("--skip-analysis", action="store_true")
    parser.add_argument("--report-only", action="store_true")
    parser.add_argument("--no-email", action="store_true")
    parser.add_argument("--reanalyze", nargs="?", const="all", metavar="TAB",
                        help="analysoi artikkelit uudelleen (promptin muututtua). "
                             "Valinnainen välilehti: golfliitot | urheilu_liitot")
    parser.add_argument("--purge", metavar="SOURCE_ID", action="append",
                        help="poista lähteen kaikki artikkelit ennen keruuta (voi toistaa)")
    parser.add_argument("--import-json", metavar="PATH")
    args = parser.parse_args()

    setup_logging()
    log = logging.getLogger("main")
    started = datetime.datetime.now().isoformat(timespec="seconds")
    conn = store.connect()
    previous_run_at = store.last_run_finished_at(conn)

    if args.import_json:
        n = store.import_legacy_json(conn, args.import_json)
        log.info("Migraatio valmis: %d artikkelia tuotu", n)
        return 0

    for source_id in (args.purge or []):
        n = store.purge_source(conn, source_id)
        log.info("Poistettu %d artikkelia lähteestä %s", n, source_id)

    if args.reanalyze:
        tab = None if args.reanalyze == "all" else args.reanalyze
        n = store.reset_analysis(conn, tab)
        log.info("Uudelleenanalyysi%s: %d artikkelia palautettu jonoon",
                 f" ({tab})" if tab else "", n)

    healths: list[dict] = []
    new_count = 0

    # ── Vaihe 1: keruu ────────────────────────────────────────────────
    if not args.report_only:
        sources, _ = load_sources()
        moved = store.sync_tabs(conn, sources)
        if moved:
            log.info("Välilehtisynkronointi: %d artikkelia siirretty", moved)
        removed = store.purge_missing_sources(conn, sources)
        if removed:
            log.info("Siivous: %d artikkelia poistetuilta lähteiltä", removed)
        since = datetime.date.today() - datetime.timedelta(days=config.LOOKBACK_DAYS)
        log.info("Keruu: %d lähdettä, artikkelit %s alkaen", len(sources), since)
        articles, healths = fetch_all(sources, since)
        new_count = store.insert_new(conn, articles)   # checkpoint: raakadata talteen heti
        log.info("Kerätty %d artikkelia, joista uusia %d", len(articles), new_count)

        dead = [h for h in healths if h["count"] == 0]
        if dead:
            log.warning("LÄHTEET ILMAN ARTIKKELEITA (%d): %s",
                        len(dead), ", ".join(h["source_id"] for h in dead))

    # ── Vaihe 2: analyysi (jatkaa myös edellisen ajon kesken jääneitä) ─
    analyzed = failed = 0
    if not args.report_only and not args.skip_analysis:
        pending = store.pending_articles(conn)
        if pending:
            log.info("Analysoidaan %d artikkelia (%d/erä, malli: %s)",
                     len(pending), config.BATCH_SIZE, config.GEMINI_MODEL)
            try:
                analyzed, failed = analyze_pending(
                    pending, save_cb=lambda results: store.save_analysis(conn, results))
            except KeyboardInterrupt:
                log.warning("Keskeytetty (Ctrl-C) — tähän mennessä analysoidut ovat "
                            "tallessa, loput jäävät jonoon. Generoidaan raportti.")
                analyzed, failed = 0, 0
            log.info("Analysoitu %d, epäonnistuneita eriä %d", analyzed, failed)
            if failed:
                log.warning("Epäonnistuneiden erien artikkelit jäivät 'new'-tilaan "
                            "ja analysoidaan seuraavassa ajossa.")
        else:
            log.info("Ei analysoitavaa.")

    # ── Vaihe 3: raportti ─────────────────────────────────────────────
    run_summary = {"new_articles": new_count, "analyzed": analyzed,
                   "previous_run_at": previous_run_at}
    report_arts = store.report_articles(conn, config.REPORT_DAYS)
    path = write_report(report_arts, healths, run_summary)
    log.info("Raportti: %s (%d artikkelia)", path, len(report_arts))

    # ── Vaihe 4: sähköposti (valinnainen) ─────────────────────────────
    if not args.no_email:
        recent_cutoff = (datetime.date.today()
                         - datetime.timedelta(days=config.LOOKBACK_DAYS)).isoformat()
        recent = [a for a in report_arts if (a.get("published") or "") >= recent_cutoff]
        send_report(recent, run_summary, path)

    store.log_run(conn, started, new_count, analyzed, failed, healths)
    conn.close()

    log.info("=" * 50)
    log.info("Valmis. Uusia: %d · Analysoitu: %d · Epäonnistuneita eriä: %d",
             new_count, analyzed, failed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
