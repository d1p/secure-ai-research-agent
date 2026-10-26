"""SSRF / exfiltration tests for the browser gateway (project spec section 13/22)."""

from __future__ import annotations

import socket
from collections.abc import Iterable

import pytest

from gateway.security import (
    is_blocked_ip,
    validate_redirect,
    validate_url,
)


def resolver(ips: list[str]):
    """Build a resolver that returns the given IPs as (AF_INET, ip) tuples."""

    def _resolve(_host: str) -> Iterable[tuple[int, str]]:
        return [(socket.AF_INET, ip) for ip in ips]

    return _resolve


# --- Literal IP ranges -----------------------------------------------------
@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",
        "10.0.0.1",
        "10.255.255.255",
        "172.16.0.1",
        "172.31.255.255",
        "192.168.0.1",
        "192.168.1.100",
        "169.254.169.254",  # cloud metadata
        "100.64.0.1",
        "100.127.255.255",
        "::1",
        "fd00::1",
        "fe80::1",
    ],
)
def test_blocked_ip_ranges(ip: str) -> None:
    assert is_blocked_ip(ip) is True, f"{ip} should be blocked"


@pytest.mark.parametrize(
    "ip", ["93.184.216.34", "8.8.8.8", "1.1.1.1", "2606:4700:4700::1111"]
)
def test_public_ips_allowed(ip: str) -> None:
    assert is_blocked_ip(ip) is False, f"{ip} should not be blocked"


# --- Hostname / scheme blocking -------------------------------------------
@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/",
        "http://localhost:8080/x",
        "http://metadata.google.internal/",
    ],
)
def test_localhost_and_metadata_blocked(url: str) -> None:
    verdict = validate_url(url, resolver=resolver(["93.184.216.34"]))
    assert not verdict.ok


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "chrome://settings",
        "about:config",
        "javascript:alert(1)",
        "data:text/html,x",
    ],
)
def test_local_schemes_blocked(url: str) -> None:
    assert not validate_url(url).ok


def test_bare_hostname_resolving_internally_blocked() -> None:
    # "nas.local" resolves to 192.168.1.10 -> blocked (suffix or IP check)
    verdict = validate_url("http://nas.local/", resolver=resolver(["192.168.1.10"]))
    assert not verdict.ok


def test_internal_suffix_hostname_blocked() -> None:
    verdict = validate_url("http://printer.lan/", resolver=resolver(["93.184.216.34"]))
    assert not verdict.ok


# --- DNS rebinding ---------------------------------------------------------
def test_dns_rebinding_caught_on_redirect() -> None:
    """A hostname that first resolves safely then resolves to an internal IP
    must be blocked when re-validated after a redirect."""

    state = {"calls": 0}

    def rebinding_resolver(_host: str) -> Iterable[tuple[int, str]]:
        state["calls"] += 1
        if state["calls"] == 1:
            return [(socket.AF_INET, "93.184.216.34")]
        return [(socket.AF_INET, "10.0.0.5")]

    first = validate_url("http://rebind.example/", resolver=rebinding_resolver)
    assert first.ok
    second = validate_redirect("http://rebind.example/", resolver=rebinding_resolver)
    assert not second.ok


def test_mixed_dns_answers_blocked() -> None:
    """Even one internal IP among many safe answers must block."""

    def mixed_resolver(_host: str) -> Iterable[tuple[int, str]]:
        return [(socket.AF_INET, "93.184.216.34"), (socket.AF_INET, "127.0.0.1")]

    assert not validate_url("http://mixed.example/", resolver=mixed_resolver).ok


# --- Exfiltration ----------------------------------------------------------
def test_url_too_long_blocked() -> None:
    long_url = "http://example.com/" + "a" * 600
    assert not validate_url(long_url, resolver=resolver(["93.184.216.34"])).ok


def test_long_base64_in_query_blocked() -> None:
    blob = "A" * 80 + "=="
    assert not validate_url(
        f"http://example.com/?data={blob}", resolver=resolver(["93.184.216.34"])
    ).ok


def test_normal_url_allowed() -> None:
    verdict = validate_url(
        "https://example.com/page?q=hello", resolver=resolver(["93.184.216.34"])
    )
    assert verdict.ok
