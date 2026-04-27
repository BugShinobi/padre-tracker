"""Token metadata enrichment via Helius DAS getAsset + off-chain JSON fallback.

Provides: description, name, logo. Socials are intentionally NOT fetched — per user
decision, not useful for Padre call analysis.

Helius `getAsset` returns Metaplex metadata in one call. When the on-chain
description is empty but a `json_uri` is present, we do a single HTTP fetch to
the off-chain JSON (often IPFS or a launchpad CDN) with browser-like headers
(many hosts 403 on default Python UA).

Launcher-spam descriptions ("Deployed using foo.io", "Launched on discord...")
are treated as empty — they add no signal and would clutter the dashboard.

Description is stable metadata — cache TTL is long (7 days), dead tokens even
longer (30 days), because this rarely changes after token creation.
"""

import json
import logging
import re
import sqlite3
import time
import urllib.error
import urllib.request

log = logging.getLogger(__name__)

HELIUS_RPC_TMPL = "https://mainnet.helius-rpc.com/?api-key={key}"
HTTP_TIMEOUT = 6
FRESH_TTL = 7 * 24 * 3600       # metadata rarely changes
DEAD_TTL  = 30 * 24 * 3600      # no point retrying dead tokens often
LOGO_RETRY_TTL = 3600           # retry missing logo every 1h (off-chain JSON / IPFS often flake)
LOGO_MAX_RETRIES = 3            # after ~3h give up and fall back to FRESH_TTL
RATE_SLEEP = 0.15               # Helius free tier: 10 req/s

_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Match launcher-spam openers: "Launched on foo.io", "Deployed using pump.fun", etc.
# Catches both URL and bare-domain forms since launcher attribution is short by design.
_SPAM_DESC_RE = re.compile(
    r"^\s*(deployed|launched|created|made|built|minted)\s+(on|using|with|via)\s+\S+\s*$",
    re.IGNORECASE,
)
_URL_ONLY_RE = re.compile(r"^\s*https?://\S+\s*$")

_IPFS_GATEWAYS = (
    "https://ipfs.io/ipfs/",
    "https://cloudflare-ipfs.com/ipfs/",
    "https://gateway.pinata.cloud/ipfs/",
)


def init_cache(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS token_metadata (
            contract_address TEXT PRIMARY KEY,
            name             TEXT,
            symbol           TEXT,
            description      TEXT,
            image_url        TEXT,
            json_uri         TEXT,
            fetched_at       INTEGER NOT NULL,
            has_data         INTEGER NOT NULL DEFAULT 1
        )
    """)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(token_metadata)").fetchall()}
    if "image_retries" not in cols:
        conn.execute("ALTER TABLE token_metadata ADD COLUMN image_retries INTEGER NOT NULL DEFAULT 0")
    conn.commit()


def _clean_description(raw) -> str | None:
    if not raw or not isinstance(raw, str):
        return None
    s = raw.strip()
    if len(s) < 15:
        return None
    if _SPAM_DESC_RE.match(s) or _URL_ONLY_RE.match(s):
        return None
    return s


def _http_get_json(url: str, timeout: int = HTTP_TIMEOUT) -> dict | None:
    """Plain HTTP GET returning parsed JSON, with browser UA. None on any failure."""
    urls = []
    if url.startswith("ipfs://"):
        cid = url[len("ipfs://"):]
        urls = [gw + cid for gw in _IPFS_GATEWAYS]
    else:
        urls = [url]

    req_headers = {
        "User-Agent": _BROWSER_UA,
        "Accept": "application/json, */*;q=0.8",
    }
    for u in urls:
        try:
            req = urllib.request.Request(u, headers=req_headers)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = r.read()
                return json.loads(data) if data else None
        except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError, TimeoutError) as e:
            log.debug("off-chain fetch failed %s: %s", u[:80], e)
            continue
        except Exception as e:
            log.debug("off-chain unexpected err %s: %s", u[:80], e)
            continue
    return None


def _pick_image(content: dict) -> str | None:
    files = content.get("files") or []
    for f in files:
        mime = (f.get("mime") or "").lower()
        if mime.startswith("image"):
            return f.get("cdn_uri") or f.get("uri")
    links = content.get("links") or {}
    return links.get("image")


def _fetch_one(api_key: str, ca: str) -> dict | None:
    """Fetch Helius DAS, fall back to off-chain JSON if description missing."""
    url = HELIUS_RPC_TMPL.format(key=api_key)
    body = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getAsset",
        "params": {"id": ca},
    }).encode()
    try:
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
            envelope = json.loads(r.read())
    except Exception as e:
        log.warning("Helius getAsset err for %s: %s", ca[:8], e)
        return None

    asset = envelope.get("result") or {}
    if not asset:
        return None

    content = asset.get("content") or {}
    meta = content.get("metadata") or {}
    json_uri = (content.get("json_uri") or "").strip() or None

    description = _clean_description(meta.get("description"))
    name = meta.get("name") or None
    symbol = meta.get("symbol") or None
    image = _pick_image(content)

    if not description and json_uri:
        off = _http_get_json(json_uri)
        if off:
            description = _clean_description(off.get("description"))
            image = image or off.get("image")
            name = name or off.get("name")

    return {
        "name": name,
        "symbol": symbol,
        "description": description,
        "image_url": image,
        "json_uri": json_uri,
    }


def _write_cache(conn: sqlite3.Connection, row: dict | None, ca: str, now: int) -> None:
    prev = conn.execute(
        "SELECT image_retries FROM token_metadata WHERE contract_address = ?", (ca,)
    ).fetchone()
    prev_retries = prev[0] if prev else 0

    if row is None:
        conn.execute(
            "INSERT OR REPLACE INTO token_metadata (contract_address, fetched_at, has_data, image_retries) VALUES (?,?,0,?)",
            (ca, now, prev_retries),
        )
        return

    image = row.get("image_url")
    retries = 0 if image else prev_retries + 1

    conn.execute(
        """INSERT OR REPLACE INTO token_metadata
           (contract_address, name, symbol, description, image_url, json_uri, fetched_at, has_data, image_retries)
           VALUES (?,?,?,?,?,?,?,1,?)""",
        (
            ca,
            row.get("name"),
            row.get("symbol"),
            row.get("description"),
            image,
            row.get("json_uri"),
            now,
            retries,
        ),
    )


def get_metadata_cached(
    conn: sqlite3.Connection, cas: list[str]
) -> tuple[dict[str, dict], list[str]]:
    """Read-only cache lookup. Returns (cached_rows, stale_cas)."""
    if not cas:
        return {}, []

    init_cache(conn)
    cas = list(dict.fromkeys(cas))
    now = int(time.time())
    fresh_cutoff = now - FRESH_TTL
    dead_cutoff = now - DEAD_TTL

    placeholders = ",".join("?" * len(cas))
    rows = conn.execute(
        f"SELECT * FROM token_metadata WHERE contract_address IN ({placeholders})",
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


def fetch_and_cache_one(db_path: str, api_key: str, ca: str) -> None:
    """Fetch one CA from Helius and write to cache. Used by worker."""
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        init_cache(conn)
        now = int(time.time())
        result = _fetch_one(api_key, ca)
        _write_cache(conn, result, ca, now)
        conn.commit()
    finally:
        conn.close()
