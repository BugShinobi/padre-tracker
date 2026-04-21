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

from flask import Flask, render_template, request

import aggregations as agg
from enrich import get_prices

DB_PATH = os.getenv("DB_PATH", "./data/calls.db")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

logging.basicConfig(level=getattr(logging, LOG_LEVEL), format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

app = Flask(__name__)
log = logging.getLogger("padre-dashboard")


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _fmt_price(v: float | None) -> str:
    if v is None:
        return "—"
    if v >= 1:
        return f"{v:,.2f}"
    if v >= 0.01:
        return f"{v:.4f}"
    return f"{v:.6f}".rstrip("0").rstrip(".")


def _fmt_big(v: float | None) -> str:
    if not v:
        return "—"
    for unit, div in [("B", 1e9), ("M", 1e6), ("K", 1e3)]:
        if v >= div:
            return f"{v/div:.2f}{unit}"
    return f"{v:.0f}"


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

        # Enrich top 10 with DexScreener (batched, cached)
        top = data["top_tokens_week"]
        if top:
            prices = get_prices(conn, [t["contract_address"] for t in top])
            for t in top:
                p = prices.get(t["contract_address"]) or {}
                t["price_usd"] = p.get("price_usd")
                t["price_fmt"] = _fmt_price(p.get("price_usd"))
                t["price_change_h24"] = p.get("price_change_h24")
                t["market_cap"] = p.get("market_cap")
                t["mc_fmt"] = _fmt_big(p.get("market_cap"))

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

    # Enrich all rows with price + MC so client-side MC filter works.
    if calls:
        conn = _conn()
        try:
            prices = get_prices(conn, [r["contract_address"] for r in calls])
        finally:
            conn.close()
        for r in calls:
            p = prices.get(r["contract_address"]) or {}
            r["price_usd"] = p.get("price_usd")
            r["price_fmt"] = _fmt_price(p.get("price_usd"))
            r["price_change_h24"] = p.get("price_change_h24")
            r["market_cap"] = p.get("market_cap") or 0
            r["mc_fmt"] = _fmt_big(p.get("market_cap"))

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


if __name__ == "__main__":
    port = int(os.getenv("DASHBOARD_PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
