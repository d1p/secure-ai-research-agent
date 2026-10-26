"""PDF and non-HTML content-type handling."""

from __future__ import annotations

import io

import httpx
import pytest
from fixture_utils import load_page_bytes

import gateway.app as gw
from gateway.security import UrlVerdict
from shared.reader import extract_pdf


def test_pdf_fixture_has_page_markers_and_facts() -> None:
    result = extract_pdf(load_page_bytes("paper-arxiv-pdf"), max_chars=None)
    assert result.method == "pdf"
    assert result.page_type == "pdf"
    assert result.reason == "pdf_text"
    assert "[page 1]" in result.text
    assert "Llama 2" in result.text
    assert "7 billion to 70 billion" in result.text


def test_pdf_budget_truncates() -> None:
    result = extract_pdf(load_page_bytes("paper-arxiv-pdf"), max_chars=500)
    assert result.truncated is True
    assert len(result.text) <= 500 + 200


def test_pdf_without_text_returns_clean_message() -> None:
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    result = extract_pdf(buf.getvalue())
    assert "no extractable text" in result.text
    assert "OCR is not supported" in result.text


def test_encrypted_pdf_returns_clean_message() -> None:
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.encrypt("secret")
    buf = io.BytesIO()
    writer.write(buf)
    result = extract_pdf(buf.getvalue())
    assert "encrypted" in result.text
    assert result.reason == "pdf_empty"


def test_corrupt_pdf_returns_clean_message() -> None:
    result = extract_pdf(b"%PDF-1.7\nnot really a pdf")
    assert result.reason == "pdf_empty"
    assert "could not be read" in result.text


@pytest.fixture(autouse=True)
def _clear(monkeypatch):
    monkeypatch.setattr(gw, "GATEWAY_TOKEN", "t")
    monkeypatch.setattr(gw, "validate_url", lambda _url: UrlVerdict(True))
    gw._HTTP_CACHE.clear()


@pytest.mark.asyncio
async def test_gateway_pdf_path() -> None:
    pdf = load_page_bytes("paper-arxiv-pdf")

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=pdf, headers={"content-type": "application/pdf"}
        )

    result = await gw._http_fetch(
        "http://example.com/paper", transport=httpx.MockTransport(handler)
    )
    envelope = result["result"]["content"][0]["text"]
    assert "[page 1]" in envelope
    assert "Llama 2" in envelope


@pytest.mark.asyncio
async def test_gateway_binary_is_rejected_cleanly() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"\x00\x01\x02binary\x00garbage" * 100,
            headers={"content-type": "application/octet-stream"},
        )

    result = await gw._http_fetch(
        "http://example.com/bin", transport=httpx.MockTransport(handler)
    )
    text = result["result"]["content"][0]["text"]
    assert "[binary content not shown" in text
    assert "garbage" not in text


@pytest.mark.asyncio
async def test_gateway_text_passthrough() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"hello\n\n\nworld",
            headers={"content-type": "text/plain; charset=utf-8"},
        )

    result = await gw._http_fetch(
        "http://example.com/plain", transport=httpx.MockTransport(handler)
    )
    text = result["result"]["content"][0]["text"]
    assert "hello" in text and "world" in text
    assert "\n\n\n" not in text
