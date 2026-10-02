"""Pure security logic for the browser safeguard gateway.

Dependency-light (stdlib only) so it can be unit-tested without the FastAPI /
async stack.  The gateway (`app.py`) wraps these functions with HTTP handlers,
rate limiting, MCP proxying and Postgres audit logging.
"""

from __future__ import annotations

import ipaddress
import re
import socket
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from urllib.parse import urlsplit

# ---------------------------------------------------------------------------
# SSRF blocklists (project spec section 13)
# ---------------------------------------------------------------------------
BLOCKED_NETWORKS: list[ipaddress._BaseNetwork] = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("::/128"),
]

BLOCKED_HOSTNAMES: set[str] = {
    "localhost",
    "localhost.localdomain",
    "ip6-localhost",
    "ip6-loopback",
    "metadata",
    "metadata.google.internal",
}

# Only http(s) are allowed; every other scheme is a browser/local scheme.
ALLOWED_SCHEMES: set[str] = {"http", "https"}

# Local/internal hostname suffixes that indicate a non-routable target.
BLOCKED_HOSTNAME_SUFFIXES: tuple[str, ...] = (
    ".localhost",
    ".local",
    ".internal",
    ".lan",
    ".home",
    ".corp",
)

# ---------------------------------------------------------------------------
# Exfiltration limits (project spec section 13)
# ---------------------------------------------------------------------------
MAX_URL_LENGTH = 512
MAX_QUERY_LENGTH = 1024
_BASE64_PAYLOAD = re.compile(r"[A-Za-z0-9+/]{64,}={0,2}")

Resolver = Callable[[str], Iterable[tuple[int, str]]]


def _default_resolver(host: str) -> Iterable[tuple[int, str]]:
    infos = socket.getaddrinfo(host, None)
    return [(info[0], info[4][0]) for info in infos]


@dataclass(frozen=True)
class UrlVerdict:
    ok: bool
    reason: str = ""


