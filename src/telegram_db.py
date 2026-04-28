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
            amount_usd      REAL,
            market_cap_usd  REAL,
            parse_status    TEXT NOT NULL DEFAULT 'matched',
            UNIQUE (source_channel, msg_id)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_alerts_date ON telegram_alerts(msg_date DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_alerts_ticker ON telegram_alerts(target_ticker)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_alerts_type ON telegram_alerts(alert_type)")
    conn.commit()


def insert_alert(conn: sqlite3.Connection, alert: dict) -> bool:
    cur = conn.execute(
        """INSERT OR IGNORE INTO telegram_alerts
           (source_channel, msg_id, msg_date, msg_text, alert_type,
            actor, target_ticker, amount_usd, market_cap_usd, parse_status)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            alert["source_channel"],
            alert["msg_id"],
            alert["msg_date"],
            alert["msg_text"],
            alert.get("alert_type"),
            alert.get("actor"),
            alert.get("target_ticker"),
            alert.get("amount_usd"),
            alert.get("market_cap_usd"),
            alert.get("parse_status", "matched"),
        ),
    )
    conn.commit()
    return cur.rowcount > 0
