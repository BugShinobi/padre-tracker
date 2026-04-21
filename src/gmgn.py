"""GMGN token enrichment — security flags, holder metrics, socials, volume.

Design mirrors enrich.py:
- SQLite cache table `token_gmgn` in same DB.
- Per-CA fetch (no batch endpoint). Rate-limit: 300ms sleep between calls.
- TTL: 180s fresh / 3600s dead.
- Fail-open: on any error return cached stale row or empty dict.
"""

import logging
import sqlite3
import time

import requests

log = logging.getLogger(__name__)

GMGN_URL = "https://gmgn.ai/defi/quotation/v1/tokens/sol/{ca}"
HTTP_TIMEOUT = 8
FRESH_TTL = 180
DEAD_TTL = 3600
RATE_SLEEP = 0.35

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://gmgn.ai/",
}


def init_cache(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS token_gmgn (
            contract_address TEXT PRIMARY KEY,
            holder_count      INTEGER,
            top10_pct         REAL,
            dev_pct           REAL,
            insider_pct       REAL,
            bundle_pct        REAL,
            sniper_count      INTEGER,
            smart_buyers      INTEGER,
            kol_count         INTEGER,
            mint_revoked      INTEGER,
            freeze_revoked    INTEGER,
            lp_burned_pct     REAL,
            renounced         INTEGER,
            twitter           TEXT,
            telegram          TEXT,
            website           TEXT,
            created_at        INTEGER,
            creator           TEXT,
            total_supply      REAL,
            buys_5m           INTEGER,
            sells_5m          INTEGER,
            volume_5m         REAL,
            swaps_count       INTEGER,
            fetched_at        INTEGER NOT NULL,
            has_data          INTEGER NOT NULL DEFAULT 1
        )
    """)
    conn.commit()


def _parse_response(ca: str, data: dict) -> dict:
    """Extract fields from GMGN API response into our flat schema."""
    token = data.get("token") or data.get("data") or data or {}

    # Security / rugpull fields
    security = token.get("security") or {}
    holder_info = token.get("holder") or token.get("holders") or {}

    # Socials
    socials = token.get("social_info") or token.get("socials") or {}
    twitter = socials.get("twitter_username") or socials.get("twitter") or token.get("twitter")
    telegram = socials.get("telegram") or token.get("telegram")
    website = socials.get("website") or token.get("website")

    # Volume / activity
    volume = token.get("volume") or {}
    buys_5m = (token.get("buy5m") or token.get("buys_5m")
               or (token.get("buys") or {}).get("m5"))
    sells_5m = (token.get("sell5m") or token.get("sells_5m")
                or (token.get("sells") or {}).get("m5"))

    return {
        "contract_address": ca,
        "holder_count": token.get("holder_count") or token.get("holders"),
        "top10_pct": token.get("top_10_holder_rate") or security.get("top_10_holder_rate"),
        "dev_pct": token.get("dev_token_burn_amount") or security.get("dev_token_burn_amount"),
        "insider_pct": token.get("insider_pct") or security.get("insider_pct"),
        "bundle_pct": token.get("bundle_pct") or security.get("bundle_pct"),
        "sniper_count": token.get("sniper_count") or security.get("sniper_count"),
        "smart_buyers": token.get("smart_degen_count") or token.get("smart_buyers"),
        "kol_count": token.get("kol_count"),
        "mint_revoked": int(bool(security.get("is_mintable") == 0 or security.get("mint_auth_revoked"))),
        "freeze_revoked": int(bool(security.get("freeze_auth_revoked") or token.get("freeze_revoked"))),
        "lp_burned_pct": token.get("burn_ratio") or security.get("burn_ratio"),
        "renounced": int(bool(security.get("is_renounced") or token.get("renounced"))),
        "twitter": twitter,
        "telegram": telegram,
        "website": website,
        "created_at": token.get("open_timestamp") or token.get("created_at"),
        "creator": token.get("creator") or token.get("deployer"),
        "total_supply": token.get("total_supply"),
        "buys_5m": buys_5m,
        "sells_5m": sells_5m,
        "volume_5m": (token.get("volume5m") or (volume.get("m5"))),
        "swaps_count": token.get("swaps") or token.get("swaps_count"),
    }


def _fetch_one(ca: str) -> dict | None:
    url = GMGN_URL.format(ca=ca)
    try:
        r = requests.get(url, headers=_HEADERS, timeout=HTTP_TIMEOUT)
        if r.status_code == 200:
            body = r.json()
            if body.get("code") == 0 or body.get("data") or body.get("token"):
                return _parse_response(ca, body.get("data") or body)
        elif r.status_code in (403, 429, 503):
            log.warning("GMGN blocked/rate-limited %d for %s", r.status_code, ca[:8])
        else:
            log.debug("GMGN %d for %s", r.status_code, ca[:8])
    except Exception as e:
        log.warning("GMGN fetch error for %s: %s", ca[:8], e)
    return None


def _write_cache(conn: sqlite3.Connection, row: dict | None, ca: str, now: int) -> None:
    if row is None:
        conn.execute(
            "INSERT OR REPLACE INTO token_gmgn (contract_address, fetched_at, has_data) VALUES (?,?,0)",
            (ca, now),
        )
        return
    conn.execute(
        """INSERT OR REPLACE INTO token_gmgn
           (contract_address, holder_count, top10_pct, dev_pct, insider_pct, bundle_pct,
            sniper_count, smart_buyers, kol_count, mint_revoked, freeze_revoked,
            lp_burned_pct, renounced, twitter, telegram, website,
            created_at, creator, total_supply,
            buys_5m, sells_5m, volume_5m, swaps_count, fetched_at, has_data)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)""",
        (
            row["contract_address"], row["holder_count"], row["top10_pct"], row["dev_pct"],
            row["insider_pct"], row["bundle_pct"], row["sniper_count"], row["smart_buyers"],
            row["kol_count"], row["mint_revoked"], row["freeze_revoked"], row["lp_burned_pct"],
            row["renounced"], row["twitter"], row["telegram"], row["website"],
            row["created_at"], row["creator"], row["total_supply"],
            row["buys_5m"], row["sells_5m"], row["volume_5m"], row["swaps_count"], now,
        ),
    )


def get_gmgn(conn: sqlite3.Connection, cas: list[str]) -> dict[str, dict]:
    """Return {ca: gmgn_row} for each CA. Fetches stale/missing with rate limiting.

    Dashboard should call this only for a small slice (top-N). Scraper pre-warms cache
    for new tokens so /day load is mostly cache reads.
    """
    if not cas:
        return {}

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

    if stale:
        log.info("GMGN: fetching %d CA(s)", len(stale))
        for i, ca in enumerate(stale):
            if i > 0:
                time.sleep(RATE_SLEEP)
            result = _fetch_one(ca)
            _write_cache(conn, result, ca, now)
            cached[ca] = dict(
                conn.execute(
                    "SELECT * FROM token_gmgn WHERE contract_address = ?", (ca,)
                ).fetchone() or {}
            )
        conn.commit()

    return cached
