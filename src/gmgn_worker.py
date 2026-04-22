"""Background GMGN refresh worker.

Keeps GMGN HTTP calls out of the dashboard request path. A single daemon
thread drains a queue of CAs, fetches each via gmgn.fetch_and_cache_one,
and throttles with RATE_SLEEP between calls to respect GMGN rate limits.

Dashboard flow:
    cached, stale = get_gmgn_cached(conn, cas)
    enqueue_refresh(stale)     # non-blocking
    # render with whatever is in `cached` — stale rows show last-known values

The queue deduplicates on enqueue (same CA enqueued twice within the
in-flight window is coalesced). Worker survives individual fetch failures
and never raises to the caller.
"""

import logging
import queue
import threading
import time

from gmgn import RATE_SLEEP, fetch_and_cache_one

log = logging.getLogger(__name__)

_queue: "queue.Queue[str]" = queue.Queue()
_enqueued: set[str] = set()
_lock = threading.Lock()
_started = False
_db_path: str | None = None


def start(db_path: str) -> None:
    """Spawn the worker thread (idempotent). Safe to call from multiple gunicorn workers."""
    global _started, _db_path
    with _lock:
        if _started:
            return
        _db_path = db_path
        _started = True
    t = threading.Thread(target=_run, name="gmgn-worker", daemon=True)
    t.start()
    log.info("GMGN worker started")


def enqueue_refresh(cas: list[str]) -> int:
    """Queue CAs for background refresh. De-duped against in-flight set.

    Returns number of CAs actually enqueued (excludes dupes).
    """
    if not _started or not cas:
        return 0
    added = 0
    with _lock:
        for ca in cas:
            if ca not in _enqueued:
                _enqueued.add(ca)
                _queue.put(ca)
                added += 1
    if added:
        log.debug("GMGN worker: enqueued %d CA(s), queue=%d", added, _queue.qsize())
    return added


def _run() -> None:
    assert _db_path is not None
    while True:
        ca = _queue.get()
        try:
            fetch_and_cache_one(_db_path, ca)
        except Exception as e:
            log.warning("GMGN worker: fetch failed for %s: %s", ca[:8], e)
        finally:
            with _lock:
                _enqueued.discard(ca)
            _queue.task_done()
        time.sleep(RATE_SLEEP)
