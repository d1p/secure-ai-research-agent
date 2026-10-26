"""Metrics, structured logging and loader reason tests."""

from __future__ import annotations

import json
import logging

import pytest

from shared import metrics
from shared.reader import read_html
from shared.telemetry import alert_large_empty, record_load
from shared.tokens import count_tokens, tokenizer_name


def setup_function() -> None:
    metrics.reset()


def test_metrics_render_counters_and_summaries() -> None:
    metrics.inc("web_loader_loads_total", {"reason": "reader_ok", "service": "gateway"})
    metrics.inc(
        "web_loader_loads_total", {"reason": "reader_ok", "service": "gateway"}, 2
    )
    metrics.observe("web_loader_tokens", 10, {"service": "gateway", "direction": "out"})
    metrics.observe("web_loader_tokens", 20, {"service": "gateway", "direction": "out"})
    text = metrics.render()
    assert 'web_loader_loads_total{reason="reader_ok",service="gateway"} 3' in text
    assert 'web_loader_tokens_sum{direction="out",service="gateway"} 30' in text
    assert 'web_loader_tokens_count{direction="out",service="gateway"} 2' in text


def test_metrics_escape_labels() -> None:
    metrics.inc("x_total", {"host": 'a"b\\c'})
    text = metrics.render()
    assert 'host="a\\"b\\\\c"' in text


def test_record_load_emits_json_without_full_url(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="web_loader")
    record_load(
        service="gateway",
        reason="reader_ok",
        method="reader",
        page_type="article",
        chars_in=1000,
        chars_out=500,
        tokens_in=100,
        tokens_out=50,
        truncated=False,
        source_count=3,
        duration_ms=12.5,
        host="example.com",
    )
    line = caplog.records[-1].message
    payload = json.loads(line)
    assert payload["event"] == "web_loader_load"
    assert payload["reason"] == "reader_ok"
    assert payload["tokens_out"] == 50
    assert payload["host"] == "example.com"
    assert "http://" not in line
    assert "?" not in line


def test_alert_large_empty_warns_and_counts(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, logger="web_loader")
    alert_large_empty(
        service="gateway", host="example.com", raw_chars=10, content_type="text/html"
    )
    assert not [r for r in caplog.records if "reader_empty_large_page" in r.message]
    alert_large_empty(
        service="gateway",
        host="example.com",
        raw_chars=300000,
        content_type="text/html",
        reason="reader_empty",
    )
    assert any("reader_empty_large_page" in r.message for r in caplog.records)
    assert "web_loader_reader_empty_large_total" in metrics.render()


def test_reader_reasons() -> None:
    assert read_html(
        "<html><body><p>hello</p></body></html>", max_chars=None
    ).reason in {
        "reader_ok",
        "fallback_low_coverage",
        "reader_empty",
    }
    empty = read_html("", max_chars=None)
    assert empty.reason == "reader_empty"
    challenge = read_html("<html><head><title>Just a moment...</title></head></html>")
    assert challenge.reason == "challenge_needs_human"
    assert challenge.challenge is True


def test_token_counter_is_labelled_and_positive() -> None:
    assert count_tokens("hello world") > 0
    assert tokenizer_name() in {"tiktoken:cl100k_base", "chars4"}
