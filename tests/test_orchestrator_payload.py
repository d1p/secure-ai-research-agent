"""Orchestrator gateway-envelope handling (offline)."""

from __future__ import annotations

import json

from orchestrator import api


def test_unwrap_fetch_payload_returns_text() -> None:
    payload = {
        "url": "https://example.com/",
        "status": 200,
        "content_type": "text/html",
        "text": "page text",
    }
    assert api._unwrap_fetch_payload(json.dumps(payload)) == "page text"


def test_unwrap_fetch_payload_handles_error_envelope() -> None:
    assert "fetch error 502" in api._unwrap_fetch_payload(
        json.dumps({"error": 502, "detail": "ConnectError"})
    )
    assert "plain text" == api._unwrap_fetch_payload("plain text")


def test_unwrap_fetch_payload_invalid_json_passthrough() -> None:
    assert api._unwrap_fetch_payload("{not json") == "{not json"


def test_extract_mcp_text_joins_text_chunks() -> None:
    payload = {
        "result": {
            "content": [
                {"type": "text", "text": "one"},
                {"type": "image", "text": "ignored"},
                {"type": "text", "text": "two"},
            ]
        }
    }
    assert api._extract_mcp_text(payload) == "one\ntwo"
