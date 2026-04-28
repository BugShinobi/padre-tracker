"""Aggregation queries for the homepage — all SQL, no heavy compute.

Kept separate from dashboard.py so the routes stay thin.
"""

import sqlite3
from datetime import date, timedelta


def daily_summary(conn: sqlite3.Connection, d: date) -> dict:
    row = conn.execute(
        """SELECT COUNT(*) AS tokens,
                  COALESCE(SUM(call_count), 0) AS total_calls,
                  SUM(CASE WHEN ticker IS NOT NULL AND ticker != '' THEN 1 ELSE 0 END) AS with_ticker,
                  SUM(CASE WHEN groups_mentioned IS NOT NULL AND groups_mentioned != '' THEN 1 ELSE 0 END) AS with_group
           FROM calls WHERE call_date = ?""",
        (d.isoformat(),),
    ).fetchone()
    return dict(row) if row else {"tokens": 0, "total_calls": 0, "with_ticker": 0, "with_group": 0}


def week_series(conn: sqlite3.Connection, today: date, days: int = 7) -> list[dict]:
    """One row per day for the last `days` days, including today, zero-filled for missing days."""
    start = today - timedelta(days=days - 1)
    rows = conn.execute(
        """SELECT call_date, COUNT(*) AS tokens, COALESCE(SUM(call_count), 0) AS total_calls
           FROM calls WHERE call_date >= ?
           GROUP BY call_date ORDER BY call_date""",
        (start.isoformat(),),
    ).fetchall()
    by_date = {r["call_date"]: dict(r) for r in rows}

    out = []
    for i in range(days):
        d = start + timedelta(days=i)
        k = d.isoformat()
        if k in by_date:
            out.append(by_date[k])
        else:
            out.append({"call_date": k, "tokens": 0, "total_calls": 0})
    return out


def top_tokens(
    conn: sqlite3.Connection,
    since: date,
    limit: int = 10,
) -> list[dict]:
    """Top token by cumulative calls across days (since `since`, inclusive).

    Collapses same CA across days — one CA can have rows for multiple call_dates.
    """
    rows = conn.execute(
        """SELECT contract_address,
                  MAX(ticker) AS ticker,
                  MAX(launchpad) AS launchpad,
                  SUM(call_count) AS total_calls,
                  COUNT(*) AS days_active,
                  MIN(first_seen_at) AS first_seen,
                  MAX(last_seen_at) AS last_seen,
                  GROUP_CONCAT(DISTINCT groups_mentioned) AS groups_raw
           FROM calls
           WHERE call_date >= ?
             AND (ticker IS NOT NULL AND ticker != '')
           GROUP BY contract_address
           ORDER BY total_calls DESC
           LIMIT ?""",
        (since.isoformat(), limit),
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        # Flatten groups_raw (comma-of-comma mess) → unique list
        groups: set[str] = set()
        for chunk in (d.pop("groups_raw") or "").split(","):
            g = chunk.strip()
            if g:
                groups.add(g)
        d["groups"] = sorted(groups)
        out.append(d)
    return out


def group_leaderboard(
    conn: sqlite3.Connection,
    since: date,
    limit: int = 10,
) -> list[dict]:
    """Groups by number of distinct CAs called since `since` (inclusive).

    groups_mentioned is a comma-joined string — expand in Python since SQLite has no split.
    """
    rows = conn.execute(
        """SELECT contract_address, groups_mentioned, call_count
           FROM calls
           WHERE call_date >= ? AND groups_mentioned IS NOT NULL AND groups_mentioned != ''""",
        (since.isoformat(),),
    ).fetchall()

    stats: dict[str, dict] = {}
    for r in rows:
        ca = r["contract_address"]
        for g in (r["groups_mentioned"] or "").split(","):
            g = g.strip()
            if not g:
                continue
            s = stats.setdefault(g, {"group": g, "tokens": set(), "calls": 0})
            s["tokens"].add(ca)
            s["calls"] += r["call_count"]

    out = [
        {"group": s["group"], "tokens": len(s["tokens"]), "calls": s["calls"]}
        for s in stats.values()
    ]
    out.sort(key=lambda x: x["tokens"], reverse=True)
    return out[:limit]


def hourly_distribution(conn: sqlite3.Connection, d: date) -> list[dict]:
    """New tokens per hour of the day (based on first_seen_at). Hours 0..23, zero-filled."""
    rows = conn.execute(
        """SELECT CAST(strftime('%H', first_seen_at) AS INTEGER) AS hour,
                  COUNT(*) AS new_tokens
           FROM calls WHERE call_date = ?
           GROUP BY hour""",
        (d.isoformat(),),
    ).fetchall()
    by_h = {r["hour"]: r["new_tokens"] for r in rows}
    return [{"hour": h, "new_tokens": by_h.get(h, 0)} for h in range(24)]


def overview(conn: sqlite3.Connection, today: date) -> dict:
    """Assemble everything the homepage needs in one call."""
    yesterday = today - timedelta(days=1)
    week_ago = today - timedelta(days=6)  # inclusive → last 7 days

    return {
        "today": daily_summary(conn, today),
        "yesterday": daily_summary(conn, yesterday),
        "week": week_series(conn, today, days=7),
        "week_totals": _sum_week(week_series(conn, today, days=7)),
        "top_tokens_today": top_tokens(conn, today, limit=10),
        "top_tokens_week": top_tokens(conn, week_ago, limit=10),
        "groups_week": group_leaderboard(conn, week_ago, limit=10),
        "hourly_today": hourly_distribution(conn, today),
    }


def _sum_week(series: list[dict]) -> dict:
    return {
        "tokens": sum(d["tokens"] for d in series),
        "total_calls": sum(d["total_calls"] for d in series),
    }


def get_lifetime_windows(conn: sqlite3.Connection, cas: list[str]) -> dict[str, dict]:
    """Return lifetime first/last seen + total calls + days active for each CA (cross-day).

    Returns {ca: {first_ever, last_ever, lifetime_calls, days_active}} for all CAs in list.
    """
    if not cas:
        return {}
    placeholders = ",".join("?" * len(cas))
    rows = conn.execute(
        f"""SELECT contract_address,
                   MIN(first_seen_at) AS first_ever,
                   MAX(last_seen_at)  AS last_ever,
                   SUM(call_count)    AS lifetime_calls,
                   COUNT(*)           AS days_active
            FROM calls
            WHERE contract_address IN ({placeholders})
            GROUP BY contract_address""",
        tuple(cas),
    ).fetchall()
    return {r["contract_address"]: dict(r) for r in rows}
