"""Playwright scraper for Padre's Alpha Tracker panel.

CA extraction: scan all <a href> links for known token explorer URL patterns
and pull the contract address directly from the URL — no fragile CSS selectors.
"""

import logging
import re
from pathlib import Path
from playwright.sync_api import sync_playwright, Page, BrowserContext

log = logging.getLogger(__name__)

# Known Solana program addresses / always-in-view tokens — never store.
_BLACKLIST_CA = {
    "pumpCmXqMfrsAkQ5r49WcJnRayYRqmXz6ae8H7H9Dfn",  # pump.fun program
    "So11111111111111111111111111111111111111112",  # wrapped SOL
    "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",  # SPL token program
    "BofA2ViUSudPBTUms2KRuG6AHNeMawjNfwqTJDgx5BKW",  # PUMP token — default page in Padre terminal
}

# Launchpad detection — match against CA suffix (case-sensitive where launchpad vanity is case-sensitive).
# Order matters: longer / more specific first.
_LAUNCHPAD_SUFFIXES = [
    ("pump", "pump.fun"),
    ("BAGS", "bags.fm"),
    ("moon", "moonshot"),
    ("bonk", "bonk.fun"),
    ("brrr", "printr"),
]


def detect_launchpad(ca: str) -> str | None:
    for suffix, name in _LAUNCHPAD_SUFFIXES:
        if ca.endswith(suffix):
            return name
    return None


# JavaScript injected to extract (ca, ticker, group) from every link in the page
_JS_EXTRACT = """
() => {
    const patterns = [
        /pump\\.fun\\/coin\\/([1-9A-HJ-NP-Za-km-z]{32,44})/,
        /dexscreener\\.com\\/solana\\/([1-9A-HJ-NP-Za-km-z]{32,44})/,
        /birdeye\\.so\\/token\\/([1-9A-HJ-NP-Za-km-z]{32,44})/,
        /solscan\\.io\\/token\\/([1-9A-HJ-NP-Za-km-z]{32,44})/,
        /raydium\\.io.*outputCurrency=([1-9A-HJ-NP-Za-km-z]{32,44})/,
        /jup\\.ag\\/swap\\/[^-]+-([1-9A-HJ-NP-Za-km-z]{32,44})/,
        /[?&\\/](?:mint|token|ca|address)=([1-9A-HJ-NP-Za-km-z]{32,44})/,
    ];

    // Sponsored/ad markers — any ancestor or sibling text matching = skip
    const AD_RE = /\\bDEX\\s*Paid\\b|\\bX\\s*Motions?\\b|\\bSponsored\\b|\\bPromoted\\b|\\bBoosted\\b/i;

    function findAdMarker(startEl) {
        let cur = startEl;
        while (cur && cur !== document.body) {
            // Check immediate children for badge-like short text (no sub-links)
            for (const child of (cur.children || [])) {
                const ct = (child.innerText || '').trim();
                if (ct.length > 0 && ct.length < 40 && AD_RE.test(ct)) return ct;
            }
            // Check this node's own direct text nodes
            const ownText = Array.from(cur.childNodes)
                .filter(n => n.nodeType === 3)
                .map(n => n.textContent).join(' ').trim();
            if (ownText.length < 40 && AD_RE.test(ownText)) return ownText;
            cur = cur.parentElement;
        }
        return null;
    }

    const results = [];
    const seen = new Set();

    for (const link of document.querySelectorAll('a[href]')) {
        const href = link.href || '';
        let ca = null;
        for (const pat of patterns) {
            const m = href.match(pat);
            if (m) { ca = m[1]; break; }
        }
        if (!ca || seen.has(ca)) continue;
        seen.add(ca);

        // Walk up DOM to find a container with readable text
        let el = link;
        let text = '';
        for (let i = 0; i < 8; i++) {
            el = el.parentElement;
            if (!el) break;
            const t = (el.innerText || '').trim();
            if (t.length > 3 && t.length < 600) { text = t; break; }
        }

        // Detect ad/sponsored — check text first, then full ancestor chain
        let adMarker = null;
        const quickMatch = text.match(AD_RE);
        if (quickMatch) {
            adMarker = quickMatch[0];
        } else {
            adMarker = findAdMarker(link);
        }

        // Clean leading row-number / time noise like "23 ", "5m ago ", etc.
        let cleaned = text.replace(/^[\\d\\s:.,]+(?:s|m|h|d|sec|min|hr|ago)?\\s*/i, '');

        // Group: "mentioned in <Group>" / "in <Group>" (capital start, 2-30 chars)
        let group = '';
        const gm1 = text.match(/mentioned in\\s+([A-Za-z][\\w\\s.-]{1,30}?)(?:\\s+\\d|\\n|$)/);
        const gm2 = text.match(/\\bin\\s+([A-Z][\\w\\s.-]{1,30}?)(?:\\s+\\d|\\n|$)/);
        if (gm1) group = gm1[1].trim();
        else if (gm2) group = gm2[1].trim();

        // Ticker: 2-12 chars starting with letter/$, not pure digits.
        const tm = cleaned.match(/^\\$?([A-Za-z][A-Z0-9a-z]{1,11})\\b/);
        let ticker = tm ? tm[1].toUpperCase() : '';
        if (/^\\d+$/.test(ticker)) ticker = '';

        results.push({ ca, ticker, group, adMarker, _text: text.slice(0, 160) });
    }
    return results;
}
"""


