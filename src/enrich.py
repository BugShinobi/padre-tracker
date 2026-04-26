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
    # ATH tracking columns — added 2026-04-25. Rolling max updated on every fetch.
    existing = {r[1] for r in conn.execute("PRAGMA table_info(token_prices)").fetchall()}
    for col, ddl in (
        ("price_ath",        "REAL"),
        ("price_ath_at",     "INTEGER"),
        ("market_cap_ath",   "REAL"),
        ("market_cap_ath_at","INTEGER"),
    ):
        if col not in existing:
            conn.execute(f"ALTER TABLE token_prices ADD COLUMN {col} {ddl}")
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
        # Preserve any previously-recorded ATH — INSERT OR REPLACE would wipe it.
        conn.execute(
            """INSERT INTO token_prices (contract_address, fetched_at, has_data)
               VALUES (?, ?, 0)
               ON CONFLICT(contract_address) DO UPDATE SET
                   fetched_at = excluded.fetched_at,
                   has_data   = 0""",
            (ca, now),
        )
        return

    price = pair.get("priceUsd")
    price_f = float(price) if price else None
    mc = pair.get("marketCap") or pair.get("fdv")
    mc_f = float(mc) if mc else None

    # UPSERT so ATH rolls forward (GREATEST(old, new)) instead of being overwritten.
    conn.execute(
        """INSERT INTO token_prices
           (contract_address, price_usd, market_cap, volume_h24,
            price_change_h24, liquidity_usd, pair_address, dex_id,
            fetched_at, has_data,
            price_ath, price_ath_at, market_cap_ath, market_cap_ath_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)
           ON CONFLICT(contract_address) DO UPDATE SET
             price_usd        = excluded.price_usd,
             market_cap       = excluded.market_cap,
             volume_h24       = excluded.volume_h24,
             price_change_h24 = excluded.price_change_h24,
             liquidity_usd    = excluded.liquidity_usd,
             pair_address     = excluded.pair_address,
             dex_id           = excluded.dex_id,
             fetched_at       = excluded.fetched_at,
             has_data         = 1,
             price_ath = CASE
                 WHEN excluded.price_usd IS NOT NULL
                  AND (token_prices.price_ath IS NULL
                       OR excluded.price_usd > token_prices.price_ath)
                 THEN excluded.price_usd
                 ELSE token_prices.price_ath END,
             price_ath_at = CASE
                 WHEN excluded.price_usd IS NOT NULL
                  AND (token_prices.price_ath IS NULL
                       OR excluded.price_usd > token_prices.price_ath)
                 THEN excluded.fetched_at
                 ELSE token_prices.price_ath_at END,
             market_cap_ath = CASE
                 WHEN excluded.market_cap IS NOT NULL
                  AND (token_prices.market_cap_ath IS NULL
                       OR excluded.market_cap > token_prices.market_cap_ath)
                 THEN excluded.market_cap
                 ELSE token_prices.market_cap_ath END,
             market_cap_ath_at = CASE
                 WHEN excluded.market_cap IS NOT NULL
                  AND (token_prices.market_cap_ath IS NULL
                       OR excluded.market_cap > token_prices.market_cap_ath)
                 THEN excluded.fetched_at
                 ELSE token_prices.market_cap_ath_at END""",
        (
            ca,
            price_f,
            mc_f,
            (pair.get("volume") or {}).get("h24"),
            (pair.get("priceChange") or {}).get("h24"),
            (pair.get("liquidity") or {}).get("usd"),
            pair.get("pairAddress"),
            pair.get("dexId"),
            now,
            price_f, now if price_f else None,
            mc_f, now if mc_f else None,
        ),
    )


def get_prices_cached(conn: sqlite3.Connection, cas: list[str]) -> dict[str, dict]:
    """Cache-only read. Never performs HTTP. Returns whatever is in token_prices.

    Used by the dashboard request path now that padre-workers populates prices
    in the background. Missing CAs are simply omitted from the returned dict —
    the caller treats absence as "no data yet" rather than blocking on HTTP.
    """
    if not cas:
        return {}

    init_cache(conn)
    cas = list(dict.fromkeys(cas))
    placeholders = ",".join("?" * len(cas))
    rows = conn.execute(
        f"SELECT * FROM token_prices WHERE contract_address IN ({placeholders})",
        tuple(cas),
    ).fetchall()
    return {r["contract_address"]: dict(r) for r in rows}


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