def is_blocked_ip(ip: str) -> bool:
    """Return True if a literal IP string falls in a blocked network."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(addr in net for net in BLOCKED_NETWORKS)


def check_exfiltration(url: str) -> UrlVerdict:
    """Reject obvious data-exfiltration attempts carried in the URL."""
    if len(url) > MAX_URL_LENGTH:
        return UrlVerdict(False, f"url length {len(url)} exceeds {MAX_URL_LENGTH}")
    parts = urlsplit(url)
    query = parts.query
    if len(query) > MAX_QUERY_LENGTH:
        return UrlVerdict(False, f"query length {len(query)} exceeds {MAX_QUERY_LENGTH}")
    if _BASE64_PAYLOAD.search(query):
        return UrlVerdict(False, "query contains a long base64/blob payload")
    return UrlVerdict(True)


def validate_url(
    url: str,
    resolver: Resolver | None = None,
) -> UrlVerdict:
    """Validate a URL for SSRF safety, resolving and checking every IP.

    `resolver` is injectable so tests can simulate DNS answers (including
    rebinding, where the same hostname resolves to different IPs across calls).
    """
    if not url:
        return UrlVerdict(False, "empty url")

    exfil = check_exfiltration(url)
    if not exfil.ok:
        return exfil

    try:
        parts = urlsplit(url)
    except ValueError as exc:
        return UrlVerdict(False, f"unparseable url: {exc}")

    scheme = (parts.scheme or "").lower()
    if scheme not in ALLOWED_SCHEMES:
        return UrlVerdict(False, f"scheme '{scheme or '(none)'}' not allowed")

    hostname = (parts.hostname or "").lower()
    if not hostname:
        return UrlVerdict(False, "url has no hostname")

    if hostname in BLOCKED_HOSTNAMES:
        return UrlVerdict(False, f"hostname '{hostname}' blocked")

    if hostname.endswith(BLOCKED_HOSTNAME_SUFFIXES):
        return UrlVerdict(False, f"hostname '{hostname}' matches internal suffix")

    # Resolve and validate EVERY resulting IP (prevents DNS rebinding where a
    # hostname answers with a mix of safe and internal addresses).
    resolve = resolver or _default_resolver
    try:
        addrinfos = list(resolve(hostname))
    except socket.gaierror as exc:
        return UrlVerdict(False, f"dns resolution failed for '{hostname}': {exc}")
    if not addrinfos:
        return UrlVerdict(False, f"dns resolution returned no addresses for '{hostname}'")

    for _family, ip in addrinfos:
        if is_blocked_ip(ip):
            return UrlVerdict(False, f"hostname '{hostname}' resolves to blocked ip {ip}")
    return UrlVerdict(True)


def validate_redirect(
    url: str,
    resolver: Resolver | None = None,
) -> UrlVerdict:
    """Re-validate after a redirect (identical rules, called on every hop)."""
    return validate_url(url, resolver)


# ---------------------------------------------------------------------------
# Tool tiers (project spec section 14)
# ---------------------------------------------------------------------------
TIER_ALWAYS = 0
TIER_VALIDATED = 1
TIER_APPROVAL = 2
TIER_FORBIDDEN = 3

# Maps Playwright MCP tool names to their base tier.
# Tier 3 tools (evaluate, cookies, storage, devtools, downloads) are 403.
TOOL_TIERS: dict[str, int] = {
    # Tier 0 — read-only / navigation
    "browser_navigate": TIER_ALWAYS,
    "browser_navigate_back": TIER_ALWAYS,
    "browser_snapshot": TIER_ALWAYS,
    "browser_find": TIER_ALWAYS,
    "browser_take_screenshot": TIER_ALWAYS,
    "browser_wait_for": TIER_ALWAYS,
    "browser_tabs": TIER_ALWAYS,
    "browser_console_messages": TIER_ALWAYS,
    "browser_network_requests": TIER_ALWAYS,
    "browser_mouse_wheel": TIER_ALWAYS,
    "browser_resize": TIER_ALWAYS,
    "browser_emulate_media": TIER_ALWAYS,
    # Tier 1 — validated interactions
    "browser_click": TIER_VALIDATED,
    "browser_type": TIER_VALIDATED,
    "browser_fill_form": TIER_VALIDATED,
    "browser_select_option": TIER_VALIDATED,
    "browser_press_key": TIER_VALIDATED,
    "browser_hover": TIER_VALIDATED,
    "browser_drag": TIER_VALIDATED,
    "browser_drop": TIER_VALIDATED,
    "browser_handle_dialog": TIER_VALIDATED,
    # Tier 2 — approval required
    "browser_file_upload": TIER_APPROVAL,
    # Tier 3 — always 403
    "browser_evaluate": TIER_FORBIDDEN,
    "browser_run_code_unsafe": TIER_FORBIDDEN,
    "browser_file_download": TIER_FORBIDDEN,

    # --- BrowserHand (real-browser) tools, mapped to the same tier model -----
    # Tier 0 — read-only / navigation
    "browserhand_navigate": TIER_ALWAYS,
    "browserhand_extract": TIER_ALWAYS,
    "browserhand_gettext": TIER_ALWAYS,
    "browserhand_screenshot": TIER_ALWAYS,
    "browserhand_fullscreenshot": TIER_ALWAYS,
    "browserhand_pdf": TIER_ALWAYS,
    "browserhand_wait": TIER_ALWAYS,
    "browserhand_waitfor": TIER_ALWAYS,
    "browserhand_scroll": TIER_ALWAYS,
    "browserhand_scrollto": TIER_ALWAYS,
    "browserhand_goback": TIER_ALWAYS,
    "browserhand_goforward": TIER_ALWAYS,
    "browserhand_refresh": TIER_ALWAYS,
    "browserhand_tab": TIER_ALWAYS,
    # Tier 1 — validated interactions
    "browserhand_hover": TIER_VALIDATED,
    "browserhand_click": TIER_VALIDATED,
    "browserhand_type": TIER_VALIDATED,
    "browserhand_select": TIER_VALIDATED,
    "browserhand_keypress": TIER_VALIDATED,
    "browserhand_clear": TIER_VALIDATED,
    "browserhand_dialog": TIER_VALIDATED,
    # Tier 2 — approval required
    "browserhand_upload": TIER_APPROVAL,
    # Tier 3 — always 403
    "browserhand_exec": TIER_FORBIDDEN,
    "browserhand_cookie": TIER_FORBIDDEN,
    "browserhand_network": TIER_FORBIDDEN,
}

# Tier-3 tool name fragments (covers caps-gated tools even if not in the list).
FORBIDDEN_TOOL_FRAGMENTS: tuple[str, ...] = (
    "cookie",
    "storage",
    "localstorage",
    "sessionstorage",
    "clipboard",
    "devtools",
    "download",
    "evaluate",
    "run_code",
    "route",  # network interception
    "tracing",
    "recording",
    "video",
)


def classify_tool(tool_name: str) -> int:
    """Return the tier for a Playwright MCP tool name."""
    name = tool_name.lower()
    if name in TOOL_TIERS:
        return TOOL_TIERS[name]
    if any(frag in name for frag in FORBIDDEN_TOOL_FRAGMENTS):
        return TIER_FORBIDDEN
    return TIER_FORBIDDEN  # unknown tools are denied by default


# Sensitive field / action keywords (project spec section 14).
SENSITIVE_FIELD_HINTS: tuple[str, ...] = (
    "password",
    "passcode",
    "pin",
    "credit",
    "card",
    "cvv",
    "cvc",
    "account number",
    "iban",
    "ssn",
    "social security",
)

SENSITIVE_ACTION_HINTS: tuple[str, ...] = (
    "buy",
    "pay",
    "checkout",
    "place order",
    "submit",
    "send",
    "post",
    "delete",
    "sign in",
    "log in",
    "login",
    "confirm",
    "purchase",
    "donate",
    "upgrade",
    "subscribe",
)


def field_is_sensitive(label: str) -> bool:
    """True if an input label/name looks like a sensitive field."""
    text = label.lower()
    return any(hint in text for hint in SENSITIVE_FIELD_HINTS)


def action_is_sensitive(label: str) -> bool:
    """True if an element label/role looks like a sensitive action."""
    text = label.lower()
    return any(hint in text for hint in SENSITIVE_ACTION_HINTS)


def is_sensitive_element(name: str, role: str, value: str) -> bool:
    """Combine element metadata to decide whether interaction must be blocked."""
    blob = f"{name} {role} {value}".lower()
    return field_is_sensitive(blob) or action_is_sensitive(blob)
