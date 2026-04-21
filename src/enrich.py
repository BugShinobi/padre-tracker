"""External token enrichment via DexScreener batch API.

Design notes — optimized for the laptop-server constraints:
- Single SQLite table (`token_prices`) in the same DB, no extra process, no extra worker.
- Batch requests: up to 30 CAs per HTTP call (DexScreener API limit).
- Fetch lazily on dashboard read; cache 60s. User that reloads = 1 small batch/min max.
- Fail-open: if DexScreener is slow/down, return whatever is cached + None for the rest.
- Cache "no data found" too, so we don't retry dead tokens every poll.
"""

import logging
import sqlite3
import time

import requests

log = logging.getLogger(__name__)

DEX_BATCH_URL = "https://api.dexscreener.com/latest/dex/tokens/"
BATCH_SIZE = 30          # DexScreener hard limit per call
DEFAULT_TTL = 60         # seconds — prices change constantly, short cache
DEAD_TOKEN_TTL = 3600    # tokens with no DexScreener pair: re-check hourly, not per poll
HTTP_TIMEOUT = 5         # don't hang the dashboard if API is slow


def init_cache(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS token_prices (
            contract_address TEXT PRIMARY KEY,
            price_usd        REAL,
            market_cap       REAL,
            volume_h24       REAL,
            price_change_h24 REAL,
            liquidity_usd    REAL,
            pair_address     TEXT,
            dex_id           TEXT,
            fetched_at       INTEGER NOT NULL,
            has_data         INTEGER NOT NULL DEFAULT 1
        )
    """)
    conn.commit()


def _pick_best_pair(pairs: list[dict]) -> dict | None:
    """DexScreener can return multiple pairs per token — pick the highest-liquidity Solana one."""
    sol = [p for p in pairs if p.get("chainId") == "solana"]
    if not sol:
        return None
    return max(sol, key=lambda p: (p.get("liquidity") or {}).get("usd") or 0)


def _fetch_batch(cas: list[str]) -> dict[str, dict]:
    """One batched HTTP call. Returns {ca: dex_pair} only for CAs that have a Solana pair."""
    if not cas:
        return {}
    try:
        r = requests.get(DEX_BATCH_URL + ",".join(cas), timeout=HTTP_TIMEOUT)
        if r.status_code != 200:
            log.warning("DexScreener %d for batch of %d", r.status_code, len(cas))
            return {}
        pairs = (r.json() or {}).get("pairs") or []
    except Exception as e:
        log.warning("DexScreener fetch failed: %s", e)
        return {}

    by_ca: dict[str, list[dict]] = {}
    for p in pairs:
        base = (p.get("baseToken") or {}).get("address")
        if base:
            by_ca.setdefault(base, []).append(p)

    result = {}
    for ca, plist in by_ca.items():
        best = _pick_best_pair(plist)
        if best:
            result[ca] = best
    return result


def _write_cache(conn: sqlite3.Connection, ca: str, pair: dict | None, now: int) -> None:
    if pair is None:
        conn.execute(
            """INSERT OR REPLACE INTO token_prices
               (contract_address, fetched_at, has_data)
               VALUES (?, ?, 0)""",
            (ca, now),
        )
        return
    price = pair.get("priceUsd")
    conn.execute(
        """INSERT OR REPLACE INTO token_prices
           (contract_address, price_usd, market_cap, volume_h24,
            price_change_h24, liquidity_usd, pair_address, dex_id,
            fetched_at, has_data)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
        (
            ca,
            float(price) if price else None,
            pair.get("marketCap") or pair.get("fdv"),
            (pair.get("volume") or {}).get("h24"),
            (pair.get("priceChange") or {}).get("h24"),
            (pair.get("liquidity") or {}).get("usd"),
            pair.get("pairAddress"),
            pair.get("dexId"),
            now,
        ),
    )


def get_prices(
    conn: sqlite3.Connection,
    cas: list[str],
    ttl: int = DEFAULT_TTL,
) -> dict[str, dict]:
    """Return {ca: price_row_dict} for each CA, fetching missing/stale in batch.

    price_row_dict keys: price_usd, market_cap, volume_h24, price_change_h24,
    liquidity_usd, pair_address, dex_id, fetched_at, has_data (0 or 1).
    CAs with no DexScreener pair still get a row with has_data=0.
    """
    if not cas:
        return {}

    init_cache(conn)
    cas = list(dict.fromkeys(cas))   # de-dup, keep order
    now = int(time.time())
    fresh_cutoff = now - ttl
    dead_cutoff = now - DEAD_TOKEN_TTL

    placeholders = ",".join("?" * len(cas))
    rows = conn.execute(
        f"SELECT * FROM token_prices WHERE contract_address IN ({placeholders})",
        tuple(cas),
    ).fetchall()
    cached = {r["contract_address"]: dict(r) for r in rows}

    stale: list[str] = []
    for ca in cas:
        row = cached.get(ca)
        if row is None:
            stale.append(ca)
        elif row["has_data"] == 1 and row["fetched_at"] < fresh_cutoff:
            stale.append(ca)
        elif row["has_data"] == 0 and row["fetched_at"] < dead_cutoff:
            stale.append(ca)

    if stale:
        log.info("Enriching %d CA(s) via DexScreener (batch size %d)", len(stale), BATCH_SIZE)
        for i in range(0, len(stale), BATCH_SIZE):
            batch = stale[i:i + BATCH_SIZE]
            found = _fetch_batch(batch)
            for ca in batch:
                _write_cache(conn, ca, found.get(ca), now)
        conn.commit()

        rows = conn.execute(
            f"SELECT * FROM token_prices WHERE contract_address IN ({placeholders})",
            tuple(cas),
        ).fetchall()
        cached = {r["contract_address"]: dict(r) for r in rows}

    return cached
