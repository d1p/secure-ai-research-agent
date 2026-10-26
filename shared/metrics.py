"""Tiny thread-safe counters/summaries with Prometheus text exposition.

No third-party metrics dependency: the loader runs in small services and only
needs a few low-cardinality series.
"""

from __future__ import annotations

import threading
from collections import defaultdict

_LOCK = threading.Lock()
_COUNTERS: dict[tuple[str, tuple[tuple[str, str], ...]], float] = defaultdict(float)
_SUMS: dict[tuple[str, tuple[tuple[str, str], ...]], float] = defaultdict(float)
_COUNTS: dict[tuple[str, tuple[tuple[str, str], ...]], int] = defaultdict(int)


def _key(
    name: str, labels: dict[str, str] | None
) -> tuple[str, tuple[tuple[str, str], ...]]:
    items = tuple(sorted((str(k), str(v)) for k, v in (labels or {}).items()))
    return name, items


def inc(name: str, labels: dict[str, str] | None = None, value: float = 1.0) -> None:
    with _LOCK:
        _COUNTERS[_key(name, labels)] += value


def observe(name: str, value: float, labels: dict[str, str] | None = None) -> None:
    with _LOCK:
        _SUMS[_key(name, labels)] += value
        _COUNTS[_key(name, labels)] += 1


def reset() -> None:
    """Test helper: clear all series."""
    with _LOCK:
        _COUNTERS.clear()
        _SUMS.clear()
        _COUNTS.clear()


def _labels(items: tuple[tuple[str, str], ...]) -> str:
    if not items:
        return ""
    escaped = [
        f'{key}="{value.replace(chr(92), chr(92) * 2).replace(chr(34), chr(92) + chr(34))}"'
        for key, value in items
    ]
    return "{" + ",".join(escaped) + "}"


def render() -> str:
    """Render Prometheus text exposition format (version 0.0.4)."""
    with _LOCK:
        counters = dict(_COUNTERS)
        sums = dict(_SUMS)
        counts = dict(_COUNTS)
    lines = []
    for (name, labels), value in sorted(counters.items()):
        lines.append(f"{name}{_labels(labels)} {value:g}")
    for (name, labels), value in sorted(sums.items()):
        lines.append(f"{name}_sum{_labels(labels)} {value:g}")
        lines.append(f"{name}_count{_labels(labels)} {counts[(name, labels)]}")
    return "\n".join(lines) + ("\n" if lines else "")
