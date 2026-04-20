# Alpha Tracker Call Logger

Scrapes Padre's (trade.padre.gg) Alpha Tracker panel to capture memecoin calls in real-time and stores them locally.

## Project Structure

```
main.py              — Entry point, main polling loop
src/
  scraper.py         — Playwright browser automation + DOM scraping
  db.py              — SQLite schema, insert, dedup, queries
  export_csv.py      — Daily CSV file generation
setup.sh             — One-command install for Ubuntu/Debian
alpha-tracker.service — systemd unit for auto-start
data/
  calls.db           — SQLite database (auto-created)
  csv/               — Daily CSV exports (calls_YYYY-MM-DD.csv)
  session/           — Playwright browser session (cookies/state)
```

## Quick Start

```bash
# On Ubuntu/Debian:
chmod +x setup.sh && ./setup.sh

# First run (headed mode — you need to log in manually):
source .venv/bin/activate
python main.py

# After first login, session is saved. Future runs auto-authenticate.
```

## Key Design Decisions

- **Playwright persistent context**: saves session cookies so you only log in once
- **SQLite dedup**: unique index on (token_name, chain, call_date) prevents duplicates
- **Headed first run**: required because Padre uses wallet-based auth (sign message)
- **30s poll interval**: balances coverage vs. resource usage
- **Daily CSV auto-export**: updates on every new call + full export at midnight
