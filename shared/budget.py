"""Cumulative per-run tool-output budget.

Approximates a sub-agent run with a run id (or an agent-scoped TTL window when
Open WebUI does not provide one). The cap forces a summarize step instead of
letting a model grow context without bound.
"""

from __future__ import annotations

import os
import threading
import time

DEFAULT_MAX_CHARS = int(os.environ.get("SUBAGENT_OUTPUT_BUDGET_CHARS", "150000"))
DEFAULT_TTL = float(os.environ.get("SUBAGENT_OUTPUT_BUDGET_TTL", "900"))


class OutputBudget:
    def __init__(
        self, max_chars: int = DEFAULT_MAX_CHARS, ttl: float = DEFAULT_TTL
    ) -> None:
        self.max_chars = max_chars
        self.ttl = ttl
        self._lock = threading.Lock()
        self._runs: dict[str, tuple[float, int]] = {}

    def _prune(self, now: float) -> None:
        expired = [
            key for key, (start, _) in self._runs.items() if now - start > self.ttl
        ]
        for key in expired:
            self._runs.pop(key, None)

    def consume(
        self, run_id: str, chars: int, now: float | None = None
    ) -> tuple[bool, int]:
        """Return (allowed, used_after). Exceeding the cap does not add chars."""
        now = time.monotonic() if now is None else now
        with self._lock:
            self._prune(now)
            start, used = self._runs.get(run_id, (now, 0))
            if self.max_chars <= 0 or used + chars <= self.max_chars:
                used += chars
                self._runs[run_id] = (start, used)
                return True, used
            self._runs[run_id] = (start, used)
            return False, used

    def used(self, run_id: str, now: float | None = None) -> int:
        now = time.monotonic() if now is None else now
        with self._lock:
            item = self._runs.get(run_id)
            if not item or now - item[0] > self.ttl:
                self._runs.pop(run_id, None)
                return 0
            return item[1]

    def clear(self) -> None:
        with self._lock:
            self._runs.clear()
