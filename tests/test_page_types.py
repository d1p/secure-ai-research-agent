"""Page-type detection and paywall/challenge negatives."""

from __future__ import annotations

from fixture_utils import fixture_dirs, load_meta, load_page_text

from shared.reader import detect_page_type, detect_paywall_html, read_html


def test_corpus_page_types_detected() -> None:
    for meta_path in fixture_dirs():
        slug = meta_path.parent.name
        meta = load_meta(slug)
        raw = load_page_text(slug) if meta["page_type"] != "pdf" else ""
        assert detect_page_type(raw, meta["source_url"]) == meta["page_type"], slug


def test_long_article_about_captcha_is_not_a_challenge() -> None:
    raw = load_page_text("captcha-mention")
    assert (
        detect_page_type(raw, load_meta("captcha-mention")["source_url"]) == "article"
    )
    result = read_html(raw, load_meta("captcha-mention")["source_url"], max_chars=None)
    assert result.challenge is False
    assert result.text


def test_paywall_positive_and_negative() -> None:
    positive = (
        "<html><body><article><p>teaser</p><div class='paywall'>"
        "<h2>Subscribe to continue</h2><p>Create a free account to continue.</p>"
        "</div></article></body></html>"
    )
    assert detect_paywall_html(positive) is True
    negative = (
        "<html><body><article><h1>How paywalls work</h1><p>"
        + ("A long article about paywalls and subscriptions. " * 100)
        + "</p><p>Subscribe to continue reading is a common phrase.</p></article></body></html>"
    )
    assert detect_paywall_html(negative) is False


def test_paywall_result_never_returns_overlay_junk() -> None:
    raw = load_page_text("paywall-cookie")
    result = read_html(raw, load_meta("paywall-cookie")["source_url"])
    assert result.page_type == "paywall"
    assert result.reason == "paywall"
    assert result.paywall is True
    assert "Subscribe to continue" not in result.text
    assert result.text.startswith("[paywall]")


def test_challenge_result_is_clean() -> None:
    raw = load_page_text("challenge-bot")
    result = read_html(raw, load_meta("challenge-bot")["source_url"])
    assert result.page_type == "challenge"
    assert result.reason == "challenge_needs_human"
    assert result.challenge is True
    assert result.text == ""


def test_product_word_review_alone_is_not_product() -> None:
    raw = (
        "<html><body><article><h1>A review of code review tools</h1>"
        + ("This article reviews the review process. " * 100)
        + "</article></body></html>"
    )
    assert detect_page_type(raw, "https://example.com/article") != "product"


def test_detection_is_deterministic() -> None:
    raw = load_page_text("docs-reference")
    url = load_meta("docs-reference")["source_url"]
    assert detect_page_type(raw, url) == detect_page_type(raw, url)
