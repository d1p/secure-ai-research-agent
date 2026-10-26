# Benchmarking

## Corpus

21 pinned fixtures in `tests/fixtures/` cover encyclopedia, news, blog, docs,
tutorial with code, HN/Stack Overflow threads, GitHub README/issue, arXiv HTML
and PDF, product, listing, SPA, data table, XBRL, paywall, challenge, CAPTCHA
mention, non-English and a >1 MB page. Synthetic fixtures are labelled.

## Metrics

- **Tokens:** tiktoken `cl100k_base` by default; `BENCH_DEEPSEEK_TOKENIZER`
  points at a `tokenizer.json` for the real tokenizer. Label every result.
- **Precision/recall:** word-multiset overlap against `reference.md`.
- **Evidence presence:** fraction of a question's evidence tokens present
  (>=80%). This is a cheap recall proxy, **not** answer accuracy; it can be
  satisfied by prose near a table.
- **LLM-graded accuracy:** optional `--grade`; answers with the page text, then
  grades against ground truth. Cached, network/LLM only. If not run, say
  "not measured".
- **Spread:** N runs; tokens/P/R min/median/max; identical output hashes should
  hold for deterministic extraction.

## Commands

```bash
.venv/bin/python scripts/bench_reader.py --runs 3 \
  --json /tmp/bench.json --markdown /tmp/bench.md
.venv/bin/python scripts/bench_reader.py --page-type-report
.venv/bin/python scripts/bench_reader.py --grade --runs 1 \
  --fixtures wikipedia-encyclopedia
```

## Agent-level A/B

`scripts/bench_ab.sh` restarts gateway/orchestrator with
`LOADER_VARIANT=legacy|new`, then runs `scripts/bench_agent.py` over
`tests/tasks/research.json`. It needs live services and credentials; report N,
model, wall time, usage (or "not measured"), success and variance. The legacy
variant is benchmark-only, not a supported deployment mode.

## Evidence rules

Same corpus, tokenizer, model and conditions for comparisons. Do not headline a
metric that only measures where facts sit in a page. Separate "what changed"
from "what we measured". Every note includes a reproduction command.
