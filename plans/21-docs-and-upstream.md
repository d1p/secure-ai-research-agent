# Plan 21 - Documentation hygiene and upstream trafilatura draft

- **Workstream:** F1-F6, E5
- **Depends on:** plans 04, 19 (numbers to report), 20 (checkers)
- **Gate:** docs layout/front matter present; inbound links fixed; privacy
  checker and markdown/link lint pass; upstream issue is drafted but not posted.

## Goal

Make the repository's notes trustworthy and navigable, and remove real infra
values and personal contact details from tracked documentation.

## Layout

```
README.md                 # landing page + links
docs/README.md            # living-reference index
docs/web-loader.md        # modes, page types, budgets, links, cache, counters
docs/runbook.md           # deploy, verify, rollback, diagnose fallbacks
docs/testing.md           # markers, fixtures, golden updates, bench
docs/benchmarking.md      # corpus, metrics, tokenizer, evidence rules
docs/privacy.md           # placeholders and the privacy checker
docs/upstream/trafilatura-deduplicate-stateful.md
notes/README.md           # dated measurement reports index
notes/_template.md        # front matter + TL;DR + evidence checklist
plans/README.md           # this plan index
CONTRIBUTING.md           # notes/plans/commits/evidence/privacy
```

Do not create a second README at each level without content; each index must be
useful, not a stub.

## Note rename and front matter

- `git mv` the existing note to a slug filename without spaces or the commit
  hash: `notes/reader-mode-token-savings-2026-10-26.md`.
- Add front matter:

```yaml
---
title: ...
date: 2026-10-26
status: verified|draft|superseded
commit_tested: <short or full hash>
environment: ...
---
```

- Keep commit hashes in front matter/links, not in the filename.
- Update README and any other inbound links; verify with a link checker.
- Add a TL;DR that states results, limitations and known regressions together.
  If the new loader loses on a page type, say it there.

## Evidence rules (enforce in notes and CONTRIBUTING)

- Every number has a reproduction command and data source.
- Estimates are labelled; do not mix measured and estimated numbers in one
  table without a label.
- Comparisons come from the same run and conditions (same corpus, tokenizer,
  model, machine).
- Do not headline a metric that only measures where facts sit in a page.
- Separate "what changed" from "what we measured".
- Remove duplicated sections; link to the single source.

## New living reference

- `docs/web-loader.md`: page types, modes, budgets, link policy, cache,
  progressive loading, reason vocabulary, counters/metrics, how to read them.
- `docs/runbook.md`: deploy (compose build/up), scripted verification, rollback
  (revert/restore), diagnosing `reader_empty`, `fallback_low_coverage`,
  `structured_mode`, `challenge_needs_human`, `paywall`, `fetch_failed`,
  `cache_hit`; rollback steps; where logs/metrics/audit live. Use env
  placeholders, never real addresses.
- `docs/testing.md`: markers/options, fixture capture policy, golden update
  procedure, how to add a fixture/question, privacy scrub.
- `docs/benchmarking.md`: metrics definitions, tokenizer rules, corpus, how to
  reproduce a note.
- `docs/privacy.md`: placeholders and checker allowlist rationale.
- `notes/_template.md` with front matter, TL;DR, reproduction, evidence
  checklist.

## PII/infra scrub

Parameterise in all tracked files:

- personal emails -> documented placeholders (`@example.invalid` etc.),
- RFC1918/link-local addresses -> `<vm-ip>`/`${VAR}`/TEST-NET placeholders,
- internal hostnames/domains -> `${APP_DOMAIN}`/`example.com` placeholders,
- Grafana/Phoenix dashboard URLs -> placeholder values,
- `.env.example` values -> placeholders (real values stay in untracked `.env`),
- script defaults (`VM_HOST`, fetch User-Agent) -> require env or documented
  placeholder,
- README commands/diagrams -> placeholders, with a "set these locally" note.

Run `scripts/check_privacy.py` and the markdown/link linters; fix false
positives with exact allowlist entries, not broad ignores. Do not add real
values to `decision.md` or plan notes.

## Upstream trafilatura draft (do not post)

Create `docs/upstream/trafilatura-deduplicate-stateful.md` with:

- version/environment, minimal repro calling
  `trafilatura.extract(..., deduplicate=True)` repeatedly on one HTML string,
- observed counts (for example stable, then shrinking, then empty),
- expected behavior (idempotent across calls; no cross-call state),
- `deduplicate=False` workaround and stability check,
- a note that the draft is not posted and the link to `decision.md`.

Add `scripts/repro_trafilatura_dedup.py` (offline, no network) and run it to
confirm the repro; do not add it to the default test suite if it is slow.

## Verification

```bash
make verify
make docs-lint
pre-commit run --all-files
.venv/bin/python scripts/check_privacy.py
.venv/bin/python scripts/repro_trafilatura_dedup.py
```

Acceptance: layout and indexes exist; no broken inbound links; front matter and
TL;DR present; privacy checker passes; upstream draft is reproducible and not
posted.

## Risks / notes

- Scrubbing docs can break copy-paste deployment instructions; use clear
  placeholders and a local-values table in the runbook.
- The existing note's live-page numbers were measured on a different corpus;
  mark the note's status/limitations rather than rewriting history.
- Link checking needs network; keep it in CI/docs-lint, not `make verify` if
  offline verification is required.
