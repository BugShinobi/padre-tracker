"""GMGN token enrichment — security flags, holder metrics, socials, volume.

Two endpoints (confirmed working 2026-04-21):
- /defi/quotation/v1/tokens/sol?address={CA}  → price, flags, burn, swaps (returns tokens[] array)
- /api/v1/token_info/sol/{CA}                 → holder_count, supply, creation time

Design mirrors enrich.py: SQLite cache, TTL, fail-open.
"""

import logging
import sqlite3
import time

# Using tls_client instead of standard requests to spoof browser fingerprints
# GMGN uses strict Cloudflare protection that blocks standard requests/curl
import tls_client

log = logging.getLogger(__name__)

GMGN_QUOTE_URL = "https://gmgn.ai/defi/quotation/v1/tokens/sol"   # ?address={CA}
GMGN_INFO_URL  = "https://gmgn.ai/api/v1/token_info/sol/{ca}"
HTTP_TIMEOUT = 8
FRESH_TTL = 180
DEAD_TTL  = 3600
RATE_SLEEP = 0.35

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://gmgn.ai/",
}


def init_cache(conn: sqlite3.Connection) -> None:
    # Drop old schema if columns don't match (one-time migration)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(token_gmgn)").fetchall()}
    if cols and "renounced_mint" not in cols:
        conn.execute("DROP TABLE IF EXISTS token_gmgn")
        conn.commit()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS token_gmgn (
            contract_address    TEXT PRIMARY KEY,
            holder_count        INTEGER,
            top10_pct           REAL,
            renounced           INTEGER,
            renounced_mint      INTEGER,
            renounced_freeze    INTEGER,
            burn_ratio          REAL,
            burn_status         TEXT,
            price               REAL,
            price_24h           REAL,
            swaps_5m            INTEGER,
            swaps_1h            INTEGER,
            swaps_24h           INTEGER,
            volume_24h          REAL,
            liquidity           REAL,
            total_supply        REAL,
            open_timestamp      INTEGER,
            creation_timestamp  INTEGER,
            fetched_at          INTEGER NOT NULL,
            has_data            INTEGER NOT NULL DEFAULT 1
        )
    """)
    conn.commit()


def _get_tls_session() -> tls_client.Session:
    """Create a TLS client session that mimics a real Chrome browser.
    
    This is necessary because GMGN strictly blocks Python requests and standard
    cURL commands via Cloudflare's bot protection (returning 403 Forbidden).
    """
    session = tls_client.Session(
        client_identifier="chrome_120",
        random_tls_extension_order=True
    )
    session.headers.update(_HEADERS)
    return session


def _fetch_one(ca: str) -> dict | None:
    """Fetch from both GMGN endpoints and merge. Returns None on failure."""
    result: dict = {"contract_address": ca}
    got_data = False
    
    session = _get_tls_session()

    # 1. Quotation endpoint: price, flags, burn, swaps
    try:
        # Use session.get instead of requests.get to bypass Cloudflare
        r = session.get(
            GMGN_QUOTE_URL, params={"address": ca},
            timeout_seconds=HTTP_TIMEOUT,
        )
        if r.status_code == 200:
            body = r.json()
            if body.get("code") == 0:
                tokens = (body.get("data") or {}).get("tokens") or []
                # Find exact match by address (endpoint may return related tokens)
                token = next((t for t in tokens if t.get("address") == ca), None)
                if token:
                    br = token.get("burn_ratio")
                    result.update({
                        "top10_pct":        token.get("top_10_holder_rate"),
                        "renounced":        1 if token.get("renounced") else 0,
                        "renounced_mint":   token.get("renounced_mint") or 0,
                        "renounced_freeze": token.get("renounced_freeze_account") or 0,
                        "burn_ratio":       float(br) if br is not None else None,
                        "burn_status":      token.get("burn_status"),
                        "price":            token.get("price"),
                        "price_24h":        token.get("price_24h"),
                        "swaps_5m":         token.get("swaps_5m"),
                        "swaps_1h":         token.get("swaps_1h"),
                        "swaps_24h":        token.get("swaps_24h"),
                        "volume_24h":       token.get("volume_24h"),
                        "liquidity":        token.get("liquidity"),
                        "total_supply":     token.get("total_supply"),
                    })
                    got_data = True
        elif r.status_code in (403, 429, 503):
            log.warning("GMGN quote blocked %d for %s", r.status_code, ca[:8])
    except Exception as e:
        log.warning("GMGN quote error for %s: %s", ca[:8], e)

    # 2. Token info endpoint: holder_count, timestamps
    try:
        # Use session.get instead of requests.get
        r2 = session.get(
            GMGN_INFO_URL.format(ca=ca),
            timeout_seconds=HTTP_TIMEOUT,
        )
        if r2.status_code == 200:
            body2 = r2.json()
            if body2.get("code") == 0:
                d = body2.get("data") or {}
                result.update({
                    "holder_count":      d.get("holder_count"),
                    "total_supply":      result.get("total_supply") or d.get("total_supply"),
                    "open_timestamp":    d.get("open_timestamp"),
                    "creation_timestamp": d.get("creation_timestamp"),
                })
                got_data = True
    except Exception as e:
        log.warning("GMGN info error for %s: %s", ca[:8], e)

    return result if got_data else None


def _write_cache(conn: sqlite3.Connection, row: dict | None, ca: str, now: int) -> None:
    if row is None:
        conn.execute(
            "INSERT OR REPLACE INTO token_gmgn (contract_address, fetched_at, has_data) VALUES (?,?,0)",
            (ca, now),
        )
        return
    conn.execute(
        """INSERT OR REPLACE INTO token_gmgn
           (contract_address, holder_count, top10_pct, renounced, renounced_mint, renounced_freeze,
            burn_ratio, burn_status, price, price_24h, swaps_5m, swaps_1h, swaps_24h,
            volume_24h, liquidity, total_supply, open_timestamp, creation_timestamp,
            fetched_at, has_data)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)""",
        (
            ca,
            row.get("holder_count"), row.get("top10_pct"),
            row.get("renounced", 0), row.get("renounced_mint", 0), row.get("renounced_freeze", 0),
            row.get("burn_ratio"), row.get("burn_status"),
            row.get("price"), row.get("price_24h"),
            row.get("swaps_5m"), row.get("swaps_1h"), row.get("swaps_24h"),
            row.get("volume_24h"), row.get("liquidity"),
            row.get("total_supply"), row.get("open_timestamp"), row.get("creation_timestamp"),
            now,
        ),
    )


def get_gmgn_cached(conn: sqlite3.Connection, cas: list[str]) -> tuple[dict[str, dict], list[str]]:
    """Read-only cache lookup. Returns (cached_rows, stale_cas).

    Never performs HTTP — safe to call from request path. The caller should
    enqueue stale_cas to the background worker (gmgn_worker.enqueue_refresh)
    so the cache gets refreshed out-of-band.
    """
    if not cas:
        return {}, []

    init_cache(conn)
    cas = list(dict.fromkeys(cas))
    now = int(time.time())
    fresh_cutoff = now - FRESH_TTL
    dead_cutoff = now - DEAD_TTL

    placeholders = ",".join("?" * len(cas))
    rows = conn.execute(
        f"SELECT * FROM token_gmgn WHERE contract_address IN ({placeholders})",
        tuple(cas),
    ).fetchall()
    cached = {r["contract_address"]: dict(r) for r in rows}

    stale = [
        ca for ca in cas
        if (ca not in cached)
        or (cached[ca]["has_data"] == 1 and cached[ca]["fetched_at"] < fresh_cutoff)
        or (cached[ca]["has_data"] == 0 and cached[ca]["fetched_at"] < dead_cutoff)
    ]
    return cached, stale


def fetch_and_cache_one(db_path: str, ca: str) -> None:
    """Fetch one CA from GMGN and write to the shared SQLite cache. Used by worker."""
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        init_cache(conn)
        now = int(time.time())
        result = _fetch_one(ca)
        _write_cache(conn, result, ca, now)
        conn.commit()
    finally:
        conn.close()


def get_gmgn(conn: sqlite3.Connection, cas: list[str]) -> dict[str, dict]:
    """Return {ca: gmgn_row} for each CA. Fetches stale/missing with rate limiting."""
    if not cas:
        return {}

    init_cache(conn)
    cas = list(dict.fromkeys(cas))
    now = int(time.time())
    fresh_cutoff = now - FRESH_TTL
    dead_cutoff  = now - DEAD_TTL

    placeholders = ",".join("?" * len(cas))
    rows = conn.execute(
        f"SELECT * FROM token_gmgn WHERE contract_address IN ({placeholders})",
        tuple(cas),
    ).fetchall()
    cached = {r["contract_address"]: dict(r) for r in rows}

    stale = [
        ca for ca in cas
        if (ca not in cached)
        or (cached[ca]["has_data"] == 1 and cached[ca]["fetched_at"] < fresh_cutoff)
        or (cached[ca]["has_data"] == 0 and cached[ca]["fetched_at"] < dead_cutoff)
    ]

    if stale:
        log.info("GMGN: fetching %d CA(s)", len(stale))
        for i, ca in enumerate(stale):
            if i > 0:
                time.sleep(RATE_SLEEP)
            result = _fetch_one(ca)
            _write_cache(conn, result, ca, now)

        conn.commit()
        rows = conn.execute(
            f"SELECT * FROM token_gmgn WHERE contract_address IN ({placeholders})",
            tuple(cas),
        ).fetchall()
        cached = {r["contract_address"]: dict(r) for r in rows}

    return cached
