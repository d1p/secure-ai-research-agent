"""Structured loader logging, metrics and optional OTel span attributes."""

from __future__ import annotations

import json
import logging
import os
from urllib.parse import urlsplit

from shared import metrics
from shared.tokens import count_tokens, tokenizer_name

LOGGER = logging.getLogger("web_loader")
ALERT_CHARS = int(os.environ.get("READER_EMPTY_ALERT_CHARS", "200000"))


def host_from_url(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


def _span_attrs(**attrs) -> None:
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        if span is not None and span.is_recording():
            for key, value in attrs.items():
                if value is not None:
                    span.set_attribute(f"web_loader.{key}", value)
    except Exception:
        LOGGER.debug("otel span attribute update failed", exc_info=True)


def record_load(
    *,
    service: str,
    reason: str,
    method: str = "",
    page_type: str = "unknown",
    chars_in: int = 0,
    chars_out: int = 0,
    tokens_in: int | None = None,
    tokens_out: int | None = None,
    truncated: bool = False,
    source_count: int = 0,
    cache_hit: bool = False,
    duration_ms: float = 0.0,
    host: str = "",
    error_class: str = "",
) -> None:
    """Increment counters, emit one JSON log line and set span attributes."""
    tokens_in = count_tokens("") if tokens_in is None else tokens_in
    tokens_out = count_tokens("") if tokens_out is None else tokens_out
    metrics.inc(
        "web_loader_loads_total",
        {
            "service": service,
            "reason": reason,
            "page_type": page_type,
            "method": method or "none",
        },
    )
    metrics.observe(
        "web_loader_tokens", tokens_in, {"service": service, "direction": "in"}
    )
    metrics.observe(
        "web_loader_tokens", tokens_out, {"service": service, "direction": "out"}
    )
    metrics.observe("web_loader_chars", chars_in, {"service": service, "kind": "in"})
    metrics.observe("web_loader_chars", chars_out, {"service": service, "kind": "out"})
    if reason == "fetch_failed":
        metrics.inc(
            "web_loader_fetch_failures_total",
            {"service": service, "error_class": error_class or "unknown"},
        )
    if reason == "cache_hit":
        metrics.inc(
            "web_loader_cache_lookups_total", {"service": service, "result": "hit"}
        )
    _span_attrs(
        reason=reason,
        page_type=page_type,
        method=method,
        chars_out=chars_out,
        tokens_out=tokens_out,
        truncated=truncated,
        cache_hit=cache_hit,
    )
    LOGGER.info(
        json.dumps(
            {
                "event": "web_loader_load",
                "service": service,
                "reason": reason,
                "method": method,
                "page_type": page_type,
                "chars_in": chars_in,
                "chars_out": chars_out,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "tokenizer": tokenizer_name(),
                "truncated": truncated,
                "source_count": source_count,
                "cache_hit": cache_hit,
                "duration_ms": round(duration_ms, 1),
                "host": host,
            },
            separators=(",", ":"),
        )
    )


def alert_large_empty(
    *,
    service: str,
    host: str,
    raw_chars: int,
    content_type: str = "",
    reason: str = "reader_empty",
) -> None:
    if raw_chars <= ALERT_CHARS:
        return
    metrics.inc(
        "web_loader_reader_empty_large_total",
        {"service": service},
    )
    LOGGER.warning(
        "reader_empty_large_page host=%s raw_chars=%d content_type=%s reason=%s",
        host,
        raw_chars,
        content_type,
        reason,
    )
