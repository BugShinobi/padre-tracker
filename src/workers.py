"""Padre-tracker enrichment workers — DB-poll daemon.

Three independent loops in one process, decoupled from the dashboard so frontend
load can never starve the data pipeline:

  - gmgn_loop:     scans `calls` for CAs missing/stale in `token_gmgn`
  - metadata_loop: scans `calls` for CAs missing/stale in `token_metadata`
  - prices_loop:   scans `calls` for active CAs missing/stale in `token_prices`

Discovery is done by SQL `LEFT JOIN ... WHERE fetched_at < cutoff` — no in-memory
queue, so a restart loses no state and the dashboard never enqueues.

Run modes:
  python -m src.workers                       # daemon, all 3 loops
  python -m src.workers --once --type=gmgn    # single scan, exit (dry run on prod DB)
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sqlite3
import sys
import threading
import time
from typing import Callable

from dotenv import load_dotenv

from src import gmgn, metadata, enrich
from src.db import init_db

load_dotenv()

DB_PATH = os.getenv("DB_PATH", "./data/calls.db")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
HELIUS_API_KEY = os.getenv("HELIUS_API_KEY", "")

GMGN_POLL_INTERVAL = int(os.getenv("GMGN_POLL_INTERVAL", "30"))
METADATA_POLL_INTERVAL = int(os.getenv("METADATA_POLL_INTERVAL", "60"))
PRICES_POLL_INTERVAL = int(os.getenv("PRICES_POLL_INTERVAL", "60"))

GMGN_BATCH = int(os.getenv("GMGN_BATCH", "50"))
METADATA_BATCH = int(os.getenv("METADATA_BATCH", "30"))
PRICES_ACTIVE_DAYS = int(os.getenv("PRICES_ACTIVE_DAYS", "7"))
MIN_LIQUIDITY_USD = float(os.getenv("MIN_LIQUIDITY_USD", "5000"))

GMGN_BREAKER_THRESHOLD = 3        # consecutive empty results → abort scan
GMGN_BREAKER_COOLDOWN = 300       # seconds to wait after circuit trip

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("padre-workers")

_running = True


def _shutdown(_sig, _frame):
    global _running
    log.info("shutdown signal received — workers will exit after current iteration")
    _running = False


def _open_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _scan_stale_simple(
    conn: sqlite3.Connection,
    table: str,
    fresh_ttl: int,
    dead_ttl: int,
    batch: int,
) -> list[str]:
    """Find CAs in `calls` that are missing or stale in `table`. Returns up to `batch` CAs."""
    now = int(time.time())
    fresh_cutoff = now - fresh_ttl
    dead_cutoff = now - dead_ttl
    rows = conn.execute(
        f"""
        SELECT DISTINCT calls.contract_address AS ca
        FROM calls
        LEFT JOIN {table} t ON calls.contract_address = t.contract_address
        WHERE t.contract_address IS NULL
           OR (t.has_data = 1 AND t.fetched_at < ?)
           OR (t.has_data = 0 AND t.fetched_at < ?)
        ORDER BY calls.first_seen_at DESC
        LIMIT ?
        """,
        (fresh_cutoff, dead_cutoff, batch),
    ).fetchall()
    return [r["ca"] for r in rows]


def _scan_stale_active(
    conn: sqlite3.Connection,
    table: str,
    fresh_ttl: int,
    dead_ttl: int,
    active_days: int,
    batch: int,
) -> list[str]:
    """Like _scan_stale_simple but restricted to recently-active calls."""
    now = int(time.time())
    fresh_cutoff = now - fresh_ttl
    dead_cutoff = now - dead_ttl
    rows = conn.execute(
        f"""
        SELECT DISTINCT calls.contract_address AS ca
        FROM calls
        LEFT JOIN {table} t ON calls.contract_address = t.contract_address
        WHERE calls.first_seen_at >= datetime('now', ?)
          AND (t.contract_address IS NULL
               OR (t.has_data = 1 AND t.fetched_at < ?)
               OR (t.has_data = 0 AND t.fetched_at < ?))
        ORDER BY calls.first_seen_at DESC
        LIMIT ?
        """,
        (f"-{active_days} days", fresh_cutoff, dead_cutoff, batch),
    ).fetchall()
    return [r["ca"] for r in rows]


def gmgn_scan_once() -> tuple[int, int, int, bool]:
    """Run a single GMGN scan. Returns (scanned, fetched_with_data, errors, breaker_tripped)."""
    conn = _open_conn()
    try:
        stale = _scan_stale_simple(conn, "token_gmgn", gmgn.FRESH_TTL, gmgn.DEAD_TTL, GMGN_BATCH)
    finally:
        conn.close()

    if not stale:
        return 0, 0, 0, False

    fetched = 0
    errors = 0
    consecutive_empty = 0
    breaker_tripped = False

    for i, ca in enumerate(stale):
        if not _running:
            break
        if i > 0:
            time.sleep(gmgn.RATE_SLEEP)
        try:
            # Inline the gmgn fetch+write so we can observe the result for the breaker.
            c = sqlite3.connect(DB_PATH, timeout=30)
            c.row_factory = sqlite3.Row
            try:
                gmgn.init_cache(c)
                now = int(time.time())
                result = gmgn._fetch_one(ca)
                gmgn._write_cache(c, result, ca, now)
                c.commit()
            finally:
                c.close()
            if result is None:
                consecutive_empty += 1
            else:
                consecutive_empty = 0
                fetched += 1
        except Exception as e:
            errors += 1
            log.warning("gmgn fetch error ca=%s err=%s", ca[:8], e)
            consecutive_empty += 1

        if consecutive_empty >= GMGN_BREAKER_THRESHOLD:
            log.warning(
                "gmgn circuit breaker tripped after %d consecutive empty results — aborting scan",
                consecutive_empty,
            )
            breaker_tripped = True
            break

    return len(stale), fetched, errors, breaker_tripped


def metadata_scan_once() -> tuple[int, int, int]:
    """Run a single metadata scan. Returns (scanned, fetched_with_data, errors)."""
    if not HELIUS_API_KEY:
        log.warning("metadata loop skipped — HELIUS_API_KEY missing")
        return 0, 0, 0

    conn = _open_conn()
    try:
        stale = _scan_stale_simple(
            conn, "token_metadata", metadata.FRESH_TTL, metadata.DEAD_TTL, METADATA_BATCH
        )
    finally:
        conn.close()

    if not stale:
        return 0, 0, 0

    fetched = 0
    errors = 0
    for i, ca in enumerate(stale):
        if not _running:
            break
        if i > 0:
            time.sleep(metadata.RATE_SLEEP)
        try:
            c = sqlite3.connect(DB_PATH, timeout=30)
            c.row_factory = sqlite3.Row
            try:
                metadata.init_cache(c)
                now = int(time.time())
                result = metadata._fetch_one(HELIUS_API_KEY, ca)
                metadata._write_cache(c, result, ca, now)
                c.commit()
            finally:
                c.close()
            if result is not None and result.get("description"):
                fetched += 1
        except Exception as e:
            errors += 1
            log.warning("metadata fetch error ca=%s err=%s", ca[:8], e)

    return len(stale), fetched, errors


def prices_scan_once() -> tuple[int, int, int]:
    """Run a single prices scan. Returns (scanned, fetched_with_data, errors).

    `enrich.get_prices` already batches DexScreener calls (30/req) and writes
    UPSERTs that preserve ATH. We only feed it the stale list to avoid
    re-querying every active CA every cycle.

    After enrichment, purges low-liquidity tokens — see `_cleanup_low_liquidity`.
    """
    conn = _open_conn()
    try:
        stale = _scan_stale_active(
            conn,
            "token_prices",
            enrich.DEFAULT_TTL,
            enrich.DEAD_TOKEN_TTL,
            PRICES_ACTIVE_DAYS,
            500,  # cap per scan; DexScreener will be batched 30/call inside get_prices
        )

        scanned = len(stale)
        fetched = 0
        errors = 0
        if stale:
            try:
                result = enrich.get_prices(conn, stale)
                fetched = sum(1 for r in result.values() if r and r.get("has_data") == 1)
            except Exception as e:
                log.warning("prices fetch error: %s", e)
                errors = 1

        purged = _cleanup_low_liquidity(conn)
        if purged:
            log.info("low-liquidity cleanup deleted %d token(s) below $%g", purged, MIN_LIQUIDITY_USD)

        return scanned, fetched, errors
    finally:
        conn.close()


def _cleanup_low_liquidity(conn: sqlite3.Connection) -> int:
    """Delete tokens whose latest liquidity is below MIN_LIQUIDITY_USD.

    Cascades the delete across all enrichment tables so re-discovery starts
    from a clean slate.
    """
    if MIN_LIQUIDITY_USD <= 0:
        return 0

    rows = conn.execute(
        """SELECT contract_address
           FROM token_prices
           WHERE has_data = 1
             AND liquidity_usd IS NOT NULL
             AND liquidity_usd < ?""",
        (MIN_LIQUIDITY_USD,),
    ).fetchall()
    if not rows:
        return 0

    cas = [r["contract_address"] for r in rows]
    placeholders = ",".join("?" * len(cas))
    for table in ("calls", "token_prices", "token_gmgn", "token_metadata"):
        try:
            conn.execute(
                f"DELETE FROM {table} WHERE contract_address IN ({placeholders})",
                tuple(cas),
            )
        except sqlite3.OperationalError as e:
            log.debug("cleanup skip table=%s err=%s", table, e)
    conn.commit()
    return len(cas)


def _loop(
    name: str,
    interval: int,
    scan_fn: Callable[[], tuple],
    on_breaker_cooldown: int = 0,
):
    """Generic loop: run scan_fn() every `interval` seconds while _running.

    scan_fn returns (scanned, fetched, errors) or (scanned, fetched, errors, breaker).
    """
    log.info("%s loop started interval=%ds", name, interval)
    while _running:
        start = time.time()
        try:
            res = scan_fn()
            breaker = False
            if len(res) == 4:
                scanned, fetched, errors, breaker = res
            else:
                scanned, fetched, errors = res
            dur = time.time() - start
            log.info(
                "%s scan complete scanned=%d fetched=%d errors=%d dur=%.1fs",
                name, scanned, fetched, errors, dur,
            )
            if breaker and on_breaker_cooldown > 0:
                log.info("%s sleeping %ds for circuit-breaker cooldown", name, on_breaker_cooldown)
                _sleep_interruptible(on_breaker_cooldown)
                continue
        except Exception as e:
            log.error("%s loop error: %s", name, e, exc_info=True)

        _sleep_interruptible(interval)
    log.info("%s loop exited", name)


def _sleep_interruptible(seconds: float) -> None:
    """Sleep but wake up promptly when _running is cleared."""
    end = time.time() + seconds
    while _running and time.time() < end:
        time.sleep(min(0.5, end - time.time()))


def _bootstrap_caches() -> None:
    """Run init_db + all init_cache once at boot under a shared connection."""
    conn = init_db(DB_PATH)
    try:
        gmgn.init_cache(conn)
        metadata.init_cache(conn)
        enrich.init_cache(conn)
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Padre-tracker enrichment workers")
    parser.add_argument("--once", action="store_true", help="Run a single scan and exit")
    parser.add_argument(
        "--type",
        choices=["gmgn", "metadata", "prices"],
        help="Scan type for --once mode",
    )
    args = parser.parse_args()

    _bootstrap_caches()

    if args.once:
        if not args.type:
            parser.error("--once requires --type=gmgn|metadata|prices")
        start = time.time()
        if args.type == "gmgn":
            scanned, fetched, errors, _ = gmgn_scan_once()
        elif args.type == "metadata":
            scanned, fetched, errors = metadata_scan_once()
        else:
            scanned, fetched, errors = prices_scan_once()
        dur = time.time() - start
        log.info(
            "%s once complete scanned=%d fetched=%d errors=%d dur=%.1fs",
            args.type, scanned, fetched, errors, dur,
        )
        return

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    threads = [
        threading.Thread(
            target=_loop,
            args=("gmgn", GMGN_POLL_INTERVAL, gmgn_scan_once, GMGN_BREAKER_COOLDOWN),
            name="gmgn-loop",
            daemon=True,
        ),
        threading.Thread(
            target=_loop,
            args=("metadata", METADATA_POLL_INTERVAL, metadata_scan_once),
            name="metadata-loop",
            daemon=True,
        ),
        threading.Thread(
            target=_loop,
            args=("prices", PRICES_POLL_INTERVAL, prices_scan_once),
            name="prices-loop",
            daemon=True,
        ),
    ]
    for t in threads:
        t.start()

    log.info("padre-workers started — 3 loops running")

    while _running:
        time.sleep(1)

    for t in threads:
        t.join(timeout=15)
    log.info("padre-workers shutdown complete")


if __name__ == "__main__":
    main()
