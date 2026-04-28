"""One-shot interactive Telegram session creator.

Run once on the server to authenticate the userbot:
    python -m src.telegram_setup

Asks for phone, SMS code, optional 2FA password. Saves session at TELEGRAM_SESSION_PATH.
"""

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def main():
    api_id = os.getenv("TELEGRAM_API_ID")
    api_hash = os.getenv("TELEGRAM_API_HASH")
    session_path = os.getenv("TELEGRAM_SESSION_PATH", "./data/telegram.session")

    if not api_id or not api_hash:
        print("ERROR: TELEGRAM_API_ID and TELEGRAM_API_HASH must be set in .env", file=sys.stderr)
        print("Get them from https://my.telegram.org → API Development Tools", file=sys.stderr)
        sys.exit(1)

    Path(session_path).parent.mkdir(parents=True, exist_ok=True)

    try:
        from telethon import TelegramClient
    except ImportError:
        print("ERROR: telethon not installed. Run: pip install telethon", file=sys.stderr)
        sys.exit(1)

    session_name = session_path[:-8] if session_path.endswith(".session") else session_path

    async def run():
        client = TelegramClient(session_name, int(api_id), api_hash)
        await client.start()
        me = await client.get_me()
        username = me.username or me.first_name or "unknown"
        print(f"✓ Authenticated as {username} (id {me.id})")
        print(f"✓ Session saved at {session_path}")
        await client.disconnect()

    asyncio.run(run())


if __name__ == "__main__":
    main()
