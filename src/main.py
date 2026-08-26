"""Golf Media Monitor v2 — pääohjelma.

Käyttö:
    python -m src.main                     # normaali ajo
    python -m src.main --skip-analysis     # vain keruu + raportti
    python -m src.main --report-only       # generoi raportti nykyisestä datasta
    python -m src.main --import-json PATH  # tuo vanhan projektin articles.json
    python -m src.main --no-email          # älä lähetä sähköpostia

    python -m src.main --apply-corrections korjaukset.json --report-only
                                           # vie raportista viedyt korjaukset kantaan
    python -m src.main --list-corrections  # katselmoimattomat korjaukset + jakauma
    python -m src.main --mark-reviewed     # merkitse erä käsitellyksi kalibroinnin jälkeen
"""
import argparse
import datetime
import json
import logging
import sys
from pathlib import Path

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


def _load_corrections(path: str) -> list[dict]:
    """Lue raportista kopioitu korjaus-JSON.

    Hyväksyy sekä listan että url_hash-avaimisen objektin, koska raportin
    localStorage on objekti ja vientinappi antaa listan — kumpi tahansa voi
    päätyä liitetyksi tiedostoon."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = list(data.values())
    if not isinstance(data, list):
        raise ValueError("Odotettiin listaa tai objektia korjauksista")
    return data


_PRIO_RANK = {"korkea": 0, "keskitaso": 1, "matala": 2}


def _correction_direction(c: dict) -> str:
    """Korjauksen suunta. Tämä on se luku, joka paljastaa aineiston vinouman:
    ylinostot huomaa punaisena kortin kärjessä, portin karsintavirheen vain
    raakalistasta, joten 'laskettu' kertyy väistämättä nopeammin."""
    if c["verdict"] == "exclude":
        return "pois katsauksesta"
    if c["verdict"] == "include":
        return "nostettu katsaukseen"
    was = _PRIO_RANK.get(c.get("was_priority") or "", 9)
    now = _PRIO_RANK.get(c.get("priority") or "", 9)
    return "nostettu" if now < was else "laskettu" if now > was else "muutettu"


def main() -> int:
    parser = argparse.ArgumentParser(description="Golf Media Monitor v2")
    parser.add_argument("--skip-analysis", action="store_true")
    parser.add_argument("--report-only", action="store_true")
    parser.add_argument("--no-email", action="store_true")
    parser.add_argument("--reanalyze", nargs="?", const="all", metavar="TAB",
                        help="analysoi raportti-ikkunan artikkelit uudelleen "
                             "(promptin muututtua). Valinnainen välilehti: "
                             "golfliitot | urheilu_liitot | media")
    parser.add_argument("--purge", metavar="SOURCE_ID", action="append",
                        help="poista lähteen kaikki artikkelit ennen keruuta (voi toistaa)")
    parser.add_argument("--dedupe", action="store_true",
                        help="poista samasta jutusta kertyneet kaksoiskappaleet "
                             "(sama otsikko, eri linkkireitti)")
    parser.add_argument("--restore", action="store_true",
                        help="palauta 'new'-tilaan jääneet jo analysoidut artikkelit "
                             "näkyviin (korjaa keskeytyneen uudelleenanalyysin)")
    parser.add_argument("--apply-corrections", metavar="PATH",
                        help="vie raportista kopioidut prioriteettikorjaukset "
                             "kantaan (ei kuluta Gemini-kutsuja)")
    parser.add_argument("--list-corrections", action="store_true",
                        help="tulosta katselmoimattomat korjaukset ja niiden "
                             "jakauma — kalibrointikierroksen aineisto")
    parser.add_argument("--mark-reviewed", action="store_true",
                        help="merkitse korjaukset käsitellyiksi promptin "
                             "päivityksen jälkeen (rivit jäävät kantaan)")
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

    if args.list_corrections:
        rows = store.pending_corrections(conn)
        log.info("Katselmoimattomia korjauksia: %d", len(rows))
        by_dir: dict[str, int] = {}
        by_tab: dict[str, int] = {}
        for c in rows:
            d = _correction_direction(c)
            by_dir[d] = by_dir.get(d, 0) + 1
            by_tab[c["tab"] or "?"] = by_tab.get(c["tab"] or "?", 0) + 1
        for d, n in sorted(by_dir.items(), key=lambda kv: -kv[1]):
            log.info("  %-22s %d", d, n)
        for t, n in sorted(by_tab.items(), key=lambda kv: -kv[1]):
            log.info("  %-22s %d", t, n)
        for c in rows:
            log.info("%s · %s · %s → %s%s", c["created_at"][:10], c["source_name"],
                     c["was_priority"] or "karsittu", _correction_direction(c),
                     f' · {c["reason"]}' if c["reason"] else "")
            log.info("    %s", c["title_fi"] or c["title"])
        if len(rows) >= 30:
            log.info("30 korjausta täynnä — aika lukea prompti kokonaisuutena "
                     "ja kuiva-ajaa muutos tätä aineistoa vasten.")
        conn.close()
        return 0

    if args.mark_reviewed:
        n = store.mark_corrections_reviewed(conn)
        log.info("Merkitty käsitellyksi: %d korjausta (rivit jäävät kantaan "
                 "testiaineistoksi)", n)
        conn.close()
        return 0

    if args.apply_corrections:
        try:
            items = _load_corrections(args.apply_corrections)
        except (OSError, ValueError) as e:
            log.error("Korjaustiedostoa ei voitu lukea (%s): %s",
                      args.apply_corrections, e)
            log.error("Odotettu sisältö on raportin \"Omat korjaukset\" -paneelista "
                      "kopioitu JSON sellaisenaan.")
            conn.close()
            return 1
        added, updated = store.save_corrections(conn, items)
        log.info("Korjaukset: %d uutta, %d päivitettyä", added, updated)

    for source_id in (args.purge or []):
        n = store.purge_source(conn, source_id)
        log.info("Poistettu %d artikkelia lähteestä %s", n, source_id)

    if args.dedupe:
        n = store.dedupe_by_title(conn)
        log.info("Kaksoiskappaleet: poistettu %d riviä", n)

    if args.restore:
        n = store.restore_stale(conn)
        log.info("Palautettu %d artikkelia näkyviin (stale)", n)

    # Retention: poista hyvin vanhat kokonaan (dedup-historia säilyy siihen asti)
    removed_old = store.purge_old(conn, config.RETENTION_DAYS)
    if removed_old:
        log.info("Retention: poistettu %d yli %d pv vanhaa artikkelia",
                 removed_old, config.RETENTION_DAYS)

    if args.reanalyze:
        tab = None if args.reanalyze == "all" else args.reanalyze
        n = store.reset_analysis(conn, tab)
        log.info("Uudelleenanalyysi%s: %d artikkelia palautettu jonoon "
                 "(analyysi-ikkuna %d pv)",
                 f" ({tab})" if tab else "", n, config.ANALYZE_DAYS)

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

        media_n = sum(h["count"] for h in healths if h["tab"] == config.MEDIA_TAB)
        if media_n:
            log.info("Suomalainen media: %d osumaa", media_n)

        # Media-hakujen nollatulos on normaali, ei vika: nimihaku osuu harvoin.
        # Liittolähteen nolla sen sijaan kannattaa aina tarkistaa.
        dead = [h for h in healths
                if h["count"] == 0 and h["tab"] != config.MEDIA_TAB]
        if dead:
            log.warning("LÄHTEET ILMAN ARTIKKELEITA (%d): %s",
                        len(dead), ", ".join(h["source_id"] for h in dead))
        quiet = [h for h in healths
                 if h["count"] == 0 and h["tab"] == config.MEDIA_TAB]
        if quiet:
            log.info("Mediahakuja ilman osumia (%d): %s",
                     len(quiet), ", ".join(h["source_id"] for h in quiet))

    # ── Vaihe 2: analyysi (jatkaa myös edellisen ajon kesken jääneitä) ─
    analyzed = failed = 0
    if not args.report_only and not args.skip_analysis:
        # Vanhentuneita ei analysoida — kutsut säästyvät tuoreille uutisille
        expired = store.expire_old_pending(conn, config.ANALYZE_DAYS)
        if expired:
            log.info("Vanhentunut jonosta: %d artikkelia (yli %d pv vanhoja)",
                     expired, config.ANALYZE_DAYS)

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

    # ── Vaihe 3: ihmisen korjaukset analyysin päälle ──────────────────
    # Tämä ajetaan JOKA ajossa eikä vain --apply-corrections-kutsussa: tuore
    # Gemini-arvio kirjoittaisi muuten korjauksen yli heti seuraavassa ajossa.
    # Sijainti on tarkoituksellisesti analyysin jälkeen ja raportin edellä.
    fixed = store.apply_corrections(conn)
    if fixed:
        log.info("Ihmisen korjaukset: %d artikkelia asetettu korjattuun arvioon", fixed)

    # ── Vaihe 4: raportti ─────────────────────────────────────────────
    run_summary = {"new_articles": new_count, "analyzed": analyzed,
                   "previous_run_at": previous_run_at}
    report_arts = store.report_articles(conn, config.REPORT_DAYS)
    # Raakalista näyttää myös karsitut ja analysoimattomat, joten se on
    # varmistus suodatusta vasten. Ikkuna on nyt sama kuin katsauksen, eli
    # katsauksesta pudonnut juttu ei jää raakalistallekaan roikkumaan.
    raw_arts = store.raw_articles(conn, config.RAW_DAYS)
    media_arts = sum(1 for a in report_arts if a["tab"] == config.MEDIA_TAB)
    path = write_report(report_arts, healths, run_summary, raw_arts)
    log.info("Raportti: %s (%d artikkelia, joista mediaa %d; raakalistalla %d)",
             path, len(report_arts), media_arts, len(raw_arts))

    # ── Vaihe 5: sähköposti (valinnainen) ─────────────────────────────
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
