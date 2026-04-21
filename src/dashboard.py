"""Flask dashboard for padre-tracker.

Two routes:
  /       homepage — weekly overview, top tokens (price-enriched), group leaderboard
  /day    daily detail — full per-CA table with filters

Templates live in src/templates/. Price enrichment via src/enrich.py is called only on
the homepage's top-10 slice (small batch, short cache), keeping the server footprint light.
"""

import logging
import os
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

from flask import Flask, render_template, request, jsonify

import aggregations as agg
from aggregations import get_lifetime_windows
from enrich import get_prices
from gmgn import get_gmgn, init_cache as gmgn_init_cache

DB_PATH = os.getenv("DB_PATH", "./data/calls.db")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

logging.basicConfig(level=getattr(logging, LOG_LEVEL), format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

app = Flask(__name__)
log = logging.getLogger("padre-dashboard")


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


def _fmt_price(v) -> str:
    v = _safe_float(v)
    if v is None:
        return "—"
    if v >= 1:
        return f"{v:,.2f}"
    if v >= 0.01:
        return f"{v:.4f}"
    return f"{v:.6f}".rstrip("0").rstrip(".")


def _fmt_big(v) -> str:
    v = _safe_float(v)
    if not v:
        return "—"
    for unit, div in [("B", 1e9), ("M", 1e6), ("K", 1e3)]:
        if v >= div:
            return f"{v/div:.2f}{unit}"
    return f"{v:.0f}"


def _fmt_pct(v) -> str:
    v = _safe_float(v)
    if v is None:
        return "—"
    return f"{v * 100:.1f}%" if v <= 1.0 else f"{v:.1f}%"


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


@app.route("/")
def home():
    if not Path(DB_PATH).exists():
        return render_template(
            "home.html",
            active_nav="home",
            date_str=date.today().isoformat(),
            today={"tokens": 0, "total_calls": 0},
            delta={"tokens_str": "±0", "tokens_class": "flat",
                   "calls_str": "±0", "calls_class": "flat"},
            week=[], week_totals={"tokens": 0, "total_calls": 0},
            hourly_today=[{"hour": h, "new_tokens": 0} for h in range(24)],
            hourly_max=0, top_tokens=[], groups=[],
        )

    conn = _conn()
    try:
        data = agg.overview(conn, date.today())

        t_delta = _delta(data["today"]["tokens"], data["yesterday"]["tokens"])
        c_delta = _delta(data["today"]["total_calls"], data["yesterday"]["total_calls"])

        # Enrich top 10 with DexScreener + GMGN (batched/cached)
        top = data["top_tokens_week"]
        if top:
            top_cas = [t["contract_address"] for t in top]
            prices = get_prices(conn, top_cas)
            gmgn_data = get_gmgn(conn, top_cas)
            for t in top:
                p = prices.get(t["contract_address"]) or {}
                t["price_usd"] = _safe_float(p.get("price_usd"))
                t["price_fmt"] = _fmt_price(t["price_usd"])
                t["price_change_h24"] = _safe_float(p.get("price_change_h24"))
                t["market_cap"] = _safe_float(p.get("market_cap"))
                t["mc_fmt"] = _fmt_big(t["market_cap"])
                g = gmgn_data.get(t["contract_address"]) or {}
                t["holder_count"] = g.get("holder_count")
                t["top10_pct"] = _fmt_pct(g.get("top10_pct"))
                t["renounced"] = g.get("renounced")
                t["mint_revoked"] = g.get("renounced_mint")
                t["freeze_revoked"] = g.get("renounced_freeze")
                t["lp_burned_pct"] = _safe_float(g.get("burn_ratio"))
                t["burn_status"] = g.get("burn_status")

        hourly_max = max((h["new_tokens"] for h in data["hourly_today"]), default=0)

        return render_template(
            "home.html",
            active_nav="home",
            date_str=date.today().isoformat(),
            today=data["today"],
            delta={
                "tokens_str": t_delta["str"], "tokens_class": t_delta["class"],
                "calls_str": c_delta["str"], "calls_class": c_delta["class"],
            },
            week=data["week"],
            week_totals=data["week_totals"],
            hourly_today=data["hourly_today"],
            hourly_max=hourly_max,
            top_tokens=top,
            groups=data["groups_week"],
        )
    finally:
        conn.close()


# ------------------------------------------------------------------ /day
def _daily_data(target: date):
    if not Path(DB_PATH).exists():
        return [], {}, [], []

    conn = _conn()
    try:
        all_rows = conn.execute(
            """SELECT contract_address, ticker, chain, launchpad, call_count,
                      first_seen_at, last_seen_at, groups_mentioned
               FROM calls WHERE call_date = ?
               ORDER BY call_count DESC, first_seen_at""",
            (target.isoformat(),),
        ).fetchall()
    finally:
        conn.close()

    all_rows = [dict(r) for r in all_rows]

    # Compute duration + velocity on ALL rows (needed for client-side filtering too)
    for r in all_rows:
        try:
            t0 = datetime.fromisoformat(r["first_seen_at"])
            t1 = datetime.fromisoformat(r["last_seen_at"])
            mins = (t1 - t0).total_seconds() / 60
            r["duration_min"] = round(mins)
            if mins < 1:
                r["duration_str"] = "once"
                r["velocity"] = "—"
            elif mins < 90:
                r["duration_str"] = f"{round(mins)}m"
                r["velocity"] = f"{r['call_count'] / max(mins / 60, 1/60):.1f}" if mins >= 30 else "—"
            else:
                r["duration_str"] = f"{mins/60:.1f}h"
                r["velocity"] = f"{r['call_count'] / (mins / 60):.1f}"
        except Exception:
            r["duration_min"] = 0
            r["duration_str"] = "—"
            r["velocity"] = "—"

    all_groups: set[str] = set()
    for r in all_rows:
        if r["groups_mentioned"]:
            for g in r["groups_mentioned"].split(","):
                g = g.strip()
                if g:
                    all_groups.add(g)
    all_launchpads = sorted({r["launchpad"] for r in all_rows if r["launchpad"]})

    lp_counts: dict[str, int] = {}
    group_counts: dict[str, int] = {}
    for r in all_rows:
        if r["launchpad"]:
            lp_counts[r["launchpad"]] = lp_counts.get(r["launchpad"], 0) + 1
        if r["groups_mentioned"]:
            for g in r["groups_mentioned"].split(","):
                g = g.strip()
                if g:
                    group_counts[g] = group_counts.get(g, 0) + 1

    stats = {
        "tokens": len(all_rows),
        "total_calls": sum(r["call_count"] for r in all_rows),
        "with_ticker": sum(1 for r in all_rows if r["ticker"]),
        "with_group": sum(1 for r in all_rows if r["groups_mentioned"]),
        "top_group": max(group_counts, key=group_counts.get) if group_counts else None,
        "top_launchpad": max(lp_counts, key=lp_counts.get) if lp_counts else None,
    }

    return list(all_rows), stats, sorted(all_groups), all_launchpads


@app.route("/day")
def day():
    d_str = request.args.get("d")
    try:
        target = date.fromisoformat(d_str) if d_str else date.today()
    except ValueError:
        target = date.today()

    date_prev = (target - timedelta(days=1)).isoformat()
    date_next = (target + timedelta(days=1)).isoformat()
    today = date.today()

    # All filtering is client-side for instant UX.
    calls, stats, all_groups, all_launchpads = _daily_data(target)

    # Enrich all rows with price + MC + lifetime windows + GMGN (cache-only for speed).
    if calls:
        conn = _conn()
        try:
            cas = [r["contract_address"] for r in calls]
            prices = get_prices(conn, cas)
            lifetime = get_lifetime_windows(conn, cas)
            # GMGN: fetch live for top-30 by call_count; rest read from cache
            top30_cas = [r["contract_address"] for r in sorted(calls, key=lambda x: x["call_count"], reverse=True)[:30]]
            gmgn_data = get_gmgn(conn, top30_cas)
            # Cache-only for remaining CAs
            rest_cas = [ca for ca in cas if ca not in gmgn_data]
            if rest_cas:
                gmgn_init_cache(conn)
                ph = ",".join("?" * len(rest_cas))
                rest_rows = conn.execute(
                    f"SELECT * FROM token_gmgn WHERE contract_address IN ({ph})",
                    tuple(rest_cas),
                ).fetchall()
                gmgn_data.update({r["contract_address"]: dict(r) for r in rest_rows})
        finally:
            conn.close()
        for r in calls:
            p = prices.get(r["contract_address"]) or {}
            r["price_usd"] = _safe_float(p.get("price_usd"))
            r["price_fmt"] = _fmt_price(r["price_usd"])
            r["price_change_h24"] = _safe_float(p.get("price_change_h24"))
            r["market_cap"] = _safe_float(p.get("market_cap")) or 0
            r["mc_fmt"] = _fmt_big(r["market_cap"])
            lw = lifetime.get(r["contract_address"]) or {}
            r["lifetime_first"] = (lw.get("first_ever") or "")[:10]
            r["lifetime_last"] = (lw.get("last_ever") or "")[:10]
            r["lifetime_calls"] = lw.get("lifetime_calls") or r["call_count"]
            r["days_active"] = lw.get("days_active") or 1
            r["is_recall"] = r["lifetime_first"] and r["lifetime_first"] < target.isoformat()
            g = gmgn_data.get(r["contract_address"]) or {}
            r["holder_count"] = g.get("holder_count")
            r["top10_pct"] = _fmt_pct(g.get("top10_pct"))
            r["renounced"] = g.get("renounced")
            r["mint_revoked"] = g.get("renounced_mint")
            r["freeze_revoked"] = g.get("renounced_freeze")
            r["lp_burned_pct"] = _fmt_pct(g.get("burn_ratio"))
            r["burn_status"] = g.get("burn_status")
            r["swaps_5m"] = g.get("swaps_5m")
            r["swaps_1h"] = g.get("swaps_1h")

    return render_template(
        "day.html",
        active_nav="day",
        calls=calls,
        stats=stats,
        all_groups=all_groups,
        all_launchpads=all_launchpads,
        date_str=target.isoformat(),
        date_prev=date_prev,
        date_next=date_next,
        is_today=(target == today),
        today=today.isoformat(),
    )


@app.route("/range")
def range_view():
    today = date.today()
    d_from_str = request.args.get("from")
    d_to_str = request.args.get("to")
    try:
        d_from = date.fromisoformat(d_from_str) if d_from_str else today - timedelta(days=6)
    except ValueError:
        d_from = today - timedelta(days=6)
    try:
        d_to = date.fromisoformat(d_to_str) if d_to_str else today
    except ValueError:
        d_to = today
    if d_from > d_to:
        d_from, d_to = d_to, d_from

    if not Path(DB_PATH).exists():
        return render_template("range.html", active_nav="range", calls=[], stats={},
                               all_groups=[], all_launchpads=[],
                               date_from=d_from.isoformat(), date_to=d_to.isoformat(),
                               today=today.isoformat())

    conn = _conn()
    try:
        rows = conn.execute(
            """SELECT contract_address,
                      MAX(ticker)           AS ticker,
                      MAX(launchpad)        AS launchpad,
                      SUM(call_count)       AS total_calls,
                      COUNT(*)              AS days_active,
                      MIN(first_seen_at)    AS first_seen_at,
                      MAX(last_seen_at)     AS last_seen_at,
                      GROUP_CONCAT(groups_mentioned, ',') AS groups_raw
               FROM calls
               WHERE call_date >= ? AND call_date <= ?
               GROUP BY contract_address
               ORDER BY total_calls DESC""",
            (d_from.isoformat(), d_to.isoformat()),
        ).fetchall()
        all_rows = []
        for r in rows:
            d = dict(r)
            groups_set: set[str] = set()
            for chunk in (d.pop("groups_raw") or "").split(","):
                g = chunk.strip()
                if g:
                    groups_set.add(g)
            d["groups_mentioned"] = ", ".join(sorted(groups_set)) if groups_set else None
            d["call_count"] = d.pop("total_calls")
            all_rows.append(d)

        cas = [r["contract_address"] for r in all_rows]
        prices = get_prices(conn, cas) if cas else {}
        gmgn_init_cache(conn)
        placeholders = ",".join("?" * len(cas)) if cas else "NULL"
        gmgn_rows = conn.execute(
            f"SELECT * FROM token_gmgn WHERE contract_address IN ({placeholders})",
            tuple(cas),
        ).fetchall() if cas else []
        gmgn_data = {row["contract_address"]: dict(row) for row in gmgn_rows}
    finally:
        conn.close()

    all_groups: set[str] = set()
    lp_counts: dict[str, int] = {}
    group_counts: dict[str, int] = {}

    for r in all_rows:
        p = prices.get(r["contract_address"]) or {}
        r["price_usd"] = _safe_float(p.get("price_usd"))
        r["price_fmt"] = _fmt_price(r["price_usd"])
        r["price_change_h24"] = _safe_float(p.get("price_change_h24"))
        r["market_cap"] = _safe_float(p.get("market_cap")) or 0
        r["mc_fmt"] = _fmt_big(r["market_cap"])
        g = gmgn_data.get(r["contract_address"]) or {}
        r["holder_count"] = g.get("holder_count")
        r["top10_pct"] = _fmt_pct(g.get("top10_pct"))
        r["renounced"] = g.get("renounced")
        r["mint_revoked"] = g.get("renounced_mint")
        r["freeze_revoked"] = g.get("renounced_freeze")
        r["burn_status"] = g.get("burn_status")
        r["lp_burned_pct"] = _fmt_pct(g.get("burn_ratio"))

        if r["launchpad"]:
            lp_counts[r["launchpad"]] = lp_counts.get(r["launchpad"], 0) + 1
        if r["groups_mentioned"]:
            for grp in r["groups_mentioned"].split(","):
                grp = grp.strip()
                if grp:
                    all_groups.add(grp)
                    group_counts[grp] = group_counts.get(grp, 0) + 1

    all_launchpads = sorted({r["launchpad"] for r in all_rows if r["launchpad"]})
    stats = {
        "tokens": len(all_rows),
        "total_calls": sum(r["call_count"] for r in all_rows),
        "with_group": sum(1 for r in all_rows if r["groups_mentioned"]),
        "days": (d_to - d_from).days + 1,
        "top_group": max(group_counts, key=group_counts.get) if group_counts else None,
        "top_launchpad": max(lp_counts, key=lp_counts.get) if lp_counts else None,
    }

    # Per-day series for the chart
    conn2 = _conn()
    try:
        day_series = conn2.execute(
            """SELECT call_date, COUNT(*) AS tokens, COALESCE(SUM(call_count),0) AS total_calls
               FROM calls WHERE call_date >= ? AND call_date <= ?
               GROUP BY call_date ORDER BY call_date""",
            (d_from.isoformat(), d_to.isoformat()),
        ).fetchall()
        day_series = [dict(r) for r in day_series]
    finally:
        conn2.close()

    # Top groups for chart
    top_groups_chart = sorted(group_counts.items(), key=lambda x: x[1], reverse=True)[:10]

    return render_template(
        "range.html",
        active_nav="range",
        calls=all_rows,
        stats=stats,
        all_groups=sorted(all_groups),
        all_launchpads=all_launchpads,
        date_from=d_from.isoformat(),
        date_to=d_to.isoformat(),
        today=today.isoformat(),
        day_series=day_series,
        top_groups_chart=top_groups_chart,
    )


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


if __name__ == "__main__":
    port = int(os.getenv("DASHBOARD_PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
