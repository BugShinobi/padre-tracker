"""Daily CSV export from SQLite."""

import csv
import sqlite3
from datetime import date
from pathlib import Path

from .db import get_calls_for_date

CSV_HEADERS = [
    "contract_address",
    "ticker",
    "chain",
    "launchpad",
    "call_count",
    "first_seen_at",
    "last_seen_at",
    "groups_mentioned",
]


def export_daily_csv(conn: sqlite3.Connection, csv_dir: str, target_date: date | None = None) -> str | None:
    if target_date is None:
        target_date = date.today()

    calls = get_calls_for_date(conn, target_date)
    if not calls:
        return None

    Path(csv_dir).mkdir(parents=True, exist_ok=True)
    filepath = Path(csv_dir) / f"calls_{target_date.strftime('%Y-%m-%d')}.csv"

    with open(filepath, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(calls)

    return str(filepath)
