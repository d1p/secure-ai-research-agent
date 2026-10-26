"""Small thread-safe TTL/LRU cache (process-local).

The gateway and orchestrator are single-process services; a process-local cache
avoids Redis dependency and cross-service complexity. It is short-lived and
bypassed for ``no-store``/``cache=0``.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Any


class TTLCache:
    def __init__(self, maxsize: int = 128, ttl: float = 300.0) -> None:
        self.maxsize = maxsize
        self.ttl = ttl
        self._lock = threading.Lock()
        self._data: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self.hits = 0
        self.misses = 0

    def get(self, key: str, now: float | None = None) -> Any | None:
        now = time.monotonic() if now is None else now
        with self._lock:
            item = self._data.get(key)
            if item is None:
                self.misses += 1
                return None
            stored, value = item
            if now - stored > self.ttl:
                self._data.pop(key, None)
                self.misses += 1
                return None
            self._data.move_to_end(key)
            self.hits += 1
            return value

    def peek(self, key: str, now: float | None = None) -> Any | None:
        now = time.monotonic() if now is None else now
        with self._lock:
            item = self._data.get(key)
            if item is None:
                return None
            stored, value = item
            if now - stored > self.ttl:
                self._data.pop(key, None)
                return None
            return value

    def set(self, key: str, value: Any, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        with self._lock:
            self._data[key] = (now, value)
            self._data.move_to_end(key)
            while len(self._data) > self.maxsize:
                self._data.popitem(last=False)

    def delete(self, key: str) -> None:
        with self._lock:
            self._data.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()
            self.hits = 0
            self.misses = 0

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)


def env_ttl(name: str, default: float) -> float:
    import os

    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default
