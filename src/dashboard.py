"""Flask API + SPA host for padre-tracker.

JSON API under /api/* powers the SvelteKit frontend (served from frontend/build/).
Everything else returns the SPA's index.html so client-side routing works.
"""

import json
import logging
import os
import sqlite3
import time
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

from flask import Flask, Response, request, jsonify, send_from_directory, stream_with_context

import aggregations as agg
from cache import ttl_cache
from db import init_db
from enrich import get_prices_cached
from gmgn import get_gmgn_cached
from metadata import get_metadata_cached
from telegram_db import init_telegram_table

DB_PATH = os.getenv("DB_PATH", "./data/calls.db")
HELIUS_API_KEY = os.getenv("HELIUS_API_KEY")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

logging.basicConfig(level=getattr(logging, LOG_LEVEL), format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

# static_folder serves frontend/build at the URL root; static_url_path='' means
# /favicon.svg and /_app/* resolve to files in the build dir without a prefix.
app = Flask(__name__, static_folder="../frontend/build", static_url_path="")
log = logging.getLogger("padre-dashboard")

if Path(DB_PATH).exists():
    _boot = init_db(DB_PATH)
    # Drop the legacy curation table — delisting is now a hard DELETE, no soft state.
    _boot.execute("DROP TABLE IF EXISTS token_status")
    _boot.execute(
        """CREATE TABLE IF NOT EXISTS token_notes (
            contract_address TEXT PRIMARY KEY,
            note             TEXT NOT NULL DEFAULT '',
            updated_at       TEXT NOT NULL
        )"""
    )
    _boot.execute(
        """CREATE TABLE IF NOT EXISTS token_watchlist (
            contract_address TEXT PRIMARY KEY,
            added_at         TEXT NOT NULL
        )"""
    )
    init_telegram_table(_boot)
    _boot.commit()
    _boot.close()


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def _safe_float(v) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _delta(curr: int, prev: int) -> dict:
    if prev == 0 and curr == 0:
        return {"str": "±0", "class": "flat"}
    if prev == 0:
        return {"str": f"+{curr}", "class": "pos"}
    diff = curr - prev
    pct = (diff / prev) * 100
    sign = "+" if diff >= 0 else ""
    cls = "pos" if diff > 0 else ("neg" if diff < 0 else "flat")
    return {"str": f"{sign}{diff} ({sign}{pct:.0f}%)", "class": cls}


@ttl_cache(30)
def _cached_overview(today: date) -> dict:
    conn = _conn()
    try:
        return agg.overview(conn, today)
    finally:
        conn.close()


@app.route("/api/latest")
def api_latest():
    """Return calls inserted/updated since `since` unix timestamp (default: last 30s).

    Used by the live feed panel to poll for new tokens without a full page reload.
    """
    try:
        since_ts = float(request.args.get("since", 0))
    except (ValueError, TypeError):
        since_ts = 0

    if not Path(DB_PATH).exists():
        return jsonify([])

    # Convert unix timestamp to ISO string for SQLite comparison
    since_iso = datetime.fromtimestamp(since_ts).isoformat() if since_ts else "1970-01-01"

    conn = _conn()
    try:
        rows = conn.execute(
            """SELECT contract_address, ticker, launchpad, call_count,
                      first_seen_at, last_seen_at, groups_mentioned, call_date
               FROM calls
               WHERE first_seen_at > ?
               ORDER BY first_seen_at DESC
               LIMIT 50""",
            (since_iso,),
        ).fetchall()
    finally:
        conn.close()

    result = []
    for r in rows:
        d = dict(r)
        d["ts"] = d["first_seen_at"]
        result.append(d)

    return jsonify(result)


@app.route("/api/stats")
def api_stats():
    """Quick stats for the live header counter."""
    if not Path(DB_PATH).exists():
        return jsonify({"tokens_today": 0, "calls_today": 0})
    conn = _conn()
    try:
        today = date.today().isoformat()
        row = conn.execute(
            "SELECT COUNT(*) AS t, COALESCE(SUM(call_count),0) AS c FROM calls WHERE call_date=?",
            (today,),
        ).fetchone()
    finally:
        conn.close()
    return jsonify({"tokens_today": row["t"], "calls_today": row["c"]})


@app.route("/api/stream/calls")
def api_stream_calls():
    """SSE feed of newly-inserted calls.

    On connect, sends a primer batch (last 10 calls) so the page is never blank,
    then sets the watermark just past those primers and polls the DB every 2s
    for newer rows, streaming each as `event: new`. A `event: ping` every 15s
    keeps proxies and EventSource alive.
    """
    if not Path(DB_PATH).exists():
        return Response("db not ready\n", status=503, mimetype="text/plain")

    @stream_with_context
    def gen():
        # Primer — last 10 calls so the user lands on a populated feed instead
        # of "0 in feed" until the next scrape lands.
        conn = _conn()
        try:
            primer_rows = conn.execute(
                """SELECT contract_address, ticker, chain, launchpad, call_count,
                          first_seen_at, last_seen_at, groups_mentioned
                   FROM calls
                   ORDER BY first_seen_at DESC
                   LIMIT 10"""
            ).fetchall()
            primer_rows = [dict(r) for r in primer_rows]
            if primer_rows:
                _enrich_rows(conn, primer_rows)
                since = primer_rows[0]["first_seen_at"]  # newest first row
            else:
                since = datetime.now().isoformat()
        finally:
            conn.close()

        last_ping = time.monotonic()
        yield f"event: ready\ndata: {json.dumps({'since': since})}\n\n"
        # Send oldest-first so the client (which prepends each event) ends with newest on top.
        for r in reversed(primer_rows):
            yield f"event: new\ndata: {json.dumps(r, default=str)}\n\n"

        while True:
            conn = _conn()
            try:
                rows = conn.execute(
                    """SELECT contract_address, ticker, chain, launchpad, call_count,
                              first_seen_at, last_seen_at, groups_mentioned
                       FROM calls
                       WHERE first_seen_at > ?
                       ORDER BY first_seen_at ASC
                       LIMIT 20""",
                    (since,),
                ).fetchall()
                rows = [dict(r) for r in rows]
                if rows:
                    _enrich_rows(conn, rows)
                    for r in rows:
                        yield f"event: new\ndata: {json.dumps(r, default=str)}\n\n"
                    since = rows[-1]["first_seen_at"]
            finally:
                conn.close()

            now_mono = time.monotonic()
            if now_mono - last_ping >= 15:
                yield "event: ping\ndata: {}\n\n"
                last_ping = now_mono

            time.sleep(2)

    return Response(
        gen(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ============================================================= JSON API
#
# Shape follows the TanStack Table/Query contract: {data, rowCount, pageCount}
# so a SvelteKit/React frontend can drive the UI without re-rendering Jinja.
# Filtering, sorting and pagination run server-side over columns we actually
# index in SQLite. Price/MC sorting happens after the SQL page is fetched and
# enriched — not billions of rows, so acceptable. Enqueueing stale GMGN rows
# to the background worker means the payload is served instantly with whatever
# is in cache; subsequent polls pick up fresh data.

_DAY_SORT_FIELDS = {
    "call_count": "calls.call_count",
    "first_seen_at": "calls.first_seen_at",
    "last_seen_at": "calls.last_seen_at",
    "ticker": "calls.ticker",
    "launchpad": "calls.launchpad",
    "market_cap": "prices.market_cap",
    "price_change_h24": "prices.price_change_h24",
    "holder_count": "gmgn.holder_count",
}

_RANGE_SORT_FIELDS = {
    "call_count": "total_calls",
    "days_active": "days_active",
    "first_seen_at": "first_seen_at",
    "last_seen_at": "last_seen_at",
    "ticker": "ticker",
    "launchpad": "launchpad",
    "market_cap": "market_cap",
    "price_change_h24": "price_change_h24",
    "holder_count": "holder_count",
}


def _parse_sort(raw: str, allowed: dict, default_field: str, default_dir: str) -> tuple[str, str]:
    if raw and ":" in raw:
        field, direction = raw.split(":", 1)
        if field in allowed and direction in ("asc", "desc"):
            return allowed[field], direction.upper()
    return allowed[default_field], default_dir.upper()


def _csv_param(raw: str) -> list[str]:
    if not raw:
        return []
    return [p.strip() for p in raw.split(",") if p.strip()]


def _enrich_rows(conn: sqlite3.Connection, rows: list[dict]) -> None:
    if not rows:
        return
    cas = [r["contract_address"] for r in rows]
    prices = get_prices_cached(conn, cas)
    gmgn_data, _ = get_gmgn_cached(conn, cas)
    meta_data, _ = get_metadata_cached(conn, cas)
    for r in rows:
        p = prices.get(r["contract_address"]) or {}
        r["price_usd"] = _safe_float(p.get("price_usd"))
        r["price_change_h24"] = _safe_float(p.get("price_change_h24"))
        r["market_cap"] = _safe_float(p.get("market_cap"))
        r["liquidity_usd"] = _safe_float(p.get("liquidity_usd"))
        r["volume_h24"] = _safe_float(p.get("volume_h24"))
        r["price_ath"] = _safe_float(p.get("price_ath"))
        r["price_ath_at"] = p.get("price_ath_at")
        r["market_cap_ath"] = _safe_float(p.get("market_cap_ath"))
        r["market_cap_ath_at"] = p.get("market_cap_ath_at")
        g = gmgn_data.get(r["contract_address"]) or {}
        r["holder_count"] = g.get("holder_count")
        r["top10_pct"] = _safe_float(g.get("top10_pct"))
        r["renounced"] = g.get("renounced")
        r["renounced_mint"] = g.get("renounced_mint")
        r["renounced_freeze"] = g.get("renounced_freeze")
        r["burn_ratio"] = _safe_float(g.get("burn_ratio"))
        r["burn_status"] = g.get("burn_status")
        r["swaps_5m"] = g.get("swaps_5m")
        r["swaps_1h"] = g.get("swaps_1h")
        r["swaps_24h"] = g.get("swaps_24h")
        r["creation_timestamp"] = g.get("creation_timestamp")
        m = meta_data.get(r["contract_address"]) or {}
        r["name"] = m.get("name")
        r["description"] = m.get("description")
        r["image_url"] = m.get("image_url")


@app.route("/api/overview")
def api_overview():
    if not Path(DB_PATH).exists():
        return jsonify({"today": {"tokens": 0, "total_calls": 0}, "ready": False})

    data = _cached_overview(date.today())
    t_delta = _delta(data["today"]["tokens"], data["yesterday"]["tokens"])
    c_delta = _delta(data["today"]["total_calls"], data["yesterday"]["total_calls"])

    week_ago = (date.today() - timedelta(days=6)).isoformat()
    conn = _conn()
    try:
        top_week = [dict(t) for t in data["top_tokens_week"]]
        top_today = [dict(t) for t in data["top_tokens_today"]]

        latest_rows = conn.execute(
            """SELECT contract_address,
                      MAX(ticker)        AS ticker,
                      MAX(launchpad)     AS launchpad,
                      MAX(chain)         AS chain,
                      SUM(call_count)    AS call_count,
                      MIN(first_seen_at) AS first_seen_at,
                      MAX(last_seen_at)  AS last_seen_at,
                      GROUP_CONCAT(DISTINCT groups_mentioned) AS groups_raw
               FROM calls
               WHERE call_date >= ?
               GROUP BY contract_address
               ORDER BY MAX(last_seen_at) DESC
               LIMIT 20""",
            (week_ago,),
        ).fetchall()
        latest = []
        for r in latest_rows:
            d = dict(r)
            groups_set: set[str] = set()
            for chunk in (d.pop("groups_raw") or "").split(","):
                g = chunk.strip()
                if g:
                    groups_set.add(g)
            d["groups_mentioned"] = ", ".join(sorted(groups_set)) if groups_set else None
            latest.append(d)

        _enrich_rows(conn, top_week)
        _enrich_rows(conn, top_today)
        _enrich_rows(conn, latest)
    finally:
        conn.close()

    return jsonify({
        "ready": True,
        "date": date.today().isoformat(),
        "today": data["today"],
        "yesterday": data["yesterday"],
        "delta": {
            "tokens": {"str": t_delta["str"], "class": t_delta["class"]},
            "calls":  {"str": c_delta["str"], "class": c_delta["class"]},
        },
        "week": data["week"],
        "week_totals": data["week_totals"],
        "top_tokens": top_week,
        "top_tokens_today": top_today,
        "latest_calls": latest,
        "groups": data["groups_week"],
    })


@app.route("/api/groups/top")
def api_groups_top():
    """Top-N groups by call activity in the last `days` window.

    Replaces the hardcoded KNOWN_GROUPS chip list on the frontend so dead
    groups drop out and trending ones surface naturally. Splits the
    comma-joined `groups_mentioned` field in Python — SQLite has no
    native split, and the row volume in a 24h window is small.
    """
    if not Path(DB_PATH).exists():
        return jsonify({"groups": [], "ready": False})

    try:
        limit = max(1, min(50, int(request.args.get("limit", 15))))
    except ValueError:
        limit = 15
    try:
        days = max(1, min(30, int(request.args.get("days", 1))))
    except ValueError:
        days = 1

    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT groups_mentioned FROM calls "
            "WHERE last_seen_at >= ? AND groups_mentioned IS NOT NULL "
            "AND groups_mentioned != ''",
            (cutoff,),
        ).fetchall()
    finally:
        conn.close()

    counts: Counter[str] = Counter()
    for r in rows:
        for g in (r["groups_mentioned"] or "").split(","):
            g = g.strip()
            if g:
                counts[g] += 1

    top = counts.most_common(limit)
    return jsonify({
        "ready": True,
        "groups": [{"name": g, "count": c} for g, c in top],
        "windowDays": days,
    })


@app.route("/api/day")
def api_day():
    """Paginated/filterable/sortable daily calls. TanStack contract.

    Query params:
      d=YYYY-MM-DD           (default: today)
      page=1                 (1-based)
      page_size=50           (max 500)
      search=<str>           (substring on ticker or contract_address)
      launchpad=a,b,c        (match any)
      groups=g1,g2           (match any — uses LIKE on the comma-joined field)
      sort=call_count:desc   (field: call_count|first_seen_at|last_seen_at|ticker|
                              launchpad|market_cap|price_change_h24|holder_count)
      min_holders=N          (filter: keep token if holder_count IS NULL or >= N)
      mc_min=N, mc_max=N     (filter: keep token if market_cap IS NULL or in range)
    """
    if not Path(DB_PATH).exists():
        return jsonify({"data": [], "rowCount": 0, "pageCount": 0, "ready": False})

    try:
        target = date.fromisoformat(request.args["d"]) if request.args.get("d") else date.today()
    except ValueError:
        target = date.today()

    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1
    try:
        page_size = max(1, min(500, int(request.args.get("page_size", 50))))
    except ValueError:
        page_size = 50
    try:
        min_holders = max(0, int(request.args.get("min_holders", 0)))
    except ValueError:
        min_holders = 0
    try:
        mc_min = max(0, int(request.args.get("mc_min", 0)))
    except ValueError:
        mc_min = 0
    try:
        mc_max = max(0, int(request.args.get("mc_max", 0)))
    except ValueError:
        mc_max = 0

    search = (request.args.get("search") or "").strip()
    launchpads = _csv_param(request.args.get("launchpad"))
    groups = _csv_param(request.args.get("groups"))
    sort_field, sort_dir = _parse_sort(
        request.args.get("sort"), _DAY_SORT_FIELDS, "call_count", "desc"
    )

    where = ["calls.call_date = ?"]
    params: list = [target.isoformat()]

    if search:
        where.append("(calls.ticker LIKE ? OR calls.contract_address LIKE ?)")
        like = f"%{search}%"
        params += [like, like]

    if launchpads:
        where.append("calls.launchpad IN (" + ",".join("?" * len(launchpads)) + ")")
        params += launchpads

    if groups:
        where.append("(" + " OR ".join(["calls.groups_mentioned LIKE ?"] * len(groups)) + ")")
        params += [f"%{g}%" for g in groups]

    if min_holders > 0:
        where.append("(gmgn.holder_count IS NULL OR gmgn.holder_count >= ?)")
        params.append(min_holders)

    if mc_min > 0:
        where.append("(prices.market_cap IS NULL OR prices.market_cap >= ?)")
        params.append(mc_min)

    if mc_max > 0:
        where.append("(prices.market_cap IS NULL OR prices.market_cap <= ?)")
        params.append(mc_max)

    where_sql = " AND ".join(where)
    join_sql = (
        "FROM calls "
        "LEFT JOIN token_gmgn   gmgn   ON calls.contract_address = gmgn.contract_address "
        "LEFT JOIN token_prices prices ON calls.contract_address = prices.contract_address"
    )
    conn = _conn()
    try:
        total = conn.execute(
            f"SELECT COUNT(*) {join_sql} WHERE {where_sql}", params
        ).fetchone()[0]

        offset = (page - 1) * page_size
        rows = conn.execute(
            f"""SELECT calls.contract_address, calls.ticker, calls.chain,
                       calls.launchpad, calls.call_count,
                       calls.first_seen_at, calls.last_seen_at,
                       calls.groups_mentioned
                {join_sql}
                WHERE {where_sql}
                ORDER BY ({sort_field}) IS NULL,
                         {sort_field} {sort_dir},
                         calls.first_seen_at DESC
                LIMIT ? OFFSET ?""",
            params + [page_size, offset],
        ).fetchall()
        rows = [dict(r) for r in rows]

        _enrich_rows(conn, rows)
    finally:
        conn.close()

    return jsonify({
        "ready": True,
        "data": rows,
        "rowCount": total,
        "pageCount": (total + page_size - 1) // page_size,
        "page": page,
        "pageSize": page_size,
        "date": target.isoformat(),
        "filters": {
            "search": search,
            "launchpad": launchpads,
            "groups": groups,
            "sort": f"{sort_field}:{sort_dir.lower()}",
        },
    })


@app.route("/api/range")
def api_range():
    """Paginated aggregate across a date range. TanStack contract.

    Query params:
      from=YYYY-MM-DD, to=YYYY-MM-DD (default: last 7 days)
      page, page_size, search, launchpad, groups, sort, min_holders, mc_min, mc_max
    """
    if not Path(DB_PATH).exists():
        return jsonify({"data": [], "rowCount": 0, "pageCount": 0, "ready": False})

    today = date.today()
    try:
        d_from = date.fromisoformat(request.args["from"]) if request.args.get("from") else today - timedelta(days=6)
    except ValueError:
        d_from = today - timedelta(days=6)
    try:
        d_to = date.fromisoformat(request.args["to"]) if request.args.get("to") else today
    except ValueError:
        d_to = today
    if d_from > d_to:
        d_from, d_to = d_to, d_from

    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1
    try:
        page_size = max(1, min(500, int(request.args.get("page_size", 50))))
    except ValueError:
        page_size = 50
    try:
        min_holders = max(0, int(request.args.get("min_holders", 0)))
    except ValueError:
        min_holders = 0
    try:
        mc_min = max(0, int(request.args.get("mc_min", 0)))
    except ValueError:
        mc_min = 0
    try:
        mc_max = max(0, int(request.args.get("mc_max", 0)))
    except ValueError:
        mc_max = 0

    search = (request.args.get("search") or "").strip()
    launchpads = _csv_param(request.args.get("launchpad"))
    groups = _csv_param(request.args.get("groups"))
    sort_field, sort_dir = _parse_sort(
        request.args.get("sort"), _RANGE_SORT_FIELDS, "call_count", "desc"
    )

    params: list = [d_from.isoformat(), d_to.isoformat()]
    row_where = ["calls.call_date >= ?", "calls.call_date <= ?"]

    if search:
        row_where.append("(calls.ticker LIKE ? OR calls.contract_address LIKE ?)")
        like = f"%{search}%"
        params += [like, like]

    if launchpads:
        row_where.append("calls.launchpad IN (" + ",".join("?" * len(launchpads)) + ")")
        params += launchpads

    if groups:
        row_where.append("(" + " OR ".join(["calls.groups_mentioned LIKE ?"] * len(groups)) + ")")
        params += [f"%{g}%" for g in groups]

    if min_holders > 0:
        row_where.append("(gmgn.holder_count IS NULL OR gmgn.holder_count >= ?)")
        params.append(min_holders)

    if mc_min > 0:
        row_where.append("(prices.market_cap IS NULL OR prices.market_cap >= ?)")
        params.append(mc_min)

    if mc_max > 0:
        row_where.append("(prices.market_cap IS NULL OR prices.market_cap <= ?)")
        params.append(mc_max)

    where_sql = " AND ".join(row_where)
    join_sql = (
        "FROM calls "
        "LEFT JOIN token_gmgn   gmgn   ON calls.contract_address = gmgn.contract_address "
        "LEFT JOIN token_prices prices ON calls.contract_address = prices.contract_address"
    )

    conn = _conn()
    try:
        total = conn.execute(
            f"""SELECT COUNT(*) FROM (
                 SELECT calls.contract_address {join_sql}
                 WHERE {where_sql}
                 GROUP BY calls.contract_address
               )""",
            params,
        ).fetchone()[0]

        offset = (page - 1) * page_size
        rows = conn.execute(
            f"""SELECT calls.contract_address                     AS contract_address,
                       MAX(calls.ticker)                          AS ticker,
                       MAX(calls.launchpad)                       AS launchpad,
                       SUM(calls.call_count)                      AS total_calls,
                       COUNT(DISTINCT calls.call_date)            AS days_active,
                       MIN(calls.first_seen_at)                   AS first_seen_at,
                       MAX(calls.last_seen_at)                    AS last_seen_at,
                       GROUP_CONCAT(DISTINCT calls.groups_mentioned) AS groups_raw,
                       MAX(gmgn.holder_count)                     AS holder_count,
                       MAX(prices.market_cap)                     AS market_cap,
                       MAX(prices.price_change_h24)               AS price_change_h24
                {join_sql}
                WHERE {where_sql}
                GROUP BY calls.contract_address
                ORDER BY ({sort_field}) IS NULL,
                         {sort_field} {sort_dir}
                LIMIT ? OFFSET ?""",
            params + [page_size, offset],
        ).fetchall()

        result = []
        for r in rows:
            d = dict(r)
            groups_set: set[str] = set()
            for chunk in (d.pop("groups_raw") or "").split(","):
                g = chunk.strip()
                if g:
                    groups_set.add(g)
            d["groups_mentioned"] = ", ".join(sorted(groups_set)) if groups_set else None
            d["call_count"] = d.pop("total_calls")
            result.append(d)

        _enrich_rows(conn, result)
    finally:
        conn.close()

    return jsonify({
        "ready": True,
        "data": result,
        "rowCount": total,
        "pageCount": (total + page_size - 1) // page_size,
        "page": page,
        "pageSize": page_size,
        "from": d_from.isoformat(),
        "to": d_to.isoformat(),
        "filters": {
            "search": search,
            "launchpad": launchpads,
            "groups": groups,
            "sort": f"{sort_field}:{sort_dir.lower()}",
        },
    })


@app.route("/api/token/<ca>", methods=["GET"])
def api_token(ca: str):
    """Detail view for a single contract address: aggregated metrics across all
    dates seen, enriched with cached price/holder/metadata, plus a per-day call
    timeline. Used by /t/[ca] in the SPA."""
    if not Path(DB_PATH).exists():
        return jsonify({"ready": False}), 503

    if not ca or len(ca) > 64 or not all(c.isalnum() or c in "_-" for c in ca):
        return jsonify({"error": "invalid ca"}), 400

    conn = _conn()
    try:
        agg_row = conn.execute(
            """SELECT contract_address,
                      MAX(ticker)        AS ticker,
                      MAX(launchpad)     AS launchpad,
                      MAX(chain)         AS chain,
                      SUM(call_count)    AS call_count,
                      COUNT(*)           AS days_active,
                      MIN(first_seen_at) AS first_seen_at,
                      MAX(last_seen_at)  AS last_seen_at,
                      GROUP_CONCAT(DISTINCT groups_mentioned) AS groups_raw
               FROM calls WHERE contract_address = ?
               GROUP BY contract_address""",
            (ca,),
        ).fetchone()
        if not agg_row:
            return jsonify({"error": "not found"}), 404

        d = dict(agg_row)
        groups_set: set[str] = set()
        for chunk in (d.pop("groups_raw") or "").split(","):
            g = chunk.strip()
            if g:
                groups_set.add(g)
        d["groups_mentioned"] = ", ".join(sorted(groups_set)) if groups_set else None
        rows = [d]
        _enrich_rows(conn, rows)
        token = rows[0]

        timeline = conn.execute(
            """SELECT call_date, call_count, first_seen_at, last_seen_at, groups_mentioned
               FROM calls WHERE contract_address = ?
               ORDER BY call_date DESC
               LIMIT 30""",
            (ca,),
        ).fetchall()
    finally:
        conn.close()

    return jsonify({
        "ready": True,
        "token": token,
        "timeline": [dict(t) for t in timeline],
    })


@app.route("/api/watchlist", methods=["GET"])
def api_watchlist():
    """Personal watchlist: enriched rows for every CA in token_watchlist, ordered by added_at desc."""
    if not Path(DB_PATH).exists():
        return jsonify({"ready": False, "data": []}), 503

    conn = _conn()
    try:
        wl_rows = conn.execute(
            "SELECT contract_address, added_at FROM token_watchlist ORDER BY added_at DESC"
        ).fetchall()
        added_at = {r["contract_address"]: r["added_at"] for r in wl_rows}
        cas = list(added_at.keys())
        if not cas:
            return jsonify({"ready": True, "data": []})

        placeholders = ",".join("?" * len(cas))
        agg_rows = conn.execute(
            f"""SELECT contract_address,
                       MAX(ticker)        AS ticker,
                       MAX(launchpad)     AS launchpad,
                       MAX(chain)         AS chain,
                       SUM(call_count)    AS call_count,
                       MIN(first_seen_at) AS first_seen_at,
                       MAX(last_seen_at)  AS last_seen_at,
                       GROUP_CONCAT(DISTINCT groups_mentioned) AS groups_raw
                FROM calls
                WHERE contract_address IN ({placeholders})
                GROUP BY contract_address""",
            cas,
        ).fetchall()
        seen_cas = {r["contract_address"] for r in agg_rows}

        rows = []
        for r in agg_rows:
            d = dict(r)
            groups_set: set[str] = set()
            for chunk in (d.pop("groups_raw") or "").split(","):
                g = chunk.strip()
                if g:
                    groups_set.add(g)
            d["groups_mentioned"] = ", ".join(sorted(groups_set)) if groups_set else None
            d["added_at"] = added_at.get(d["contract_address"])
            rows.append(d)

        # CAs in watchlist but never called (e.g. just added) — return a stub row.
        for ca in cas:
            if ca not in seen_cas:
                rows.append({
                    "contract_address": ca,
                    "ticker": None,
                    "launchpad": None,
                    "chain": "Solana",
                    "call_count": 0,
                    "first_seen_at": None,
                    "last_seen_at": None,
                    "groups_mentioned": None,
                    "added_at": added_at[ca],
                })

        _enrich_rows(conn, rows)
        rows.sort(key=lambda r: r.get("added_at") or "", reverse=True)
    finally:
        conn.close()

    return jsonify({"ready": True, "data": rows})


@app.route("/api/watchlist/cas", methods=["GET"])
def api_watchlist_cas():
    """Lightweight set of CAs currently in the watchlist — used to render star indicators across the UI."""
    if not Path(DB_PATH).exists():
        return jsonify({"cas": []})
    conn = _conn()
    try:
        rows = conn.execute("SELECT contract_address FROM token_watchlist").fetchall()
    finally:
        conn.close()
    return jsonify({"cas": [r["contract_address"] for r in rows]})


@app.route("/api/watchlist/<ca>", methods=["POST", "DELETE"])
def api_watchlist_toggle(ca: str):
    if not ca or len(ca) > 64 or not all(c.isalnum() or c in "_-" for c in ca):
        return jsonify({"error": "invalid ca"}), 400

    conn = _conn()
    try:
        if request.method == "DELETE":
            conn.execute("DELETE FROM token_watchlist WHERE contract_address = ?", (ca,))
            conn.commit()
            return jsonify({"contract_address": ca, "watchlisted": False})
        now = datetime.now().isoformat()
        conn.execute(
            "INSERT OR IGNORE INTO token_watchlist (contract_address, added_at) VALUES (?, ?)",
            (ca, now),
        )
        conn.commit()
    finally:
        conn.close()

    return jsonify({"contract_address": ca, "watchlisted": True})


@app.route("/api/token/<ca>/note", methods=["GET"])
def api_token_note_get(ca: str):
    """Personal free-form note for a token. Used by /t/[ca] textarea."""
    if not ca or len(ca) > 64 or not all(c.isalnum() or c in "_-" for c in ca):
        return jsonify({"error": "invalid ca"}), 400
    if not Path(DB_PATH).exists():
        return jsonify({"note": "", "updated_at": None})

    conn = _conn()
    try:
        row = conn.execute(
            "SELECT note, updated_at FROM token_notes WHERE contract_address = ?", (ca,)
        ).fetchone()
    finally:
        conn.close()

    if not row:
        return jsonify({"note": "", "updated_at": None})
    return jsonify({"note": row["note"], "updated_at": row["updated_at"]})


@app.route("/api/token/<ca>/note", methods=["PUT"])
def api_token_note_put(ca: str):
    """Upsert the note for a token. Empty string deletes the row."""
    if not ca or len(ca) > 64 or not all(c.isalnum() or c in "_-" for c in ca):
        return jsonify({"error": "invalid ca"}), 400

    body = request.get_json(silent=True) or {}
    note = body.get("note", "")
    if not isinstance(note, str):
        return jsonify({"error": "note must be a string"}), 400
    note = note[:8000]
    now = datetime.now().isoformat()

    conn = _conn()
    try:
        if note.strip() == "":
            conn.execute("DELETE FROM token_notes WHERE contract_address = ?", (ca,))
            conn.commit()
            return jsonify({"note": "", "updated_at": None})
        conn.execute(
            """INSERT INTO token_notes (contract_address, note, updated_at)
               VALUES (?, ?, ?)
               ON CONFLICT(contract_address) DO UPDATE SET
                 note = excluded.note,
                 updated_at = excluded.updated_at""",
            (ca, note, now),
        )
        conn.commit()
    finally:
        conn.close()

    return jsonify({"note": note, "updated_at": now})


@app.route("/api/token/<ca>", methods=["DELETE"])
def api_delete_token(ca: str):
    """Hard-delete a token from every enrichment table.

    Irreversible: the token will only reappear if the scraper sees it again on
    a future call (which then re-creates the row from scratch — past history is
    gone). Used by the "Delisted" button in the SPA."""
    if not ca or len(ca) > 64 or not all(c.isalnum() or c in "_-" for c in ca):
        return jsonify({"error": "invalid ca"}), 400

    conn = _conn()
    try:
        deleted = 0
        for table in ("calls", "token_prices", "token_gmgn", "token_metadata", "token_notes", "token_watchlist"):
            try:
                cur = conn.execute(
                    f"DELETE FROM {table} WHERE contract_address = ?", (ca,)
                )
                deleted += cur.rowcount
            except sqlite3.OperationalError as e:
                log.debug("delete skip table=%s err=%s", table, e)
        conn.commit()
    finally:
        conn.close()

    return jsonify({"ok": True, "contract_address": ca, "deleted_rows": deleted})


# =========================================================== Telegram alerts

@app.route("/api/alerts")
def api_alerts():
    """Paginated list of telegram_alerts. TanStack-shaped response.

    Filters: type, min_usd, max_usd, min_mc, max_mc, ticker, actor, source, from, to.
    Order: msg_date DESC.
    """
    if not Path(DB_PATH).exists():
        return jsonify({
            "ready": False, "data": [], "rowCount": 0, "pageCount": 0,
            "page": 1, "pageSize": 100, "filters": {},
        })

    try:
        page = max(1, int(request.args.get("page", "1")))
        page_size = max(1, min(500, int(request.args.get("page_size", "100"))))
    except (ValueError, TypeError):
        page, page_size = 1, 100

    alert_type = (request.args.get("type") or "").strip().lower()
    ticker = (request.args.get("ticker") or "").strip()
    actor = (request.args.get("actor") or "").strip()
    source = (request.args.get("source") or "").strip()
    date_from = (request.args.get("from") or "").strip()
    date_to = (request.args.get("to") or "").strip()

    def _f(name: str) -> float | None:
        try:
            v = request.args.get(name)
            return float(v) if v not in (None, "") else None
        except (ValueError, TypeError):
            return None

    min_usd = _f("min_usd")
    max_usd = _f("max_usd")
    min_mc = _f("min_mc")
    max_mc = _f("max_mc")

    where = []
    params: list = []
    if alert_type and alert_type != "all":
        where.append("alert_type = ?")
        params.append(alert_type)
    if ticker:
        where.append("target_ticker LIKE ? COLLATE NOCASE")
        params.append(f"%{ticker}%")
    if actor:
        where.append("actor LIKE ? COLLATE NOCASE")
        params.append(f"%{actor}%")
    if source:
        where.append("source_channel = ?")
        params.append(source)
    if min_usd is not None:
        where.append("amount_usd >= ?")
        params.append(min_usd)
    if max_usd is not None:
        where.append("amount_usd <= ?")
        params.append(max_usd)
    if min_mc is not None:
        where.append("market_cap_usd >= ?")
        params.append(min_mc)
    if max_mc is not None:
        where.append("market_cap_usd <= ?")
        params.append(max_mc)
    if date_from:
        where.append("msg_date >= ?")
        params.append(date_from)
    if date_to:
        where.append("msg_date <= ?")
        params.append(date_to)

    where_sql = "WHERE " + " AND ".join(where) if where else ""

    conn = _conn()
    try:
        total = conn.execute(
            f"SELECT COUNT(*) AS c FROM telegram_alerts {where_sql}", params
        ).fetchone()["c"]

        offset = (page - 1) * page_size
        rows = conn.execute(
            f"""SELECT id, source_channel, msg_id, msg_date, msg_text,
                       alert_type, actor, target_ticker, amount_usd, market_cap_usd, parse_status
               FROM telegram_alerts
               {where_sql}
               ORDER BY msg_date DESC, id DESC
               LIMIT ? OFFSET ?""",
            [*params, page_size, offset],
        ).fetchall()
    finally:
        conn.close()

    page_count = (total + page_size - 1) // page_size if total else 0

    return jsonify({
        "ready": True,
        "data": [dict(r) for r in rows],
        "rowCount": total,
        "pageCount": page_count,
        "page": page,
        "pageSize": page_size,
        "filters": {
            "type": alert_type,
            "ticker": ticker,
            "actor": actor,
            "source": source,
            "min_usd": min_usd,
            "max_usd": max_usd,
            "min_mc": min_mc,
            "max_mc": max_mc,
            "from": date_from,
            "to": date_to,
        },
    })


@app.route("/api/alerts/stats")
def api_alerts_stats():
    if not Path(DB_PATH).exists():
        return jsonify({"alerts_today": 0, "top_actors_7d": [], "top_tickers_7d": []})

    today = date.today().isoformat()
    week_ago = (date.today() - timedelta(days=6)).isoformat()

    conn = _conn()
    try:
        today_count = conn.execute(
            "SELECT COUNT(*) AS c FROM telegram_alerts WHERE substr(msg_date,1,10) = ?",
            (today,),
        ).fetchone()["c"]

        actors = conn.execute(
            """SELECT actor, COUNT(*) AS hits
               FROM telegram_alerts
               WHERE substr(msg_date,1,10) >= ? AND actor IS NOT NULL
               GROUP BY actor
               ORDER BY hits DESC
               LIMIT 10""",
            (week_ago,),
        ).fetchall()

        tickers = conn.execute(
            """SELECT target_ticker, COUNT(*) AS hits
               FROM telegram_alerts
               WHERE substr(msg_date,1,10) >= ? AND target_ticker IS NOT NULL
               GROUP BY target_ticker
               ORDER BY hits DESC
               LIMIT 10""",
            (week_ago,),
        ).fetchall()
    finally:
        conn.close()

    return jsonify({
        "alerts_today": today_count,
        "top_actors_7d": [dict(r) for r in actors],
        "top_tickers_7d": [dict(r) for r in tickers],
    })


@app.route("/api/alerts/summary")
def api_alerts_summary():
    """Aggregated alerts by target ticker.

    Gives the operational view: total dollars added, number of alerts, distinct
    actors, whale count, KOL count, and last-seen timestamp for each ticker.
    """
    if not Path(DB_PATH).exists():
        return jsonify({"ready": False, "data": [], "rowCount": 0})

    alert_type = (request.args.get("type") or "").strip().lower()
    ticker = (request.args.get("ticker") or "").strip()
    actor = (request.args.get("actor") or "").strip()
    source = (request.args.get("source") or "").strip()
    date_from = (request.args.get("from") or "").strip()
    date_to = (request.args.get("to") or "").strip()
    try:
        limit = max(1, min(200, int(request.args.get("limit", "50"))))
    except (ValueError, TypeError):
        limit = 50

    def _f(name: str) -> float | None:
        try:
            v = request.args.get(name)
            return float(v) if v not in (None, "") else None
        except (ValueError, TypeError):
            return None

    min_usd = _f("min_usd")
    max_usd = _f("max_usd")
    min_mc = _f("min_mc")
    max_mc = _f("max_mc")

    where = ["target_ticker IS NOT NULL", "parse_status = 'matched'"]
    params: list = []
    if alert_type and alert_type != "all":
        where.append("alert_type = ?")
        params.append(alert_type)
    if ticker:
        where.append("target_ticker LIKE ? COLLATE NOCASE")
        params.append(f"%{ticker}%")
    if actor:
        where.append("actor LIKE ? COLLATE NOCASE")
        params.append(f"%{actor}%")
    if source:
        where.append("source_channel = ?")
        params.append(source)
    if min_usd is not None:
        where.append("amount_usd >= ?")
        params.append(min_usd)
    if max_usd is not None:
        where.append("amount_usd <= ?")
        params.append(max_usd)
    if min_mc is not None:
        where.append("market_cap_usd >= ?")
        params.append(min_mc)
    if max_mc is not None:
        where.append("market_cap_usd <= ?")
        params.append(max_mc)
    if date_from:
        where.append("msg_date >= ?")
        params.append(date_from)
    if date_to:
        where.append("msg_date <= ?")
        params.append(date_to)

    where_sql = "WHERE " + " AND ".join(where)

    conn = _conn()
    try:
        rows = conn.execute(
            f"""SELECT target_ticker,
                       COUNT(*) AS alert_count,
                       COUNT(DISTINCT actor) AS actor_count,
                       SUM(COALESCE(amount_usd, 0)) AS total_amount_usd,
                       AVG(market_cap_usd) AS avg_market_cap_usd,
                       MAX(market_cap_usd) AS max_market_cap_usd,
                       MAX(msg_date) AS last_seen_at,
                       SUM(CASE WHEN alert_type = 'whale' THEN 1 ELSE 0 END) AS whale_count,
                       SUM(CASE WHEN alert_type IN ('kol', 'kol_newpair') THEN 1 ELSE 0 END) AS kol_count
                FROM telegram_alerts
                {where_sql}
                GROUP BY target_ticker
                ORDER BY total_amount_usd DESC, alert_count DESC, last_seen_at DESC
                LIMIT ?""",
            [*params, limit],
        ).fetchall()
    finally:
        conn.close()

    data = [dict(r) for r in rows]
    return jsonify({"ready": True, "data": data, "rowCount": len(data)})


# --------------------------------------------------------------------- SPA host
# With static_url_path='' the Flask static handler claims `/<path:filename>` and
# returns 404 directly when the file doesn't exist — so a hard-reload on
# /day or /t/abc never reaches our catch-all. The 404 errorhandler below pulls
# those non-API paths back into the SPA by serving index.html (SvelteKit then
# resolves the route client-side).
@app.errorhandler(404)
def spa_fallback(_e):
    if request.path.startswith("/api/"):
        return jsonify({"error": "not found"}), 404
    return send_from_directory(app.static_folder, "index.html")


if __name__ == "__main__":
    port = int(os.getenv("DASHBOARD_PORT", "8080"))
    app.run(host="0.0.0.0", port=port, threaded=True)
