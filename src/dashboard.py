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
import gmgn_worker
import metadata_worker
from cache import ttl_cache
from db import init_db
from enrich import get_prices
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
    _boot.close()
    gmgn_worker.start(DB_PATH)
    metadata_worker.start(DB_PATH, HELIUS_API_KEY)


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

    The dashboard polls the DB once per second for rows with first_seen_at
    greater than the last value already pushed to this client, then streams
    them as `event: new`. A heartbeat (`event: ping`) every 15s keeps proxies
    and EventSource connections alive. The watermark starts at "now" so a
    fresh client only receives genuinely live tokens, not the day's backlog.
    """
    if not Path(DB_PATH).exists():
        return Response("db not ready\n", status=503, mimetype="text/plain")

    @stream_with_context
    def gen():
        since = datetime.now().isoformat()
        last_ping = time.monotonic()
        yield f"event: ready\ndata: {json.dumps({'since': since})}\n\n"

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

            time.sleep(1)

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
    "call_count": "call_count",
    "first_seen_at": "first_seen_at",
    "last_seen_at": "last_seen_at",
    "ticker": "ticker",
    "launchpad": "launchpad",
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
    prices = get_prices(conn, cas)
    gmgn_data, stale = get_gmgn_cached(conn, cas)
    gmgn_worker.enqueue_refresh(stale)
    meta_data, meta_stale = get_metadata_cached(conn, cas)
    metadata_worker.enqueue_refresh(meta_stale)
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
      sort=call_count:desc   (field: call_count|first_seen_at|last_seen_at|ticker|launchpad)
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

    search = (request.args.get("search") or "").strip()
    launchpads = _csv_param(request.args.get("launchpad"))
    groups = _csv_param(request.args.get("groups"))
    sort_field, sort_dir = _parse_sort(
        request.args.get("sort"), _DAY_SORT_FIELDS, "call_count", "desc"
    )

    where = ["call_date = ?"]
    params: list = [target.isoformat()]

    if search:
        where.append("(ticker LIKE ? OR contract_address LIKE ?)")
        like = f"%{search}%"
        params += [like, like]

    if launchpads:
        where.append("launchpad IN (" + ",".join("?" * len(launchpads)) + ")")
        params += launchpads

    if groups:
        where.append("(" + " OR ".join(["groups_mentioned LIKE ?"] * len(groups)) + ")")
        params += [f"%{g}%" for g in groups]

    where_sql = " AND ".join(where)
    conn = _conn()
    try:
        total = conn.execute(f"SELECT COUNT(*) FROM calls WHERE {where_sql}", params).fetchone()[0]

        offset = (page - 1) * page_size
        rows = conn.execute(
            f"""SELECT contract_address, ticker, chain, launchpad, call_count,
                       first_seen_at, last_seen_at, groups_mentioned
                FROM calls WHERE {where_sql}
                ORDER BY {sort_field} {sort_dir}, first_seen_at DESC
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
      page, page_size, search, launchpad, groups, sort
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

    search = (request.args.get("search") or "").strip()
    launchpads = _csv_param(request.args.get("launchpad"))
    groups = _csv_param(request.args.get("groups"))
    range_sort = {
        "call_count": "total_calls",
        "days_active": "days_active",
        "first_seen_at": "first_seen_at",
        "last_seen_at": "last_seen_at",
        "ticker": "ticker",
        "launchpad": "launchpad",
    }
    sort_field, sort_dir = _parse_sort(
        request.args.get("sort"), range_sort, "call_count", "desc"
    )

    having = []
    params: list = [d_from.isoformat(), d_to.isoformat()]
    row_where = ["call_date >= ?", "call_date <= ?"]

    if search:
        row_where.append("(ticker LIKE ? OR contract_address LIKE ?)")
        like = f"%{search}%"
        params += [like, like]

    if launchpads:
        row_where.append("launchpad IN (" + ",".join("?" * len(launchpads)) + ")")
        params += launchpads

    if groups:
        row_where.append("(" + " OR ".join(["groups_mentioned LIKE ?"] * len(groups)) + ")")
        params += [f"%{g}%" for g in groups]

    where_sql = " AND ".join(row_where)
    having_sql = (" HAVING " + " AND ".join(having)) if having else ""

    conn = _conn()
    try:
        total = conn.execute(
            f"""SELECT COUNT(*) FROM (
                 SELECT contract_address FROM calls WHERE {where_sql}
                 GROUP BY contract_address{having_sql}
               )""",
            params,
        ).fetchone()[0]

        offset = (page - 1) * page_size
        rows = conn.execute(
            f"""SELECT contract_address,
                       MAX(ticker)        AS ticker,
                       MAX(launchpad)     AS launchpad,
                       SUM(call_count)    AS total_calls,
                       COUNT(*)           AS days_active,
                       MIN(first_seen_at) AS first_seen_at,
                       MAX(last_seen_at)  AS last_seen_at,
                       GROUP_CONCAT(DISTINCT groups_mentioned) AS groups_raw
                FROM calls WHERE {where_sql}
                GROUP BY contract_address{having_sql}
                ORDER BY {sort_field} {sort_dir}
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


# --------------------------------------------------------------------- SPA host
# Catch-all for client-side routing: any path not matched above falls back to
# index.html so the SvelteKit app can take over. Real static files (/_app/*,
# /favicon.svg, etc.) are served by Flask's automatic static handling because
# of static_folder + static_url_path='' on the Flask() ctor.
@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def spa(path: str):
    build = Path(app.static_folder)
    target = build / path
    if path and target.is_file():
        return send_from_directory(build, path)
    return send_from_directory(build, "index.html")


if __name__ == "__main__":
    port = int(os.getenv("DASHBOARD_PORT", "8080"))
    app.run(host="0.0.0.0", port=port, threaded=True)