def launch_browser(session_dir: str) -> tuple:
    Path(session_dir).mkdir(parents=True, exist_ok=True)
    pw = sync_playwright().start()
    context = pw.chromium.launch_persistent_context(
        user_data_dir=session_dir,
        headless=False,
        args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        viewport={"width": 1400, "height": 900},
        ignore_default_args=["--enable-automation"],
    )
    return pw, context


def get_live_page(context: BrowserContext) -> Page:
    """Always return a FRESH new page and close any restored ones.

    Reusing a persistent-context restored page caused TargetClosedError: Padre's SPA
    seems to tear down the original frame. A brand-new page avoids that race.
    """
    restored = list(context.pages)
    log.info("Context had %d page(s) on init: %s",
             len(restored), [p.url for p in restored if not p.is_closed()])

    page = context.new_page()
    _attach_page_diagnostics(page)

    for p in restored:
        if p is page or p.is_closed():
            continue
        try:
            log.info("Closing restored tab: %s", p.url)
            p.close()
        except Exception as e:
            log.warning("Could not close restored tab: %s", e)
    return page


def _attach_page_diagnostics(page: Page) -> None:
    """Log every signal that could explain why page.evaluate ends up on a dead target."""
    url = lambda: getattr(page, "url", "?")
    try:
        page.on("close", lambda _p: log.warning("page.on(close): url=%s", url()))
    except Exception:
        pass
    try:
        page.on("crash", lambda _p: log.error("page.on(crash): url=%s", url()))
    except Exception:
        pass
    try:
        page.on("framenavigated", lambda fr: log.info("framenavigated: %s", fr.url))
    except Exception:
        pass


def register_page_listeners(context: BrowserContext) -> None:
    """Log context-level events (new/closed pages, context close)."""
    def on_page(p):
        log.warning("context.on(page): NEW page %s", getattr(p, "url", "?"))
        _attach_page_diagnostics(p)
    def on_close():
        log.error("context.on(close): browser context died")
    try:
        context.on("page", on_page)
    except Exception:
        pass
    try:
        context.on("close", on_close)
    except Exception:
        pass


