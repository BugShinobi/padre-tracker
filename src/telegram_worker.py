"""Telegram ingestion worker — reads @whalewatchsolana via MTProto userbot.

Run modes:
  python -m src.telegram_worker                   # daemon, live tail
  python -m src.telegram_worker --backfill 100    # fetch last 100 then exit

Bot API cannot read public channels we are not admin in, so we use a userbot
session (see telegram_setup.py for one-time auth).
"""

import argparse
import asyncio
import logging
import os
import re
import signal
import sqlite3
import sys
from pathlib import Path

from dotenv import load_dotenv

from src import telegram_parser
from src.telegram_db import init_telegram_table, insert_alert

load_dotenv()

DB_PATH = os.getenv("DB_PATH", "./data/calls.db")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
TELEGRAM_API_ID = os.getenv("TELEGRAM_API_ID")
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH")
TELEGRAM_SESSION_PATH = os.getenv("TELEGRAM_SESSION_PATH", "./data/telegram.session")
SOURCE_CHANNEL = os.getenv("TELEGRAM_CHANNEL", "whalewatchsolana")

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("telegram-worker")

_stop = asyncio.Event()
SOLANA_CA_RE = re.compile(r"/solana/([1-9A-HJ-NP-Za-km-z]{32,44})")


def _open_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _bootstrap():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = _open_conn()
    try:
        init_telegram_table(conn)
    finally:
        conn.close()


def _extract_urls(msg) -> list[str]:
    urls: list[str] = []
    for row in getattr(msg, "buttons", None) or []:
        buttons = row if isinstance(row, list) else [row]
        for btn in buttons:
            url = getattr(btn, "url", None)
            if url:
                urls.append(url)

    for entity in getattr(msg, "entities", None) or []:
        url = getattr(entity, "url", None)
        if url:
            urls.append(url)
    return urls


def _extract_target_ca(urls: list[str]) -> tuple[str | None, str | None]:
    for url in urls:
        m = SOLANA_CA_RE.search(url)
        if m:
            return m.group(1), url
    return None, urls[0] if urls else None


def _ingest_message(conn: sqlite3.Connection, msg) -> str:
    text = msg.message or ""
    parsed = telegram_parser.parse(text)
    target_ca, link_url = _extract_target_ca(_extract_urls(msg))
    alert = {
        "source_channel": SOURCE_CHANNEL,
        "msg_id": msg.id,
        "msg_date": msg.date.isoformat() if msg.date else "",
        "msg_text": text,
        "target_ca": target_ca,
        "link_url": link_url,
        **parsed,
    }
    inserted = insert_alert(conn, alert)
    return "INSERT" if inserted else "DUP"


async def run_backfill(client, n: int):
    conn = _open_conn()
    try:
        ins = dup = unmatched = 0
        async for msg in client.iter_messages(SOURCE_CHANNEL, limit=n):
            res = _ingest_message(conn, msg)
            if res == "INSERT":
                ins += 1
            else:
                dup += 1
            if telegram_parser.parse(msg.message or "").get("parse_status") == "unmatched":
                unmatched += 1
        log.info(
            "backfill done channel=%s inserted=%d duplicates=%d unmatched=%d",
            SOURCE_CHANNEL, ins, dup, unmatched,
        )
    finally:
        conn.close()


async def run_daemon(client):
    from telethon import events

    log.info("daemon starting channel=%s", SOURCE_CHANNEL)

    @client.on(events.NewMessage(chats=SOURCE_CHANNEL))
    async def handler(event):
        try:
            conn = _open_conn()
            try:
                res = _ingest_message(conn, event.message)
            finally:
                conn.close()
            preview = (event.message.message or "").replace("\n", " ")[:80]
            log.info("msg id=%s result=%s text=%r", event.message.id, res, preview)
        except Exception as e:
            log.error("ingest failed: %s", e, exc_info=True)

    await _stop.wait()
    log.info("daemon stopping")


async def main_async(args):
    if not TELEGRAM_API_ID or not TELEGRAM_API_HASH:
        log.error("TELEGRAM_API_ID and TELEGRAM_API_HASH required in .env")
        sys.exit(1)

    try:
        from telethon import TelegramClient
    except ImportError:
        log.error("telethon not installed: pip install telethon")
        sys.exit(1)

    _bootstrap()

    session_name = (
        TELEGRAM_SESSION_PATH[:-8]
        if TELEGRAM_SESSION_PATH.endswith(".session")
        else TELEGRAM_SESSION_PATH
    )
    client = TelegramClient(session_name, int(TELEGRAM_API_ID), TELEGRAM_API_HASH)
    await client.connect()

    if not await client.is_user_authorized():
        log.error("session not authorized — run: python -m src.telegram_setup")
        await client.disconnect()
        sys.exit(1)

    try:
        if args.backfill > 0:
            await run_backfill(client, args.backfill)
        else:
            await run_daemon(client)
    finally:
        await client.disconnect()


def main():
    p = argparse.ArgumentParser(description="Padre-tracker Telegram ingestion worker")
    p.add_argument("--backfill", type=int, default=0, help="Fetch last N messages and exit")
    args = p.parse_args()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def _shutdown():
        log.info("shutdown signal received")
        _stop.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _shutdown)
        except NotImplementedError:
            signal.signal(sig, lambda *_: _shutdown())

    try:
        loop.run_until_complete(main_async(args))
    finally:
        loop.close()


if __name__ == "__main__":
    main()
