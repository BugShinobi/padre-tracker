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
    conn.execute("CREATE INDEX IF NOT EXISTS idx_calls_date ON calls(call_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_calls_first_seen ON calls(first_seen_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_calls_ca ON calls(contract_address)")
    _migrate_add_launchpad(conn)
    _cleanup_bad_tickers(conn)
    conn.commit()
    return conn


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
    """Record a CA that just appeared on the feed (newly visible this poll).

    Returns:
        'NEW'       — first appearance today (INSERT, count=1)
        'RECALL'    — seen earlier today, left feed, came back (UPDATE count+=1)
        'SKIP'      — invalid input
    """
    now = datetime.now().isoformat()
    call_date = datetime.now().strftime("%Y-%m-%d")
    ca = call.get("contract_address")
    if not ca:
        return "SKIP"

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


# Legacy alias kept for compatibility; prefer record_new_call / touch_seen.
def upsert_call(conn: sqlite3.Connection, call: dict) -> bool:
    result = record_new_call(conn, call)
    return result == "NEW"


def _merge_groups(existing: str, new: str) -> str:
    parts = [g.strip() for g in existing.split(",") if g.strip()]
    if new.strip() and new.strip() not in parts:
        parts.append(new.strip())
    return ", ".join(parts)


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
