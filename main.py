"""Padre Alpha Tracker — main polling loop."""

import logging
import os
import signal
import sqlite3
import sys
import threading
import time
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

from src.db import (
    backfill_launchpad, get_today_cas, init_db, purge_by_launchpad,
    purge_low_quality, purge_no_group, record_new_call, reset_today_counts, touch_seen,
)
from src.export_csv import export_daily_csv
from src.gmgn import get_gmgn
from src.scraper import (
    detect_launchpad, dump_page_html, get_live_page,
    launch_browser, navigate_to_alpha, register_page_listeners, scrape_alpha_tracker,
)

load_dotenv()

POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "30"))
PADRE_URL = os.getenv("PADRE_URL", "https://trade.padre.gg")
SESSION_DIR = os.getenv("SESSION_DIR", "./data/session")
DB_PATH = os.getenv("DB_PATH", "./data/calls.db")
CSV_DIR = os.getenv("CSV_DIR", "./data/csv")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

IGNORE_LAUNCHPADS = {
    lp.strip() for lp in os.getenv("IGNORE_LAUNCHPADS", "").split(",") if lp.strip()
}
REQUIRE_QUALITY = os.getenv("REQUIRE_QUALITY", "1") not in ("0", "false", "False", "")

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/scraper.log", mode="a"),
    ],
)
log = logging.getLogger("padre-tracker")


def _gmgn_prewarm(db_path: str, ca: str) -> None:
    """Fire-and-forget: fetch GMGN data for a single CA into the cache."""
    try:
        c = sqlite3.connect(db_path)
        c.row_factory = sqlite3.Row
        get_gmgn(c, [ca])
        c.close()
    except Exception as e:
        log.debug("GMGN prewarm failed for %s: %s", ca[:8], e)


def _gmgn_backfill(db_path: str) -> None:
    """Startup backfill: fetch GMGN for recent CAs not yet in cache (background thread)."""
    try:
        c = sqlite3.connect(db_path)
        c.row_factory = sqlite3.Row
        from src.gmgn import init_cache as _ginit
        _ginit(c)
        rows = c.execute(
            """SELECT DISTINCT calls.contract_address
               FROM calls
               LEFT JOIN token_gmgn g ON calls.contract_address = g.contract_address
               WHERE calls.call_date >= date('now', '-3 days')
                 AND g.contract_address IS NULL
               LIMIT 200"""
        ).fetchall()
        cas = [r["contract_address"] for r in rows]
        c.close()
        if not cas:
            return
        log.info("GMGN backfill: %d CAs without cache", len(cas))
        c2 = sqlite3.connect(db_path)
        c2.row_factory = sqlite3.Row
        get_gmgn(c2, cas)
        c2.close()
        log.info("GMGN backfill complete")
    except Exception as e:
        log.warning("GMGN backfill error: %s", e)


def setup_dirs():
    for d in [SESSION_DIR, CSV_DIR, "logs"]:
        Path(d).mkdir(parents=True, exist_ok=True)


def main():
    dump_mode = "--dump" in sys.argv
    setup_dirs()

    conn = init_db(DB_PATH)
    backfilled = backfill_launchpad(conn, detect_launchpad)
    if backfilled:
        log.info("Backfilled launchpad on %d existing rows", backfilled)

    # One-shot cleanup on startup: apply current filter policy to historical rows.
    if IGNORE_LAUNCHPADS:
        purged_lp = purge_by_launchpad(conn, IGNORE_LAUNCHPADS)
        if purged_lp:
            log.info("Purged %d rows with ignored launchpad(s): %s", purged_lp, sorted(IGNORE_LAUNCHPADS))
    if REQUIRE_QUALITY:
        purged_q = purge_low_quality(conn)
        if purged_q:
            log.info("Purged %d low-quality rows (no ticker and no group)", purged_q)
    purged_ng = purge_no_group(conn)
    if purged_ng:
        log.info("Purged %d rows without group (DEX Paid / ad noise)", purged_ng)
    reset = reset_today_counts(conn)
    if reset:
        log.info("Reset call_count=1 on %d today-rows (fixing pre-bug inflated counters)", reset)

    # GMGN backfill in background — fetch data for recent CAs missing from cache
    threading.Thread(target=_gmgn_backfill, args=(DB_PATH,), daemon=True).start()

    pw, context = launch_browser(SESSION_DIR)
    register_page_listeners(context)
    page = get_live_page(context)

    running = True

    def shutdown(sig, frame):
        nonlocal running
        log.info("Shutting down...")
        running = False

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    navigate_to_alpha(page, PADRE_URL)

    # Diagnostic mode: dump HTML and exit — use to inspect DOM when calls=0
    if dump_mode:
        dump_page_html(page, "logs/page_dump.html")
        log.info("Dump complete. Open logs/page_dump.html to inspect the DOM.")
        context.close()
        pw.stop()
        conn.close()
        return

    log.info("Monitoring Alpha Tracker (interval: %ds)", POLL_INTERVAL)
    log.info("First run: log in manually in the browser, session is saved for future runs.")

    current_date = date.today()
    new_today = 0

    # Seed in-memory "previously visible" set from today's DB rows so a restart
    # doesn't re-count CAs that are still on the feed.
    previously_visible: set[str] = get_today_cas(conn)
    if previously_visible:
        log.info("Resuming with %d CAs already recorded today", len(previously_visible))

    while running:
        try:
            today = date.today()
            if today != current_date:
                export_daily_csv(conn, CSV_DIR, current_date)
                current_date = today
                new_today = 0
                previously_visible = set()

            calls = scrape_alpha_tracker(
                page,
                ignore_launchpads=IGNORE_LAUNCHPADS,
                require_quality=REQUIRE_QUALITY,
            )
            current_cas = {c["contract_address"] for c in calls}
            newly_visible = current_cas - previously_visible

            for call in calls:
                ca = call["contract_address"]
                if ca in newly_visible:
                    result = record_new_call(conn, call)
                    if result == "NEW":
                        new_today += 1
                        log.info(
                            "NEW    %s  ticker=%s  launchpad=%s  groups=%s",
                            ca, call.get("ticker"), call.get("launchpad"), call.get("groups_mentioned"),
                        )
                        # Pre-warm GMGN cache in background so dashboard reads are instant
                        threading.Thread(
                            target=_gmgn_prewarm, args=(DB_PATH, ca), daemon=True
                        ).start()
                    elif result == "RECALL":
                        log.info("RECALL %s  (re-appeared on feed)", ca)
                else:
                    touch_seen(conn, call)

            previously_visible = current_cas

            if calls:
                export_daily_csv(conn, CSV_DIR, current_date)

            time.sleep(POLL_INTERVAL)

        except KeyboardInterrupt:
            break
        except Exception as e:
            err_msg = str(e)
            log.error("Scrape error: %s", err_msg)
            # Page/browser closed → rebuild page and re-navigate before retrying.
            if "closed" in err_msg.lower() or "target" in err_msg.lower():
                try:
                    log.info("Recovering: getting fresh page and re-navigating...")
                    page = get_live_page(context)
                    navigate_to_alpha(page, PADRE_URL)
                    log.info("Recovery complete.")
                except Exception as rec:
                    log.error("Recovery failed: %s", rec, exc_info=True)
            time.sleep(POLL_INTERVAL * 2)

    export_daily_csv(conn, CSV_DIR, current_date)
    context.close()
    pw.stop()
    conn.close()
    log.info("Shutdown complete. New calls today: %d", new_today)


if __name__ == "__main__":
    main()
