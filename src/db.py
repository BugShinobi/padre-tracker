"""SQLite layer for padre-tracker calls."""

import sqlite3
from datetime import datetime, date
from pathlib import Path


def init_db(db_path: str) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS calls (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            contract_address TEXT NOT NULL,
            ticker           TEXT,
            chain            TEXT DEFAULT 'Solana',
            launchpad        TEXT,
            call_count       INTEGER DEFAULT 1,
            first_seen_at    TEXT NOT NULL,
            last_seen_at     TEXT NOT NULL,
            groups_mentioned TEXT,
            call_date        TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_ca_date
        ON calls (contract_address, call_date)
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS call_events (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            event_key        TEXT NOT NULL UNIQUE,
            contract_address TEXT NOT NULL,
            ticker           TEXT,
            chain            TEXT DEFAULT 'Solana',
            launchpad        TEXT,
            group_name       TEXT,
            call_bucket      TEXT,
            row_text         TEXT,
            observed_at      TEXT NOT NULL,
            call_date        TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_calls_date ON calls(call_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_calls_first_seen ON calls(first_seen_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_calls_ca ON calls(contract_address)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_call_events_date ON call_events(call_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_call_events_ca_date ON call_events(contract_address, call_date)")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tracker_status (
            key        TEXT PRIMARY KEY,
            value      TEXT,
            updated_at TEXT NOT NULL
        )
    """)
    _migrate_add_launchpad(conn)
    _cleanup_bad_tickers(conn)
    conn.commit()
    return conn


def record_tracker_status(conn: sqlite3.Connection, **values) -> None:
    now = datetime.now().isoformat()
    for key, value in values.items():
        conn.execute(
            """INSERT INTO tracker_status (key, value, updated_at)
               VALUES (?, ?, ?)
               ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at""",
            (key, "" if value is None else str(value), now),
        )
    conn.commit()


def _migrate_add_launchpad(conn: sqlite3.Connection) -> None:
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(calls)").fetchall()}
    if "launchpad" not in cols:
        conn.execute("ALTER TABLE calls ADD COLUMN launchpad TEXT")


def _cleanup_bad_tickers(conn: sqlite3.Connection) -> None:
    """Null out pure-digit / single-char / garbage tickers accumulated before the regex fix."""
    conn.execute(
        "UPDATE calls SET ticker = NULL WHERE ticker IS NOT NULL AND ("
        "ticker GLOB '[0-9]*' AND ticker NOT GLOB '*[A-Za-z]*' OR length(ticker) < 2)"
    )


def purge_by_launchpad(conn: sqlite3.Connection, launchpads: set[str]) -> int:
    """Delete all rows whose launchpad is in the given set. Returns rows deleted."""
    if not launchpads:
        return 0
    placeholders = ",".join("?" * len(launchpads))
    cur = conn.execute(f"DELETE FROM calls WHERE launchpad IN ({placeholders})", tuple(launchpads))
    conn.commit()
    return cur.rowcount


def purge_low_quality(conn: sqlite3.Connection) -> int:
    """Delete rows with no ticker AND no group — unidentifiable tokens."""
    cur = conn.execute(
        "DELETE FROM calls WHERE (ticker IS NULL OR ticker = '') "
        "AND (groups_mentioned IS NULL OR groups_mentioned = '')"
    )
    conn.commit()
    return cur.rowcount


def purge_no_group(conn: sqlite3.Connection) -> int:
    """Delete rows with no group mentioned — likely DEX Paid sponsored events, not real calls."""
    cur = conn.execute(
        "DELETE FROM calls WHERE groups_mentioned IS NULL OR groups_mentioned = ''"
    )
    conn.commit()
    return cur.rowcount


def reset_today_counts(conn: sqlite3.Connection) -> int:
    """Reset today's inflated call_counts to 1 (after counter-logic fix). Returns rows updated."""
    call_date = datetime.now().strftime("%Y-%m-%d")
    cur = conn.execute(
        "UPDATE calls SET call_count = 1 WHERE call_date = ? AND call_count > 1",
        (call_date,),
    )
    conn.commit()
    return cur.rowcount


def backfill_counts_from_groups(conn: sqlite3.Connection) -> int:
    """Ensure call_count is at least the number of distinct groups recorded.

    Older scraper logic deduped by CA before counting, so tokens seen in many
    groups could have call_count=1 with several groups_mentioned. This is a
    conservative repair: it never lowers counts and cannot recover repeat calls
    from the same group.
    """
    rows = conn.execute(
        "SELECT id, call_count, groups_mentioned FROM calls WHERE groups_mentioned IS NOT NULL"
    ).fetchall()
    updated = 0
    for r in rows:
        groups = {g.strip() for g in (r["groups_mentioned"] or "").split(",") if g.strip()}
        group_count = len(groups)
        if group_count > (r["call_count"] or 0):
            conn.execute("UPDATE calls SET call_count = ? WHERE id = ?", (group_count, r["id"]))
            updated += 1
    conn.commit()
    return updated


def repair_call_aggregates_from_events(conn: sqlite3.Connection) -> int:
    """Recover missing/undercounted daily aggregate rows from raw call events."""
    rows = conn.execute(
        """SELECT contract_address, call_date, ticker, chain, launchpad, group_name, observed_at
           FROM call_events
           ORDER BY call_date, contract_address, observed_at"""
    ).fetchall()
    aggregates: dict[tuple[str, str], dict] = {}
    for row in rows:
        key = (row["contract_address"], row["call_date"])
        agg = aggregates.setdefault(
            key,
            {
                "contract_address": row["contract_address"],
                "call_date": row["call_date"],
                "ticker": None,
                "chain": "Solana",
                "launchpad": None,
                "call_count": 0,
                "first_seen_at": row["observed_at"],
                "last_seen_at": row["observed_at"],
                "groups_mentioned": "",
            },
        )
        agg["call_count"] += 1
        agg["ticker"] = agg["ticker"] or row["ticker"]
        agg["chain"] = row["chain"] or agg["chain"]
        agg["launchpad"] = agg["launchpad"] or row["launchpad"]
        agg["first_seen_at"] = min(agg["first_seen_at"], row["observed_at"])
        agg["last_seen_at"] = max(agg["last_seen_at"], row["observed_at"])
        agg["groups_mentioned"] = _merge_groups(agg["groups_mentioned"], row["group_name"] or "")

    repaired = 0
    for agg in aggregates.values():
        existing = conn.execute(
            """SELECT id, call_count, first_seen_at, last_seen_at, groups_mentioned
               FROM calls
               WHERE contract_address = ? AND call_date = ?""",
            (agg["contract_address"], agg["call_date"]),
        ).fetchone()

        if not existing:
            conn.execute(
                """INSERT INTO calls
                   (contract_address, ticker, chain, launchpad, call_count,
                    first_seen_at, last_seen_at, groups_mentioned, call_date)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    agg["contract_address"],
                    agg["ticker"],
                    agg["chain"],
                    agg["launchpad"],
                    agg["call_count"],
                    agg["first_seen_at"],
                    agg["last_seen_at"],
                    agg["groups_mentioned"],
                    agg["call_date"],
                ),
            )
            repaired += 1
            continue

        merged_groups = existing["groups_mentioned"] or ""
        for group in (agg["groups_mentioned"] or "").split(","):
            merged_groups = _merge_groups(merged_groups, group)
        new_count = max(existing["call_count"] or 0, agg["call_count"])
        new_first = min(existing["first_seen_at"], agg["first_seen_at"])
        new_last = max(existing["last_seen_at"], agg["last_seen_at"])

        if (
            new_count != existing["call_count"]
            or merged_groups != (existing["groups_mentioned"] or "")
            or new_first != existing["first_seen_at"]
            or new_last != existing["last_seen_at"]
        ):
            conn.execute(
                """UPDATE calls
                   SET call_count = ?, first_seen_at = ?, last_seen_at = ?,
                       groups_mentioned = ?, ticker = COALESCE(ticker, ?),
                       chain = COALESCE(chain, ?), launchpad = COALESCE(launchpad, ?)
                   WHERE id = ?""",
                (
                    new_count,
                    new_first,
                    new_last,
                    merged_groups,
                    agg["ticker"],
                    agg["chain"],
                    agg["launchpad"],
                    existing["id"],
                ),
            )
            repaired += 1

    conn.commit()
    return repaired


def backfill_launchpad(conn: sqlite3.Connection, detector) -> int:
    """Populate launchpad for existing rows. Returns number of rows updated."""
    rows = conn.execute(
        "SELECT id, contract_address FROM calls WHERE launchpad IS NULL"
    ).fetchall()
    n = 0
    for r in rows:
        lp = detector(r["contract_address"])
        if lp:
            conn.execute("UPDATE calls SET launchpad = ? WHERE id = ?", (lp, r["id"]))
            n += 1
    conn.commit()
    return n


def record_new_call(conn: sqlite3.Connection, call: dict) -> str:
    """Record one raw Padre call event and update the daily CA aggregate.

    Returns:
        'NEW'       — first event for this CA today (aggregate INSERT)
        'RECALL'    — additional event for this CA today (aggregate UPDATE count+=1)
        'DUP'       — same raw event already recorded
        'SKIP'      — invalid input
    """
    now = datetime.now().isoformat()
    call_date = datetime.now().strftime("%Y-%m-%d")
    ca = call.get("contract_address")
    if not ca:
        return "SKIP"
    event_key = call.get("event_key") or _fallback_event_key(call, call_date)

    cur = conn.execute(
        """INSERT OR IGNORE INTO call_events
           (event_key, contract_address, ticker, chain, launchpad, group_name,
            call_bucket, row_text, observed_at, call_date)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            event_key,
            ca,
            call.get("ticker"),
            call.get("chain", "Solana"),
            call.get("launchpad"),
            call.get("groups_mentioned"),
            call.get("call_bucket"),
            call.get("normalized_text") or call.get("_text"),
            now,
            call_date,
        ),
    )
    if cur.rowcount == 0:
        conn.commit()
        return "DUP"

    existing = conn.execute(
        "SELECT id, groups_mentioned FROM calls WHERE contract_address = ? AND call_date = ?",
        (ca, call_date),
    ).fetchone()

    if existing:
        merged = _merge_groups(existing["groups_mentioned"] or "", call.get("groups_mentioned") or "")
        conn.execute(
            """UPDATE calls
               SET call_count = call_count + 1, last_seen_at = ?, groups_mentioned = ?
               WHERE contract_address = ? AND call_date = ?""",
            (now, merged, ca, call_date),
        )
        conn.commit()
        return "RECALL"

    conn.execute(
        """INSERT INTO calls
           (contract_address, ticker, chain, launchpad, call_count,
            first_seen_at, last_seen_at, groups_mentioned, call_date)
           VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?)""",
        (ca, call.get("ticker"), call.get("chain", "Solana"), call.get("launchpad"),
         now, now, call.get("groups_mentioned"), call_date),
    )
    conn.commit()
    return "NEW"


def seed_call_event(conn: sqlite3.Connection, call: dict) -> bool:
    """Record a visible raw event without changing the daily aggregate.

    Used on scraper startup so rows already visible before the process begins
    don't all get counted again after a restart/deploy.
    """
    now = datetime.now().isoformat()
    call_date = datetime.now().strftime("%Y-%m-%d")
    ca = call.get("contract_address")
    if not ca:
        return False
    event_key = call.get("event_key") or _fallback_event_key(call, call_date)
    cur = conn.execute(
        """INSERT OR IGNORE INTO call_events
           (event_key, contract_address, ticker, chain, launchpad, group_name,
            call_bucket, row_text, observed_at, call_date)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            event_key,
            ca,
            call.get("ticker"),
            call.get("chain", "Solana"),
            call.get("launchpad"),
            call.get("groups_mentioned"),
            call.get("call_bucket"),
            call.get("normalized_text") or call.get("_text"),
            now,
            call_date,
        ),
    )
    conn.commit()
    return cur.rowcount > 0


def touch_seen(conn: sqlite3.Connection, call: dict) -> None:
    """CA still visible from previous poll — refresh last_seen_at and merge any new group info.

    Does NOT increment call_count.
    """
    now = datetime.now().isoformat()
    call_date = datetime.now().strftime("%Y-%m-%d")
    ca = call.get("contract_address")
    if not ca:
        return

    existing = conn.execute(
        "SELECT groups_mentioned FROM calls WHERE contract_address = ? AND call_date = ?",
        (ca, call_date),
    ).fetchone()
    if not existing:
        return

    merged = _merge_groups(existing["groups_mentioned"] or "", call.get("groups_mentioned") or "")
    conn.execute(
        "UPDATE calls SET last_seen_at = ?, groups_mentioned = ? WHERE contract_address = ? AND call_date = ?",
        (now, merged, ca, call_date),
    )
    conn.commit()


def get_today_cas(conn: sqlite3.Connection) -> set[str]:
    """Set of CAs already recorded today — used to seed in-memory state after restart."""
    call_date = datetime.now().strftime("%Y-%m-%d")
    rows = conn.execute(
        "SELECT contract_address FROM calls WHERE call_date = ?", (call_date,)
    ).fetchall()
    return {r["contract_address"] for r in rows}


def get_today_call_keys(conn: sqlite3.Connection) -> set[str]:
    """Set of raw event keys already recorded today."""
    call_date = datetime.now().strftime("%Y-%m-%d")
    rows = conn.execute(
        "SELECT event_key FROM call_events WHERE call_date = ?", (call_date,)
    ).fetchall()
    return {r["event_key"] for r in rows}


# Legacy alias kept for compatibility; prefer record_new_call / touch_seen.
def upsert_call(conn: sqlite3.Connection, call: dict) -> bool:
    result = record_new_call(conn, call)
    return result == "NEW"


def _merge_groups(existing: str, new: str) -> str:
    parts = [g.strip() for g in existing.split(",") if g.strip()]
    if new.strip() and new.strip() not in parts:
        parts.append(new.strip())
    return ", ".join(parts)


def _fallback_event_key(call: dict, call_date: str) -> str:
    ca = call.get("contract_address") or ""
    group = (call.get("groups_mentioned") or "").strip()
    text = (call.get("normalized_text") or call.get("_text") or "").strip()
    return "|".join([ca, group or "-", call.get("call_bucket") or text or call_date])


def get_calls_for_date(conn: sqlite3.Connection, target_date: date | None = None) -> list[dict]:
    if target_date is None:
        target_date = date.today()
    cursor = conn.execute(
        """SELECT contract_address, ticker, chain, launchpad, call_count,
                  first_seen_at, last_seen_at, groups_mentioned
           FROM calls WHERE call_date = ?
           ORDER BY call_count DESC, first_seen_at""",
        (target_date.strftime("%Y-%m-%d"),),
    )
    return [dict(row) for row in cursor.fetchall()]
