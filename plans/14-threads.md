# Plan 14 - Thread/forum mode

- **Workstream:** B5
- **Depends on:** plans 08-10
- **Gate:** benchmark shows equal or better accuracy on thread fixtures with
  lower tokens; no loss of accepted answers or author/order context.

## Goal

Turn forum/Q&A pages into readable threads instead of either a flat blob or a
reader that drops comments.

## Output

```markdown
## Thread: <title>
- @author (depth 0, score 42, time): comment text
  - @reply (depth 1): ...
```

- Keep author, order and nesting depth.
- Collapse deleted/removed comments to one marker; drop low-signal comments
  (for example `+1`, "thanks", empty, repeated boilerplate) only when they carry
  no answer; record dropped count.
- Dedupe quoted text that repeats an ancestor; keep a short `> quote` marker
  when the quote is needed to understand a reply.
- Cap comments/thread by budget; add `[N comments omitted; fetch with
  offset/query or open the source thread]` and keep the highest-signal comments
  (accepted answer, high score, ancestors of answers) rather than the first N.
- Preserve code blocks and tables inside comments.

## Detection/parsing

Use `page_type=thread` and generic container heuristics first:

- HN: `tr.athing.comtr`, `.commtext`, `.hnuser`, `.age`, indent width.
- Stack Overflow: `.question`, `.answer`, `.comment`, accepted-answer marker,
  author/time.
- Generic: repeated `article`/`[class*=comment]`/`[data-testid*=comment]` with
  author/time; fall back to reader if structure is unclear.

No finance-specific rules. If structure is not confident, return the reader
output with a `[thread structure not detected]` marker rather than inventing
order.

## Tests (`tests/test_threads.py`)

- HN fixture: author/order/depth; deleted comment collapsed; accepted/high
  score kept.
- Stack Overflow fixture: question + accepted answer + comments; author/time.
- Quoted text dedupe.
- Low-signal collapse with dropped-count marker.
- Cap keeps high-signal comments and reports omission.
- Generic malformed thread falls back safely.
- Code block inside a comment preserved.
- Budget respected.

## Verification

```bash
.venv/bin/python -m pytest -q tests/test_threads.py
.venv/bin/python scripts/bench_reader.py --fixtures forum-hackernews,qa-stackoverflow,github-issue --runs 3
.venv/bin/python -m pytest -q
```

Acceptance: accuracy/fact presence on thread fixtures not worse; tokens lower
or equal; default suite green.

## Risks / notes

- Thread extraction is brittle across sites. Prefer fallback over wrong order.
- Deleting "low signal" can remove the only answer; keep the rule conservative
  and test against ground truth.
- The XBRL/finance fixture is not a thread; do not reuse financial table logic.
