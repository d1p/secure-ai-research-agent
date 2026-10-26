# Contributing

Read `plans/README.md` for the current work plan and `decision.md` for
decisions that must not be re-litigated silently.

## Commits

- Conventional commit prefixes: `feat:`, `fix:`, `test:`, `docs:`, `perf:`,
  `refactor:`, `chore:`, `build:`, `ci:`.
- One logical change per commit.
- A behavior change links its plan file and benchmark note in the body, for
  example:
  `feat(reader): page-type budgets (plans/10-budgets.md)`
- Never commit secrets, personal emails, private IPs or internal hostnames.
  Use the documented placeholders and run `python scripts/check_privacy.py`.

## Notes and plans

- `plans/` is for approved work plans; each plan must be independently testable.
- `notes/` is for dated measurement reports. Use `notes/_template.md`, include
  front matter and a TL;DR that states results, limitations and regressions.
- `docs/` is the living reference (runbook, loader behavior, testing).

## Evidence rules

- Every number has a reproduction command and data source.
- Estimates are labelled; do not mix measured and estimated numbers in one
  table.
- Compare runs under the same conditions and tokenizer.
- Do not headline a metric that only measures where facts sit in a page.
- Separate "what changed" from "what we measured".

## Verification

```bash
make verify
pre-commit run --all-files
```

Network/LLM tests are opt-in: `pytest --run-network`, `--run-llm`, `--run-slow`.
