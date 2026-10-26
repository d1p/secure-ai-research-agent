# Plan 19 - End-to-end A/B: old vs new loader

- **Workstream:** A5
- **Depends on:** plans 04, 09-18 (loader changes kept by the benchmark)
- **Gate:** N runs of the same research tasks on old and new loaders, same
  conditions; total tokens, tool calls, success rate and variance reported.
  Every "estimate" in existing notes is replaced by a measured number or
  explicitly labelled.

## Goal

Measure the loader at the agent level, not just the extractor level. The
offline benchmark can win on content and still lose after extra tool calls.

## Task set

Use a small, fixed set of research tasks that exercises page types:

- a deep fact from a long article,
- a table/list answer,
- a code/tutorial answer,
- a thread answer with author/order context,
- a PDF answer,
- a link/citation follow-up.

Each task has a ground-truth answer and source URL; store in
`tests/tasks/research.json` (no PII, pinned public URLs).

## Loader variants

- `LOADER_VARIANT=legacy`: old behavior (regex tag-strip / old budget / old
  browser innerText path), preserved for the benchmark only.
- `LOADER_VARIANT=new`: current adopted loader.

The legacy path is benchmark-only; it is not a supported deployment mode and
must not be enabled by default. Log this in `decision.md`.

## Runner

`scripts/bench_agent.py` (network/LLM, not default CI):

- `--variant legacy|new`, `--runs N`, `--tasks`, `--model`, `--base-url`,
  `--token` from env.
- Runs the task through the orchestrator/Open WebUI path; records the answer,
  total prompt/completion tokens from LiteLLM usage (or the response `usage`),
  wall time, tool-call count from the audit table, and the commit/image.
- Grades success against ground truth (LLM grader or exact for numeric
  answers); caches grades; reports per-task and aggregate.
- `scripts/bench_ab.sh` restarts gateway/orchestrator with each variant, waits
  for health, runs the runner, and writes JSON/Markdown. Run on the VM with
  provider credentials; not in CI by default.
- Include a dry-run mode (`--runs 1 --task ...`) to validate plumbing before
  spending tokens.

## Analysis and honesty

- Report mean/median/min/max and variance; N >= 3 for a claim; state N and
  model.
- Compare total tokens, tool calls and success rate; do not headline only the
  extractor's tokens.
- If the new loader loses on a page type, the TL;DR says so and the plan note
  records it. Revert the responsible change if it cannot be scoped.
- Replace the "70-85% fewer tool-output tokens" estimate in the existing note
  with a measured number, or label it "estimate, not measured" and link the
  new note.

## Deliverable

`notes/loader-ab-2026-10-26.md` with front matter, TL;DR, per-task table,
aggregate, variance, environment, exact commands, limitations and rejected
options. Update `decision.md`.

## Verification

```bash
.venv/bin/python scripts/bench_agent.py --variant new --runs 1 --task deep-fact
# after approval and credentials:
./scripts/bench_ab.sh --runs 3 --tasks tests/tasks/research.json
.venv/bin/python -m pytest -q
```

Acceptance: dry-run works; N>=3 results reported with variance; estimates are
replaced/labelled; no claim beyond the measured conditions.

## Risks / notes

- Live pages change; pin URLs/tasks and record capture dates. This is not the
  offline corpus and is not used for extractor precision/recall.
- LLM variance can exceed the loader effect; use N>=3 and report spread.
- Credentials and provider availability are required; if unavailable, this plan
  ends as "not measured" rather than a guess.
