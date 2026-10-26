---
title: Reader benchmark baseline (corpus v1)
date: 2026-10-26
status: draft
commit_tested: 8d51cf3
environment: Python 3.13.5; trafilatura 2.3.1; lxml 6.1.3; tiktoken cl100k_base; offline fixture corpus
---

# Reader benchmark baseline (corpus v1)

## TL;DR

- The corpus and harness now exist (21 fixtures, offline, 3 runs each). This
  note is the **pre-change baseline**, not a claim that the current loader is
  optimal.
- On prose pages, the current reader beats tag-strip on evidence recall at
  similar or lower tokens; on Wikipedia the reader drops infobox/table context
  (15/17 evidence questions vs 16/17 for `reader-precision`, 13/17 for
  tag-strip). That is the main accuracy gap plan 09 targets.
- `reader-no-tables` sometimes looks cheaper on the bag-of-words evidence
  proxy because table answers are also mentioned in nearby prose. It is **not**
  evidence that removing tables is safe; the proxy is not answer accuracy.
- LLM-graded answer accuracy was **not measured** in this run (no benchmark
  credentials on the host). All accuracy numbers here are evidence-token
  presence, not an LLM answer score.
- PDF extraction is **not implemented yet** (plan 15), so the PDF row is empty.
  Paywall/challenge rows are excluded from winners: those paths are judged by a
  clean `needs_human` result in the gateway, not by P/R.
- A real bug was found and fixed: the CAPTCHA Wikipedia article was misclassified
  as a bot challenge because the structural regex treated any `captcha` class as
  a challenge. The generic `captcha` marker was removed; the article now
  extracts normally (4/4 evidence).

## Method

- Corpus: `tests/fixtures/` (see its README and `manifest.json`).
- Budget: each fixture's resolved per-domain budget (12k default, 24k finance,
  32k SEC) unless noted; `large-page`, `paper`, and table pages are truncated
  at that budget, so recall is budget-limited by design.
- Tokens: tiktoken `cl100k_base`; this is a proxy for DeepSeek, not the real
  DeepSeek tokenizer.
- Precision/recall: word-multiset overlap against `reference.md`.
- Evidence presence: a question counts as present when at least 80% of its
  evidence tokens occur in the output (bag of words). This is deterministic and
  cheap, but it can be satisfied by prose near a table; it is not answer
  accuracy.
- Scores: min/median/max over 3 runs; the table shows medians.

## Provisional winners by page type

Selected by evidence presence first, then tokens; **not** a final adoption
decision where the metric limitation applies.

| Page type | Best on this run | Facts | Tokens | Note |
|---|---|---:|---:|---|
| article | `reader-precision` | 16/17 | 3,212 | Wikipedia infobox/lede gap remains |
| blog | `reader-default` | 4/4 | 857 | reader clearly beats tag-strip on tokens |
| docs | `reader-precision` / `reader-default` | 8/8 | 2,870 | tie; keep default |
| listing | `reader-default` | 4/4 | 93 | |
| news | `readability` | 4/4 | 517 | readability wins tokens here; not adopted globally |
| paper | `reader-no-tables` | 3/4 | 2,854 | proxy may count table-adjacent prose |
| product | `reader-no-tables` | 2/4 | 63 | low absolute recall; needs structured mode |
| spa | `reader-no-tables` | 3/4 | 35 | rendered DOM path; structure lost |
| table | `reader-no-tables` / `reader-default` | 9/9 | 1,496 / 2,026 | **do not drop tables** on this proxy |
| thread | `reader-default` | 13/13 | 1,767 | |
| tutorial | `stagehand-innertext` | 3/4 | 3,152 | code/structure loss in reader |
| pdf | not measured | - | - | plan 15 |
| paywall/challenge | excluded | - | - | gateway refusal, not P/R |

The `reader-precision` win on `article` is not yet a recommendation: it may
help Wikipedia infoboxes, but plan 09 adds a title/description/canonical header
and structured content first. Re-run after those changes.

## What is already visible

- Wikipedia (`wikipedia-encyclopedia`, `large-page`, `non-english`) loses
  infobox/table facts under the reader at the 12k budget. Tag-strip and
  `reader-precision` keep more of them but include more navigation noise.
- The tutorial loses code-adjacent answers (2/4 for reader vs 3/4 for
  tag-strip/Stagehand innerText); the range() and default-argument facts are in
  code blocks.
- The synthetic SPA raw shell has almost no text; the rendered DOM path is
  required (the `/web-loader` path already uses rendered HTML).
- XBRL table numbers are present in table mode but the evidence-phrase proxy
  scores 0/4 for some extractors because the numbers are in separate cells;
  this is a metric artifact, not necessarily a content loss. Plan 17/09 will
  use table-aware checks.

## Reproduction

```bash
.venv/bin/python scripts/bench_reader.py --runs 3 \
  --json /tmp/bench-baseline3.json --markdown /tmp/bench-baseline3.md
```

Data source: `/tmp/bench-baseline3.json` from the run above; the committed
fixtures and their hashes are in `tests/fixtures/manifest.json`. The output is
not committed as a large artifact; rerun the command to reproduce.

## Limitations

- No LLM-graded answers in this run; "facts" is evidence-token presence.
- P/R uses a full reference; a 12k budget necessarily lowers recall on large
  pages.
- The corpus is 21 fixtures, not a random sample of the web; synthetic
  product/listing/paywall/challenge/SPA fixtures are labelled.
- The `reader-no-tables` proxy win on table pages is not actionable.
- The PDF, paywall, and challenge rows are not real extraction comparisons.

## Next

1. Plan 05 (observability), then plan 06-07 (regression/gateway tests).
2. Plan 08 page types, plan 09 structured content/header, plan 10 budgets.
3. Re-run this benchmark after each kept change and update the winner table;
   supersede this note rather than editing old numbers.
