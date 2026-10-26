#!/usr/bin/env python3
"""Block personal emails, private IPs and internal hostnames in tracked files.

Placeholders are allowed: example.com/invalid/org, *.test, TEST-NET ranges,
host.docker.internal, and redaction markers. The security blocklist and its
SSRF test vectors are explicit code exceptions.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PRIVATE_IP_RE = re.compile(
    r"\b(?:10|127|169\.254|172\.(?:1[6-9]|2[0-9]|3[01])|192\.168)"
    r"\.[0-9]{1,3}\.[0-9]{1,3}\b"
)
INTERNAL_HOST_RE = re.compile(r"\.(?:local|lan|internal|home|corp)\b", re.IGNORECASE)
ALLOWED_EMAIL_DOMAINS = ("@example.com", "@example.invalid", "@example.org")
ALLOWED_FILES = {
    "gateway/security.py",  # SSRF blocklist networks
    "tests/test_ssrf.py",  # private-IP test vectors
}
ALLOWED_LINE_MARKERS = (
    "[redacted-email]",
    "[redacted-private-ip]",
    "[redacted-phone]",
    "host.docker.internal",
    "open_webui.internal",
    "example.com",
    "example.invalid",
    "example.org",
    "192.0.2.",
    "198.51.100.",
    "203.0.113.",
)
SKIP_SUFFIXES = {".pdf", ".gz", ".png", ".jpg", ".jpeg", ".webp", ".woff", ".woff2"}


def tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return [line for line in out.splitlines() if line.strip()]


def scan() -> list[str]:
    deny_domains = [
        item.strip().lower()
        for item in os.environ.get("PRIVACY_DENY_DOMAINS", "").split(",")
        if item.strip()
    ]
    issues: list[str] = []
    for name in tracked_files():
        path = Path(name)
        if not path.is_file() or path.suffix.lower() in SKIP_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line_no, line in enumerate(text.splitlines(), 1):
            if any(marker in line for marker in ALLOWED_LINE_MARKERS):
                continue
            for match in EMAIL_RE.finditer(line):
                email = match.group(0).lower()
                if not email.endswith(ALLOWED_EMAIL_DOMAINS):
                    issues.append(f"{name}:{line_no}: email {match.group(0)}")
            if name not in ALLOWED_FILES:
                for match in PRIVATE_IP_RE.finditer(line):
                    issues.append(f"{name}:{line_no}: private IP {match.group(0)}")
                scrubbed = line.replace("host.docker.internal", "host.docker.example")
                for match in INTERNAL_HOST_RE.finditer(scrubbed):
                    issues.append(
                        f"{name}:{line_no}: internal hostname {match.group(0)}"
                    )
            for domain in deny_domains:
                if domain in line.lower():
                    issues.append(f"{name}:{line_no}: denied domain {domain}")
    return issues


def main() -> int:
    issues = scan()
    if issues:
        print("privacy check failed:", file=sys.stderr)
        for issue in issues:
            print(" ", issue, file=sys.stderr)
        return 1
    print("privacy check ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
