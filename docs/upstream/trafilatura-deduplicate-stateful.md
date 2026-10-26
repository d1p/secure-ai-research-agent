# trafilatura stateful `deduplicate=True` (draft issue, not posted)

Status: draft; do not post without review. See `decision.md` and
`notes/reader-mode-token-savings-2026-10-26.md`.

## Environment

- trafilatura 2.3.1
- Python 3.13
- lxml 6.1.3

## Problem

With `deduplicate=True`, repeated `trafilatura.extract()` calls on the **same**
HTML string appear to share state: output shrinks and can become empty after
several calls. A service that calls the extractor repeatedly then silently
falls back to a tag-strip, losing the reader benefits.

## Minimal repro

```bash
.venv/bin/python scripts/repro_trafilatura_dedup.py \
  --fixture docs-reference --calls 10
```

Measured on `docs-reference` (8 calls, trafilatura 2.3.1):

| call | deduplicate=True | deduplicate=False |
|---:|---:|---:|
| 1-3 | 56,913 chars | 56,913 chars |
| 4-6 | 41,591 chars | 56,913 chars |
| 7-8 | 0 chars | 56,913 chars |

The script prints the character count and hash of each extraction.

## Expected

`extract()` should be a pure function of its inputs; repeated calls on identical
HTML should return identical output.

## Workaround

Use `deduplicate=False` when the same document may be extracted more than once;
deduplicate links/sources outside the extractor.

## Notes

- The workaround is deployed in `shared/reader.py`.
- Re-check on a trafilatura upgrade; add a regression test if upstream changes.
