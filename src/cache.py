"""Thread-safe TTL memoization for dashboard read paths.

Aggregations served to the browser rerun on every request by default.
Wrap them with @ttl_cache(seconds) so concurrent polls and auto-refreshes
reuse the last result within the TTL window. The scraper (writer) must
never touch this cache — staleness up to `ttl_seconds` is acceptable for
a dashboard that auto-refreshes every 60s.

sqlite3.Connection args are stripped from the cache key (unhashable, and
irrelevant to the cached value's identity).
"""

import sqlite3
import threading
import time
from functools import wraps


def ttl_cache(ttl_seconds: float):
    def deco(fn):
        store: dict = {}
        lock = threading.Lock()

        @wraps(fn)
        def wrapper(*args, **kwargs):
            key_args = tuple(a for a in args if not isinstance(a, sqlite3.Connection))
            key = (key_args, tuple(sorted(kwargs.items())))
            now = time.monotonic()
            with lock:
                hit = store.get(key)
                if hit and hit[1] > now:
                    return hit[0]
            value = fn(*args, **kwargs)
            with lock:
                store[key] = (value, now + ttl_seconds)
                if len(store) > 64:
                    for k, (_, exp) in list(store.items()):
                        if exp <= now:
                            store.pop(k, None)
            return value

        wrapper.cache_clear = lambda: store.clear()
        return wrapper

    return deco
