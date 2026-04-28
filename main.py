"""Padre Alpha Tracker — main polling loop."""

import logging
import os
import signal
import sys
import time
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

from src.db import (
    backfill_counts_from_groups, backfill_launchpad, init_db, purge_by_launchpad,
    purge_low_quality, purge_no_group, record_new_call, repair_call_aggregates_from_events, touch_seen,
)
from src.export_csv import export_daily_csv
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


def call_event_key(call: dict) -> str:
    ca = call.get("contract_address") or ""
    group = (call.get("groups_mentioned") or "").strip()
    text = (call.get("normalized_text") or call.get("_text") or "").strip()
    return call.get("event_key") or "|".join([ca, group or "-", call.get("call_bucket") or text])


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
    repaired = backfill_counts_from_groups(conn)
    if repaired:
        log.info("Repaired call_count from distinct groups on %d rows", repaired)
    repaired = repair_call_aggregates_from_events(conn)
    if repaired:
        log.info("Repaired %d daily call aggregate row(s) from raw call events", repaired)

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
    consecutive_empty_scrapes = 0

    while running:
        try:
            today = date.today()
            if today != current_date:
                export_daily_csv(conn, CSV_DIR, current_date)
                current_date = today
                new_today = 0

            calls = scrape_alpha_tracker(
                page,
                ignore_launchpads=IGNORE_LAUNCHPADS,
                require_quality=REQUIRE_QUALITY,
            )
            if calls:
                consecutive_empty_scrapes = 0
            else:
                consecutive_empty_scrapes += 1
                log.warning("Empty Alpha scrape #%d", consecutive_empty_scrapes)
                if consecutive_empty_scrapes >= 3:
                    log.warning("Recovering after %d empty scrapes: reload Padre page", consecutive_empty_scrapes)
                    page.reload(wait_until="domcontentloaded", timeout=45000)
                    page.wait_for_timeout(5000)
                    navigate_to_alpha(page, PADRE_URL)
                    consecutive_empty_scrapes = 0
                    time.sleep(POLL_INTERVAL)
                    continue

            processed_keys: set[str] = set()
            seeded = 0

            for call in calls:
                ca = call["contract_address"]
                key = call_event_key(call)
                if key in processed_keys:
                    continue
                processed_keys.add(key)

                result = record_new_call(conn, call)
                if result == "NEW":
                    new_today += 1
                    log.info(
                        "NEW    %s  ticker=%s  launchpad=%s  groups=%s",
                        ca, call.get("ticker"), call.get("launchpad"), call.get("groups_mentioned"),
                    )
                elif result == "RECALL":
                    log.info("RECALL %s  (additional raw call event)", ca)
                elif result == "DUP":
                    touch_seen(conn, call)

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
