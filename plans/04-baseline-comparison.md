# Plan 04 - Baseline comparison and winners per page type

- **Workstream:** A4
- **Depends on:** plan 03
- **Gate:** a dated note with reproducible numbers exists; winner per page type
  is logged in `decision.md`. No loader behavior change before this gate.

## Goal

Choose the extraction configuration from data, not intuition, and establish the
baseline that later plans must beat.

## Run

1. Run every candidate on the full corpus with `--runs 3` and `--grade`
   (LLM grading is optional; if credentials are unavailable, report QA as
   "not measured" and rely on precision/recall + fact-presence, clearly
   labelled).
2. Use the same machine, Python, tokenizer, fixture hashes and budgets for all
   candidates. Record the command and environment in the note.
3. Do not refresh fixtures during the run; the pinned copies are the data.

## Selection rule

Per page type, in order:

1. Highest answer accuracy (LLM-graded where available; otherwise fact
   presence and P/R with the limitation stated).
2. Lowest tokens at that accuracy.
3. Highest recall, then precision.
4. Simpler configuration wins ties.

If the current default is already best on a page type, keep it and say so. If a
candidate only wins on a metric that does not reflect answer quality (for
example, precision while losing deep facts), do not adopt it.

## Deliverable

`notes/reader-benchmark-2026-10-26.md` with:

- front matter (title, date, status, commit tested, environment, tokenizer),
- TL;DR stating results, limitations and any regression,
- one table per page type (tokens, P/R, accuracy/fact-presence, spread),
- per-fixture appendix,
- exact reproduction command,
- what changed vs what was measured,
- rejected candidates and why.

Update `decision.md` with the winner per page type, the date, and the note path.
If the corpus cannot support a decision (too noisy, questions ambiguous), say
so and fix the corpus before touching the loader.

## Verification

```bash
# Re-run one slice and compare to the note
.venv/bin/python scripts/bench_reader.py --runs 3 --json /tmp/bench-rerun.json
.venv/bin/python -m pytest -q
```

Acceptance: rerun reproduces the note's numbers within tokenizer/extraction
determinism; no unlabelled estimate appears in the note; every page type has a
decision or an explicit "not enough data".

## Risks / notes

- The existing reader note's live-page results were measured on a different
  corpus; do not overwrite it. The new note supersedes it as the current
  benchmark and links back.
- LLM grading adds cost; run it once per fixture/config and cache. If not run,
  never headline "accuracy".
