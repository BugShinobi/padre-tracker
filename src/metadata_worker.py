"""Background metadata refresh worker (Helius DAS).

Mirror of gmgn_worker: single daemon thread draining a queue of CAs,
deduped against an in-flight set. Keeps Helius calls off the request path.

Started from dashboard.py at boot with api_key + db_path. No-ops if
api_key is missing (Helius key not configured).
"""

import logging
import queue
import threading
import time

from metadata import RATE_SLEEP, fetch_and_cache_one

log = logging.getLogger(__name__)

_queue: "queue.Queue[str]" = queue.Queue()
_enqueued: set[str] = set()
_lock = threading.Lock()
_started = False
_db_path: str | None = None
_api_key: str | None = None


def start(db_path: str, api_key: str | None) -> None:
    """Spawn the worker thread (idempotent). No-op if api_key missing."""
    global _started, _db_path, _api_key
    if not api_key:
        log.info("Metadata worker disabled (no HELIUS_API_KEY)")
        return
    with _lock:
        if _started:
            return
        _db_path = db_path
        _api_key = api_key
        _started = True
    t = threading.Thread(target=_run, name="metadata-worker", daemon=True)
    t.start()
    log.info("Metadata worker started")


def enqueue_refresh(cas: list[str]) -> int:
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
        log.debug("Metadata worker: enqueued %d CA(s), queue=%d", added, _queue.qsize())
    return added


def _run() -> None:
    assert _db_path is not None and _api_key is not None
    while True:
        ca = _queue.get()
        try:
            fetch_and_cache_one(_db_path, _api_key, ca)
        except Exception as e:
            log.warning("Metadata worker: fetch failed for %s: %s", ca[:8], e)
        finally:
            with _lock:
                _enqueued.discard(ca)
            _queue.task_done()
        time.sleep(RATE_SLEEP)
