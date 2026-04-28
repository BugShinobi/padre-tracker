"""Parse @whalewatchsolana messages.

Three known patterns:
  whale:        A $TROLL whale just bought $4.35K of $ZEREBRO at $15.4M MC 🐳
  kol:          KOL MarcellxMarcell just bought $5.99K of $Buttcoin at $9.1M MC 🧠
  kol_newpair:  🌱 New Pair: KOL bandeez just bought $3.01K of $LIFE at $169.35K MC 🧠

Anything else → parse_status='unmatched', raw text retained for later inspection.
"""

import re

_MONEY = r"\$([\d.,]+)\s*([KMBkmb]?)"
_TICKER = r"\$([A-Za-z][A-Za-z0-9]{0,30})"

WHALE_RE = re.compile(
    rf"A\s+{_TICKER}\s+whale\s+just\s+bought\s+{_MONEY}\s+of\s+{_TICKER}\s+at\s+{_MONEY}\s+MC",
    re.IGNORECASE,
)

KOL_NEWPAIR_RE = re.compile(
    rf"🌱\s*New\s+Pair:\s*KOL\s+(.+?)\s+just\s+bought\s+{_MONEY}\s+of\s+{_TICKER}\s+at\s+{_MONEY}\s+MC",
    re.IGNORECASE,
)

KOL_RE = re.compile(
    rf"^KOL\s+(.+?)\s+just\s+bought\s+{_MONEY}\s+of\s+{_TICKER}\s+at\s+{_MONEY}\s+MC",
    re.IGNORECASE,
)


def _parse_money(num: str | None, suffix: str | None) -> float | None:
    if not num:
        return None
    try:
        v = float(num.replace(",", ""))
    except ValueError:
        return None
    s = (suffix or "").upper()
    mult = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}.get(s, 1)
    return v * mult


def parse(text: str) -> dict:
    if not text:
        return {"parse_status": "unmatched"}

    m = KOL_NEWPAIR_RE.search(text)
    if m:
        actor, amt_n, amt_s, ticker, mc_n, mc_s = m.groups()
        return {
            "alert_type": "kol_newpair",
            "actor": actor.strip(),
            "target_ticker": ticker,
            "amount_usd": _parse_money(amt_n, amt_s),
            "market_cap_usd": _parse_money(mc_n, mc_s),
            "parse_status": "matched",
        }

    m = WHALE_RE.search(text)
    if m:
        src_t, amt_n, amt_s, dst_t, mc_n, mc_s = m.groups()
        return {
            "alert_type": "whale",
            "actor": f"{src_t} whale",
            "target_ticker": dst_t,
            "amount_usd": _parse_money(amt_n, amt_s),
            "market_cap_usd": _parse_money(mc_n, mc_s),
            "parse_status": "matched",
        }

    m = KOL_RE.search(text)
    if m:
        actor, amt_n, amt_s, ticker, mc_n, mc_s = m.groups()
        return {
            "alert_type": "kol",
            "actor": actor.strip(),
            "target_ticker": ticker,
            "amount_usd": _parse_money(amt_n, amt_s),
            "market_cap_usd": _parse_money(mc_n, mc_s),
            "parse_status": "matched",
        }

    return {"parse_status": "unmatched"}


if __name__ == "__main__":
    samples = [
        "A $TROLL whale just bought $4.35K of $ZEREBRO at $15.4M MC 🐳",
        "KOL MarcellxMarcell just bought $5.99K of $Buttcoin at $9.1M MC 🧠",
        "🌱 New Pair: KOL bandeez just bought $3.01K of $LIFE at $169.35K MC 🧠",
        "Random message that should not parse",
    ]
    for s in samples:
        print(s)
        print(" →", parse(s))
        print()
