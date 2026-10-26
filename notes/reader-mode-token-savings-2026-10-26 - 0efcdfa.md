# Reader-mode web extraction: token efficiency and reliability

- **Date:** 2026-10-26
- **Original change:** [`0efcdfa`](https://github.com/d1p/secure-ai-research-agent/commit/0efcdfa) — reader-mode extraction and resilient sub-agents
- **Follow-up fixes:** [`3def9e7`](https://github.com/d1p/secure-ai-research-agent/commit/3def9e7) — reader core (`fa6e5b5`), table-first XBRL (`9e3dabf`), fetch hardening (`bba5dcf`/`3def9e7`)
- **Component:** `shared/reader.py`, `gateway/app.py`, `orchestrator/{api,agent}.py`, `browser/stagehand-server.mjs` (`/content`), Open WebUI `smart_web` / sub-agents
- **Measured on:** AI stack VM (10.0.0.210), live pages, `trafilatura==2.3.1`

## TL;DR

- The earlier **“same 12k budget” comparison was the wrong metric.** At a hard
  cap both methods simply fill the cap; it cannot show whether the reader is
  better. The useful metric is the **minimum budget that keeps all key facts**,
  plus the tokens needed at that budget.
- At equal key-fact recall the reader needs **1.5k vs 6k chars** on Wikipedia
  (**-75% tokens**) and **10k vs 16k chars** on GitHub (**-34%**). On clean docs
  (Python asyncio) the win is smaller (2.5k vs 3.5k chars, **-24%**) and at a
  fixed 12k cap the reader is slightly more expensive (+8%). There is no
  universal token win.
- The biggest fixes are for data-heavy pages: link compaction cuts the reader’s
  full Wikipedia output by **42%**, and table-first extraction returns the
  complete SEC R2 statement in **1,120 chars / 475 tokens** instead of a 12k
  tag-strip (**3,859 tokens**).
- Reliability fixes: trafilatura 2.3.x `deduplicate=True` was stateful and
  started returning empty output after repeated fetches; SEC now gets a
  descriptive User-Agent (403 -> 200); challenges are detected on rendered
  content; sub-agent iterations are hard-bounded at 40.
- Accuracy: **15/15 key facts** retained at the minimum budgets. SEC statement
  data is complete. StockAnalysis table data is preserved, but the ticker and
  market cap live outside the table and need a search/another source.

## What changed

| Area | Before | After |
|------|--------|-------|
| Reader implementation | `gateway/reader.py` + `orchestrator/reader.py` copies | one `shared/reader.py` copied into both images |
| Links | inline `[label](url)` for every citation | inline labels + one deduped `Sources:` footer |
| Fallback | tag-strip only when trafilatura returned empty | tag-strip when reader is <35% and <4k chars; table-first for data pages/XBRL |
| SEC XBRL | reader empty -> 12k tag-strip | detect IDEA/XBRL and return the statement table directly |
| trafilatura dedup | `deduplicate=True` (stateful) | `deduplicate=False` (stable across calls) |
| Output budget | 12k everywhere (60k orchestrator ceiling) | 12k default, 24k finance, 32k SEC; ceilings, not targets |
| SEC User-Agent | generic browser UA -> 403 | `FETCH_USER_AGENT` with contact -> 200 |
| Challenge detection | navigation text only; raw HTML skipped | raw HTML + rendered content + visible text |
| `http_fetch` payload | gateway JSON envelope forwarded | orchestrator unwraps to plain text |
| Sub-agents | 80 iterations, 12k builtin fetch cap | 40 iterations, 32k cap so loader budgets survive |
| Browser dependency | Stagehand pinned `zod` 4.4.3 | `zod` 4.6.7 override (GHSA-mrhx-c7xc-m3w5) |

## Methodology

Pages:

1. `https://en.wikipedia.org/wiki/Reddit` — citation-heavy article + infobox
2. `https://docs.python.org/3/library/asyncio-task.html` — clean technical docs
3. `https://github.com/open-webui/open-webui` — project README
4. `https://www.sec.gov/Archives/edgar/data/1713445/000171344526000100/R2.htm` — income statement (XBRL)
5. `https://stockanalysis.com/stocks/rddt/financials/` — JS/data-heavy financial page

Metrics:

- **Minimum budget for full recall:** smallest character budget at which all
  chosen key facts are present.
- **Tokens at 12k:** diagnostic only; a fixed cap hides information density.
- **Full-output link compaction:** inline vs sources vs none.
- **Tokens:** `tiktoken` `cl100k_base` as a proxy for DeepSeek’s tokenizer.
  Percentages are stable; absolute counts differ slightly.
- Old behavior: gateway regex tag-strip; Stagehand `body.innerText`.

## Token results

### Minimum budget for full key-fact recall (new reader vs old tag-strip)

| Page | Reader budget / tokens | Tag-strip budget / tokens | Token change |
|------|------------------------|---------------------------|--------------|
| Wikipedia / Reddit | **1,500 chars / 475 tok** | 6,000 chars / 1,924 tok | **-75%** |
| Python asyncio docs | **2,500 chars / 647 tok** | 3,500 chars / 852 tok | **-24%** |
| GitHub README | **10,000 chars / 2,286 tok** | 16,000 chars / 3,461 tok | **-34%** |

Reader facts at those budgets: 5/5, 5/5, 5/5. The tag-strip needs 4x, 1.4x and
1.6x the budget respectively. This is the comparison that matters.

### Fixed 12k budget (diagnostic, not a value claim)

| Page | Reader @12k | Tag-strip @12k | Change | Reader facts | Tag facts |
|------|-------------|----------------|--------|--------------|-----------|
| Wikipedia / Reddit | 3,242 tok | 3,467 tok | -6.5% | 5/5 | 5/5 |
| Python asyncio docs | 2,911 tok | 2,702 tok | +7.7% | 5/5 | 5/5 |
| GitHub README | 2,834 tok | 2,547 tok | +11.3% | **5/5** | 4/5 |
| SEC R2 (table) | **475 tok** | 3,859 tok | **-87.7%** | 5/5 | 5/5 (truncated) |
| StockAnalysis (table) | 923 tok | 1,872 tok | -50.7% | 3/5 | 4/5 |

At a fixed budget the reader is not automatically cheaper on clean prose. It
wins by **what occupies the budget** (article instead of navigation), by
**link compaction**, and by **table extraction** on data pages.

### Link compaction (full output, no truncation)

| Page | Inline links | Sources mode | Change | No links | Change |
|------|--------------|--------------|--------|----------|--------|
| Wikipedia / Reddit | 292,854 chars / 84,508 tok | 169,049 / 45,907 | **-45.7%** | 145,270 / 38,636 | -54.3% |
| Python asyncio docs | 56,847 / 13,609 | 47,273 / 11,263 | -17.2% | 44,241 / 10,448 | -23.2% |
| GitHub README | 15,885 / 3,761 | 15,518 / 3,636 | -3.3% | 14,438 / 3,331 | -11.4% |

Sources mode kept 60, 60 and 26 unique URLs respectively. It removes per-link
URL duplication while preserving citations.

### SEC XBRL

- **Raw HTML:** trafilatura returns empty. Table-first mode returns the complete
  R2 income statement in **1,120 chars / 475 tokens**.
- **Old 12k tag-strip:** 3,859 tokens, same numbers but with XBRL boilerplate and
  a truncated tail.
- **Full tag-strip:** 53,404 chars / 17,080 tokens.
- **Rendered Stagehand path:** now also table-first, `/web-loader` returned the
  same 1,120-char table (previously a 32k reader blob).
- **Narrative SEC filings** (10-K/10-Q HTML) do not carry the XBRL marker and
  still use the normal reader.

### Stagehand end-to-end (earlier run, old innerText vs new reader)

| Page | Old innerText (<=60k chars) | New reader @12k | Change |
|------|-----------------------------|-----------------|--------|
| Wikipedia / Reddit | ~15,500 tok | 3,242 tok | **-79%** |
| Python asyncio docs | 11,178 tok | 2,911 tok | **-74%** |
| GitHub README | 4,772 tok | 2,834 tok | **-41%** |
| SEC R2 | ~300 tok, table missing | 475 tok, table complete | +tokens, accuracy fixed |

### Sub-agent workload

The failed earlier Reddit run produced sub-agent outputs of **74k, 131k, 236k,
272k, 380k and 510k chars**. With per-fetch caps, table mode and the 40-iteration
hard bound, the worst case is now roughly the number of calls x the domain
budget, and the prompt asks for under 20 calls. The exact reduction depends on
prompt adherence; the previous estimate was **70-85%** fewer tool-output tokens.

## Accuracy results

| Page | Checked facts | Reader | Tag-strip |
|------|---------------|--------|-----------|
| Wikipedia / Reddit | Founded, Headquarters, Advance Publications, Steve Huffman, San Francisco | **5/5** | 5/5 |
| Python asyncio docs | asyncio, coroutine, await, TaskGroup, create_task | **5/5** | 5/5 |
| GitHub README | Open WebUI, Installation, Features, Docker, pip | **5/5** | 4/5 (@12k) |
| Total | 15 | **15/15** | 14/15 at 12k |

- SEC R2: Revenue `$804,905`, net income `$252,848`, operating income `$231,716`
  and the 2026/2025 columns survive in the table.
- StockAnalysis: Revenue, net income and gross profit survive; ticker and market
  cap do not (they are outside the table). Use `web_search` or the rendered page
  for those.
- Rendered StockAnalysis: headed Chrome received the data page; when a challenge
  is served (headless Chrome got “Just a moment…”), the extractor returns
  `needs_human` instead of junk.

## Reliability fixes found while measuring

1. **Stateful trafilatura dedup.** With `deduplicate=True`, repeated calls on
   the same Wikipedia HTML returned 292,854 chars, then 280,440, then **0** from
   the sixth call onward. The service would silently fall back to tag-strip,
   losing the reader benefits. `deduplicate=False` is stable across 10 calls.
2. **SEC User-Agent.** `Mozilla/5.0 (compatible; homelab-ai-stack/1.0)` -> 403;
   `homelab-ai-stack/1.0 (admin@debashis.xyz)` -> 200.
3. **Challenge detection.** Raw HTML and rendered content are checked for
   structural markers/titles; long articles that merely mention “captcha” are
   not flagged.
4. **Fetch failures and event-loop blocking.** Connect/read failures retry with
   backoff and return a clean 502 with the exception type instead of a 500
   traceback. trafilatura/lxml extraction now runs in a worker thread, so a
   1.5MB page cannot block health checks or concurrent fetches. After this,
   20/20 consecutive Wikipedia fetches succeeded (an earlier run failed 1/10).
5. **Payload wrapping.** The orchestrator no longer forwards the gateway JSON
   envelope to the model; it returns page text only.

## Recommendations (implemented)

1. Reader-vs-tag fallback heuristic — implemented (reader <35% and <4k chars).
2. SEC-compliant User-Agent — implemented via `FETCH_USER_AGENT`.
3. Per-domain caps — implemented (12k / 24k / 32k, ceilings).
4. Strip noise links — implemented (labels + deduped Sources).
5. Lower sub-agent iterations — implemented (80 -> 40).
6. Detect challenges on content — implemented (HTML + rendered + text).
7. Table-first XBRL — implemented (SEC R2/R4/R24 statement pages).
8. Stateful dedup removal — implemented (`deduplicate=False`).

## Remaining risks

1. **Non-table context is dropped in table mode** (ticker, market cap, narrative
   around a financial table). Use search or the reader path for those.
2. **Long narrative filings** can still hit the 32k SEC ceiling.
3. **Prompt adherence:** 40 iterations is a hard bound, not a token bound. A
   model that ignores the <20-call budget can still grow context.
4. **Table extraction is heuristic:** it chooses the most numeric tables and
   may miss small two-column tables or include a nearby data table.
5. **Challenge detection is signature-based;** a new challenge layout may need
   another marker.

## Reproduction

```bash
# One page, local HTML, key-fact recall at several budgets
.venv/bin/python scripts/measure_reader.py \
  --html /tmp/reddit.html --url https://en.wikipedia.org/wiki/Reddit \
  --facts "Founded|Headquarters|Advance Publications|Steve Huffman|San Francisco"

# Live SEC statement page (table-first)
.venv/bin/python scripts/measure_reader.py \
  --url https://www.sec.gov/Archives/edgar/data/1713445/000171344526000100/R2.htm \
  --facts "Revenue|804,905|252,848|231,716"
```

`scripts/measure_reader.py` prints full-output tokens, link-compaction savings,
the per-budget table, and the minimum budget for full recall. Install
`trafilatura==2.3.1` and `tiktoken` in the venv; without `tiktoken` it falls
back to a chars/4 estimate.

## Appendix: runtime notes

- Gateway memory is 512 MB (lxml + trafilatura); table-first XBRL avoids a large
  reader pass on statement pages.
- The gateway and orchestrator images build from the repo root and copy
  `shared/` so there is one reader implementation.
- Open WebUI runtime config after the fix: `subagents.max_iterations=40`,
  `web.fetch.max_content_length=32000`, `subagents.enable=true`,
  `subagents.background_enabled=false`, `subagents.max_concurrent=3`,
  `subagents.max_output=30000`.
- `browser/package.json` overrides Stagehand’s pinned zod with 4.6.7;
  `npm audit` reports 0 high vulnerabilities.
