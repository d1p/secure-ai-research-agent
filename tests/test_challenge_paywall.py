"""Challenge/paywall detection: positives, negatives and clean refusals."""

from __future__ import annotations

from fixture_utils import load_meta, load_page_text

from shared.reader import (
    detect_challenge_html,
    detect_challenge_text,
    detect_paywall_html,
    read_html,
)


def test_challenge_html_signatures() -> None:
    assert detect_challenge_html(
        "<html><head><title>Just a moment...</title></head></html>"
    )
    assert detect_challenge_html("<div id='cf-challenge-running'></div>")
    assert detect_challenge_html("<div class='g-recaptcha'></div>")
    assert detect_challenge_html(
        "<html><body>Checking your browser. Enable JavaScript and cookies to continue.</body></html>"
    )


def test_challenge_visible_text_and_negatives() -> None:
    assert detect_challenge_text("Performing security verification") is True
    assert detect_challenge_text("Please verify you are human to continue") is True
    assert detect_challenge_text("A long article about captcha design " * 100) is False
    assert (
        detect_challenge_html(
            "<html><head><title>How CAPTCHAs work</title></head><body><article>"
            + ("captcha " * 400)
            + "</article></body></html>"
        )
        is False
    )


def test_cookie_wall_positive_banner_negative() -> None:
    positive = (
        "<html><body><div class='consent-wall'><h2>We value your privacy</h2>"
        "<p>Accept cookies to continue to the site.</p></div></body></html>"
    )
    assert detect_challenge_html(positive) or detect_paywall_html(positive)
    negative = (
        "<html><body><article><p>" + ("real article content " * 200) + "</p></article>"
        "<div class='cookie-banner'>We use cookies.</div></body></html>"
    )
    assert detect_paywall_html(negative) is False


def test_paywall_overlay_positive_article_negative() -> None:
    positive = (
        "<html><body><article><p>teaser</p><div class='paywall'>"
        "<h2>Subscribe to continue</h2></div></article></body></html>"
    )
    assert detect_paywall_html(positive) is True
    negative = (
        "<html><body><article><h1>Paywalls explained</h1><p>"
        + ("This article discusses paywalls and subscriptions. " * 100)
        + "</p></article></body></html>"
    )
    assert detect_paywall_html(negative) is False


def test_needs_human_never_leaks_junk() -> None:
    challenge = read_html(
        load_page_text("challenge-bot"), load_meta("challenge-bot")["source_url"]
    )
    assert challenge.text == ""
    assert challenge.reason == "challenge_needs_human"
    paywall = read_html(
        load_page_text("paywall-cookie"), load_meta("paywall-cookie")["source_url"]
    )
    assert paywall.text.startswith("[paywall]")
    assert "Create a free account" not in paywall.text
    assert "Subscribe to continue" not in paywall.text
