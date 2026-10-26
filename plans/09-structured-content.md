# Plan 09 - Structured content preservation and context header

- **Workstream:** B2
- **Depends on:** plans 04, 08
- **Gate:** benchmark shows equal or better accuracy with no worse tokens; each
  sub-change is kept or reverted individually and logged.

## Goal

Give the agent the parts of a page that answers research questions (tables,
code, lists, comments) plus cheap context (title, headings, description,
canonical URL), and say clearly when content was left out.

## Changes

1. **Header (always, cheap):** prepend title, h1, meta description and
   canonical URL when present and non-duplicate. Cap title/description length;
   strip tracking query parameters from the canonical URL. Do not duplicate a
   heading already at the start of the body.
2. **Tables:** preserve data tables as readable Markdown/GitHub pipe tables
   (escape pipes, keep header separator, handle simple colspan/rowspan
   predictably). Keep the existing table-first recovery for pages where
   trafilatura returns little, but generalize it from "XBRL" to "structured
   content" and include nearby title/context.
3. **Code blocks:** preserve fenced blocks and language class when available;
   never collapse indentation inside code.
4. **Lists:** preserve ordered/unordered lists and nested depth.
5. **Comments:** preserve comment text where the reader includes it; full
   thread structure is plan 14.
6. **Omission marker:** whenever content is dropped, collapsed or truncated,
   add one line saying what and how to get it, for example:
   - `[omitted 8,400 chars of navigation/footer; fetch the source URL for the full page]`
   - `[truncated at 12,000 chars; request max_chars=24000 or a query-focused excerpt]`
   - `[table mode: non-table context omitted; use the reader mode for narrative]`
   - `[N source links omitted by the link cap]` (plan 13).
   The marker is part of the budget; it must be accurate and not claim an
   option that does not exist yet.

## Method

- Add a structured extraction mode chosen by `page_type`: `table`-dominant
  pages and `xbrl` use table recovery, `tutorial`/`docs` favor code/list
  preservation, prose pages use reader with header.
- Run the benchmark before/after per page type (tokens, P/R, fact presence, QA
  if enabled). Keep the header separately from table/code changes so a
  regression can be reverted alone.
- If header adds tokens without accuracy benefit on a page type, drop it there
  or shorten it; log the decision.

## Tests

- Golden tests for header fields (title/h1/description/canonical), deduplication
  and tracking-parameter stripping.
- Table conversion: header row, numeric cells, pipes, colspan/rowspan, nested
  `<style>` removal.
- Code block fences/language/indentation; list nesting.
- Omission markers for truncation, table mode and source cap; marker length
  counted against the budget.
- Existing reader tests updated only where output intentionally changes;
  explain each in the plan note.

## Verification

```bash
.venv/bin/python -m pytest -q tests/test_reader.py tests/test_structured.py
.venv/bin/python scripts/bench_reader.py --runs 3
```

Acceptance: benchmark table in the plan note shows accuracy first and tokens
second; no page type regresses without a logged reason; default suite green.

## Risks / notes

- Header text is model-facing and repeated per page; keep it to a few lines.
- Table extraction can drop narrative context; the omission marker and reader
  mode are the escape hatch.
- Do not add finance-specific table rules; use generic structure signals.
