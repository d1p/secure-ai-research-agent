---
title: <short descriptive title>
date: YYYY-MM-DD
status: draft|verified|superseded
commit_tested: <short or full hash>
environment: <Python, parser versions, tokenizer, machine/service>
---

# <title>

## TL;DR

- What changed.
- What was measured (numbers, tokenizer, run count).
- Limitations and any page type where the new loader is worse.
- What was **not** measured.

## Method

- Corpus/fixtures and versions:
- Tokenizer:
- Runs and budgets:
- Grading (if any):

## Results

<table per page type; include precision/recall/tokens and spread>

## What changed

<separate behavior changes from measurements>

## Reproduction

```bash
<exact command>
```

Data source: <file/JSON; fixtures are committed>.

## Limitations / rejected options

- <estimate labels, corpus scope, metric caveats>
