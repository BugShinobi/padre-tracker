"""SQLite layer for Telegram-channel alerts (whale watch + future channels).

Schema is multi-channel ready: `source_channel` lets us add Bonkbot, Birdeye, etc.
later without touching the table. Dedup is on (source_channel, msg_id) so re-runs
of backfill are idempotent.
"""

import sqlite3


def init_telegram_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS telegram_alerts (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            source_channel  TEXT NOT NULL,
            msg_id          INTEGER NOT NULL,
            msg_date        TEXT NOT NULL,
            msg_text        TEXT NOT NULL,
            alert_type      TEXT,
            actor           TEXT,
            target_ticker   TEXT,
            target_ca       TEXT,
            link_url        TEXT,
            amount_usd      REAL,
            market_cap_usd  REAL,
            parse_status    TEXT NOT NULL DEFAULT 'matched',
            UNIQUE (source_channel, msg_id)
        )
        """
    )
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(telegram_alerts)").fetchall()}
    if "target_ca" not in cols:
        conn.execute("ALTER TABLE telegram_alerts ADD COLUMN target_ca TEXT")
    if "link_url" not in cols:
        conn.execute("ALTER TABLE telegram_alerts ADD COLUMN link_url TEXT")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_alerts_date ON telegram_alerts(msg_date DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_alerts_ticker ON telegram_alerts(target_ticker)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_alerts_ca ON telegram_alerts(target_ca)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_alerts_type ON telegram_alerts(alert_type)")
    conn.commit()


def insert_alert(conn: sqlite3.Connection, alert: dict) -> bool:
    cur = conn.execute(
        """INSERT OR IGNORE INTO telegram_alerts
           (source_channel, msg_id, msg_date, msg_text, alert_type,
            actor, target_ticker, target_ca, link_url, amount_usd,
            market_cap_usd, parse_status)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            alert["source_channel"],
            alert["msg_id"],
            alert["msg_date"],
            alert["msg_text"],
            alert.get("alert_type"),
            alert.get("actor"),
            alert.get("target_ticker"),
            alert.get("target_ca"),
            alert.get("link_url"),
            alert.get("amount_usd"),
            alert.get("market_cap_usd"),
            alert.get("parse_status", "matched"),
        ),
    )
    inserted = cur.rowcount > 0
    if not inserted and (alert.get("target_ca") or alert.get("link_url")):
        conn.execute(
            """UPDATE telegram_alerts
               SET target_ca = COALESCE(target_ca, ?),
                   link_url = COALESCE(link_url, ?)
               WHERE source_channel = ? AND msg_id = ?""",
            (
                alert.get("target_ca"),
                alert.get("link_url"),
                alert["source_channel"],
                alert["msg_id"],
            ),
        )
    conn.commit()
    return inserted
