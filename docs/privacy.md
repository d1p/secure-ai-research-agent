# Privacy and infrastructure placeholders

Tracked files must not contain secrets, personal emails, private/link-local IPs
or internal hostnames. Use:

- `${APP_DOMAIN}` / `example.com` for public examples
- `ops@example.invalid` for a contact placeholder
- `192.0.2.0/24`, `198.51.100.0/24`, `203.0.113.0/24` (TEST-NET) for example IPs
- `host.docker.internal` only as the documented Docker special-use name
- `[redacted-email]`, `[redacted-private-ip]`, `[redacted-phone]` in fixtures

`scripts/check_privacy.py` scans tracked and untracked non-ignored text files.
It allows documented placeholders and has explicit exceptions for the SSRF
blocklist module and its private-IP test vectors. Set
`PRIVACY_DENY_DOMAINS=host1,host2` (CI secret) to block deployment-specific
domains; never commit that list.

Fixtures are scrubbed at capture time. If a real email or private IP appears,
treat it as a bug and re-capture/redact the fixture.
