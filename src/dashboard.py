"""Flask API + SPA host for padre-tracker.

JSON API under /api/* powers the SvelteKit frontend (served from frontend/build/).
Everything else returns the SPA's index.html so client-side routing works.
"""

import json
import logging
import os
import sqlite3
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from flask import Flask, Response, request, jsonify, send_from_directory, stream_with_context

import aggregations as agg
from cache import ttl_cache
from db import init_db
from enrich import get_prices_cached
from gmgn import get_gmgn_cached
from metadata import get_metadata_cached

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

    conn = _conn()
    try:
        top = [dict(t) for t in data["top_tokens_week"]]
        _enrich_rows(conn, top)
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
        "hourly_today": data["hourly_today"],
        "top_tokens": top,
        "groups": data["groups_week"],
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
        for table in ("calls", "token_prices", "token_gmgn", "token_metadata"):
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
