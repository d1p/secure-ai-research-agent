# Plan 20 - Workflow tooling, privacy checker and CI

- **Workstream:** E1-E4
- **Depends on:** plans 06 (minimal Makefile), 17-19 (tests/bench)
- **Gate:** `make verify`, pre-commit hooks and CI config pass locally; the
  privacy checker blocks a synthetic violation and allows documented
  placeholders/test blocklists.

## Goal

Make the measured workflow repeatable and make leaking PII/infra values hard.

## Makefile (extend the plan 06 file)

Targets: `install-dev`, `test`, `lint`, `fmt`, `bench`, `bench-live`, `up`,
`down`, `verify`, `docs-lint`, `privacy`.

- `verify` = lint + tests + privacy + `docker compose config -q` (using an
  example env file if needed).
- `fmt` = `ruff format .` + `ruff check --fix`; run a repo-wide format as an
  isolated commit before `verify` enforces `ruff format --check` (the current
  16-file drift is pre-existing).
- `bench` is offline; `bench-live` is explicitly network/LLM.
- No target silently deploys or commits.

## pre-commit

`.pre-commit-config.yaml` with pinned revisions:

- `ruff` and `ruff-format`,
- markdownlint (node hook or pinned action-compatible tool),
- `gitleaks` secret scanner,
- `trailing-whitespace`, `end-of-file-fixer`, `check-yaml`, `check-json`,
  `check-merge-conflict`, `check-added-large-files` (gzip/large fixture
  allowance documented),
- local `python scripts/check_privacy.py`.

The privacy checker:

- scans `git ls-files` (tracked content only),
- flags personal emails unless they are documented placeholders
  (`@example.com`, `@example.invalid`, `@example.org`),
- flags RFC1918/link-local IPs except an explicit allowlist for the security
  blocklist module and SSRF test vectors (documented in the checker),
- flags internal-only hostname suffixes (private/local TLDs) and an optional
  `PRIVACY_DENY_DOMAINS` list supplied via env/CI secret (never committed),
- exits non-zero with file/line details; placeholders and public URLs pass.

## GitHub Actions

`.github/workflows/ci.yml` on PRs and main:

- `lint`: ruff check, ruff format --check, markdownlint, privacy checker.
- `test`: `pytest -q` on Python 3.13 (fast/offline).
- `docs`: markdownlint + link check (pinned action).
- `security`: `pip-audit -r requirements-dev.txt`, `npm audit
  --audit-level=high --prefix browser`, gitleaks; fail on high.
- `permissions: contents: read`, concurrency group, pip/npm cache.
- Pin actions to full SHAs; document the update procedure.

## Conventional commits

Add a short `CONTRIBUTING.md` section (full docs in plan 21): conventional
commit prefixes; one logical change per commit; behavior changes link the plan
file and benchmark note in the body; no secrets/PII. No commit is made by this
plan.

## Verification

```bash
make verify
pre-commit run --all-files
.venv/bin/python scripts/check_privacy.py
.venv/bin/python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"
```

Acceptance: all targets pass locally; checker catches a temporary planted
private IP/email in `/tmp` copy and ignores documented placeholders; CI YAML
parses. CI itself is validated when pushed (not in this environment).

## Risks / notes

- `ruff format` touches many files; keep it a separate commit so review is
  mechanical.
- `npm audit`/`pip-audit` need network in CI; they are not part of the default
  local test command.
- The privacy checker is intentionally conservative; false positives are fixed
  with documented placeholders or exact allowlist entries, not broad ignores.