def navigate_to_alpha(page: Page, padre_url: str) -> None:
    """Ensure we're on Padre. Alpha Tracker is a persistent left panel — no click needed.

    Only navigates if the current URL is NOT already on trade.padre.gg (e.g. first launch).
    """
    try:
        current = page.url
    except Exception:
        current = ""

    if "trade.padre.gg" not in current:
        log.info("Navigating to %s (was on %s)", padre_url, current or "<blank>")
        page.goto(padre_url, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(5000)
    else:
        log.info("Already on Padre (%s), skipping navigation", current)

    if not page.is_closed():
        log.info("Ready. url=%s, title=%r", page.url, page.title())


def dump_page_html(page: Page, out_path: str) -> None:
    """Save full page HTML for selector inspection (--dump mode)."""
    html = page.content()
    Path(out_path).write_text(html, encoding="utf-8")
    log.info("Page HTML dumped to %s (%d bytes)", out_path, len(html))


def scrape_alpha_tracker(
    page: Page,
    ignore_launchpads: set[str] | None = None,
    require_quality: bool = True,
) -> list[dict]:
    """Return list of dicts with keys: contract_address, ticker, chain, launchpad, groups_mentioned.

    Args:
        ignore_launchpads: skip CAs whose detected launchpad is in this set (e.g. {"pump.fun"})
        require_quality: drop CAs with no ticker AND no group (can't identify what token it is)
    """
    ignore_launchpads = ignore_launchpads or set()

    if page.is_closed():
        raise RuntimeError("page is closed — caller must recover")

    try:
        current_url = page.url
    except Exception:
        current_url = "<unknown>"
    log.debug("Scraping page at url=%s", current_url)

    raw = page.evaluate(_JS_EXTRACT)

    calls = []
    skipped_lp = 0
    skipped_quality = 0
    skipped_ad = 0
    for i, item in enumerate(raw):
        ca = (item.get("ca") or "").strip()
        if not ca or ca in _BLACKLIST_CA:
            continue

        ticker = (item.get("ticker") or "").strip()
        if ticker and (ticker.isdigit() or len(ticker) < 2):
            ticker = ""
        group = (item.get("group") or "").strip()
        launchpad = detect_launchpad(ca)
        ad_marker = item.get("adMarker")

        # Skip known ad/sponsored events (DEX Paid, X Motions, Sponsored, etc.)
        if ad_marker:
            skipped_ad += 1
            log.info("SKIP_AD  [%d] %s marker=%r %r", i, ca[:8], ad_marker, item.get("_text", "")[:80])
            continue

        # No group = always skip — Padre calls always have group attribution; no group = ad/noise
        if not group:
            skipped_ad += 1
            log.info("SKIP_AD  [%d] %s (no group) %r", i, ca[:8], item.get("_text", "")[:80])
            continue

        if launchpad and launchpad in ignore_launchpads:
            skipped_lp += 1
            if i < 5:
                log.info("SKIP_LP  [%d] %s (lp=%s) %r", i, ca[:8], launchpad, item.get("_text", "")[:80])
            continue
        if require_quality and not ticker and not group:
            skipped_quality += 1
            if i < 5:
                log.info("SKIP_Q   [%d] %s (no ticker/group) %r", i, ca[:8], item.get("_text", "")[:80])
            continue

        if i < 5:
            log.info("KEEP     [%d] %s ticker=%s group=%s lp=%s", i, ca[:8], ticker or "-", group or "-", launchpad or "-")

        calls.append({
            "contract_address": ca,
            "ticker": ticker or None,
            "chain": "Solana",
            "launchpad": launchpad,
            "groups_mentioned": group or None,
        })

    if not calls and not skipped_lp and not skipped_quality and not skipped_ad:
        log.warning("No calls found — page may need login or Padre changed its DOM. Run with --dump to inspect.")

    log.info(
        "Scraped: %d kept, %d skipped (lp=%d, quality=%d, ad=%d)",
        len(calls), skipped_lp + skipped_quality + skipped_ad,
        skipped_lp, skipped_quality, skipped_ad,
    )
    return calls
