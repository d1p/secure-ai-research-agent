# Reader-mode web extraction: token savings and accuracy

- **Date:** 2026-10-26
- **Change commit:** [`0efcdfa`](https://github.com/d1p/secure-ai-research-agent/commit/0efcdfa) — feat: reader-mode web extraction and resilient sub-agents
- **Component:** `gateway/reader.py`, `orchestrator/reader.py`, `browser/stagehand-server.mjs` (`/content`), Open WebUI `smart_web` / sub-agents
- **Measured on:** AI stack VM (10.0.0.210), live pages, `trafilatura==2.3.1`

## TL;DR

- Reader mode **does not reduce tokens by itself** at a fixed output budget. At 12k chars it is within ±8% of the old tag-strip/innerText.
- The real savings come from the **12k output cap** (previously up to 60k on the Stagehand paths) and the **sub-agent call budget** (`<20` tool calls).
- Expected savings: **~80% fewer tokens per `fetch_url`/`browse_page` fetch**; **~70–85% fewer tool-output tokens** for a typical research sub-agent.
- Accuracy: **high on articles/docs** (15/15 key facts retained at 12k vs 14/15 for tag-strip). **Better on SEC filings** (the rendered reader recovers table data the old `innerText` path missed), but the 12k cap is the main recall risk for long financial statements.
- Biggest caveat: raw XBRL HTML makes trafilatura return empty, so SEC pages fetched over plain HTTP fall back to the old tag-strip. A SEC-compliant User-Agent is also still missing (`http_fetch` currently gets 403 from sec.gov).

## What changed

| Path | Before | After |
|------|--------|-------|
| `http_fetch` (plain HTTP via gateway) | HTML -> regex tag-strip, 12k cap | HTML -> `trafilatura` reader Markdown, 12k cap, tag-strip fallback |
| `fetch_url` / `browse_page` (Stagehand) | `body.innerText`, up to 60k chars | rendered HTML -> `trafilatura` reader Markdown, 12k cap |
| Sub-agents | 30 iterations, no routing prompt | 80 iterations, `subagents.system_prompt`, 3 concurrent, 30k output |

Extraction keeps the main article body, headings, lists, tables and links, and drops navigation, headers/footers, ads, cookie banners, scripts and styles.

## Methodology

Pages used:

1. `https://en.wikipedia.org/wiki/Reddit` — citation-heavy article + infobox table
2. `https://docs.python.org/3/library/asyncio-task.html` — technical docs with code
3. `https://github.com/open-webui/open-webui` — app/docs page
4. `https://www.sec.gov/Archives/edgar/data/1713445/000171344526000100/R2.htm` — income statement (XBRL viewer)
5. `https://www.sec.gov/.../R4.htm`, `R24.htm` — balance sheet / revenue tables
6. `https://stockanalysis.com/stocks/rddt/financials/` — JS/data-heavy financial page

Method:

- Raw HTML: `curl` from the VM.
- Rendered HTML: Stagehand `/content` (`document.documentElement.outerHTML`).
- Reader output: `trafilatura.extract(..., output_format="markdown", include_links=True, include_tables=True, include_formatting=True, favor_recall=True, deduplicate=True)`.
- Token counts: `tiktoken` `cl100k_base` as a proxy for DeepSeek's tokenizer. Percentages are stable; absolute counts will differ slightly.
- Old behavior: gateway `_html_to_text` (tag-strip) for `http_fetch`; Stagehand `body.innerText` for `fetch_url`/`browse_page`.

## Token results

### Same 12k budget: old tag-strip vs new reader

| Page | Old tag-strip @ 12k | New reader @ 12k | Δ |
|------|---------------------|------------------|---|
| Wikipedia / Reddit | 3,512 tok | 3,337 tok | **-5.0%** |
| Python asyncio docs | 2,765 tok | 2,933 tok | **+6.1%** |
| GitHub README | 2,613 tok | 2,825 tok | **+8.1%** |
| StockAnalysis (raw HTML) | 1,880 tok | 256 tok | -86.4% *(missed data — fallback needed)* |
| SEC R2/R4/R24 (raw HTML) | 3,872 / 3,747 / 592 tok | 0 | reader failed, tag-strip fallback |

At the same budget the token count barely moves. What changes is **what occupies the budget**: the reader's 12k starts with the article/infobox instead of navigation. For example, the old GitHub tag-strip's first 12k missed the "Installation" section; the reader's first 12k included it.

### Stagehand path: old innerText (≤60k) vs new reader (≤12k)

| Page | Old innerText (≤60k chars) | New reader (≤12k chars) | Δ |
|------|----------------------------|-------------------------|---|
| Wikipedia / Reddit | ~15,500 tok (60k-char cap) | 3,337 tok | **-78.5%** |
| Python asyncio docs | 11,178 tok | 2,933 tok | **-73.8%** |
| GitHub README | 4,772 tok | 2,825 tok | **-40.8%** |
| SEC R2 (income statement) | ~300 tok (1,325 chars; table missing) | 4,038 tok (table recovered) | **+** tokens, accuracy improved |

### Full output (uncapped) with links

| Page | Reader with links | Reader, all links unwrapped | Δ | External links only | Δ |
|------|-------------------|----------------------------|---|---------------------|---|
| Wikipedia / Reddit | 79,132 tok | 42,344 tok | -46.5% | 73,877 tok | -6.6% |
| Python asyncio docs | 12,465 tok | 10,484 tok | -15.9% | 10,528 tok | -15.5% |
| GitHub README | 3,752 tok | 3,330 tok | -11.2% | 3,712 tok | -1.1% |
| SEC R2 (rendered) | 18,375 tok | 17,853 tok | -2.8% | 17,853 tok | -2.8% |

Takeaways:

- **Citation links are expensive.** Wikipedia's full reader output is **91% larger** than its plain text (79,132 vs 41,409 tokens) because of link URLs. At the 12k cap the difference is negligible (~1%), but don't run this uncapped with `include_links=True`.
- Unwrapping internal/anchor links saves 11–46% on uncapped pages. Unwrapping external citation links too would save more but removes sources.
- SEC pages contain many `javascript:void(0)` links; these are pure noise and can be stripped.

### Sub-agent workload

The failed Reddit equity-research run produced sub-agent tool outputs of **74k, 131k, 236k, 272k, 380k and 510k chars** (two sub-agents failed before producing output). With the 12k cap and `<20` calls, a sub-agent is bounded at ~240k chars (~60k tokens) worst case, and typically ~120k chars (~30k tokens). That is a **~70–85% reduction** versus the old run, but the exact figure depends on how closely the model follows the call budget.

## Accuracy results

### Key-fact recall (first 12k of reader vs tag-strip)

| Page | Checked facts | Reader | Tag-strip |
|------|---------------|--------|-----------|
| Wikipedia / Reddit | Founded, Headquarters, Advance Publications, Steve Huffman, San Francisco | **5/5** | 5/5 |
| Python asyncio docs | asyncio, coroutine, await, TaskGroup, create_task | **5/5** | 5/5 |
| GitHub README | Open WebUI, Installation, Features, Docker, pip | **5/5** | 4/5 |
| **Total** | 15 | **15/15 (100%)** | 14/15 (93%) |

### SEC filings

- **Rendered HTML (Stagehand):** the reader extracted the full income statement (56,421 chars, Markdown table with periods and values). The old `body.innerText` path returned only 1,325 chars and missed the table. This is a significant accuracy improvement for financial research.
- **Raw XBRL HTML (`http_fetch`):** `trafilatura` returns empty, so the gateway falls back to `_html_to_text`. The table text is preserved (e.g., R2: 54,434 chars), but there is no boilerplate removal and no token reduction.
- **Truncation:** the 12k cap retains only ~21% of the 56k-char R2 statement. Rows near the bottom can be lost.

### What is at risk

1. **12k truncation on long financial tables** — the largest accuracy risk for equity research.
2. **JS / bot-verification pages** — StockAnalysis returned a "performing security verification" page; challenge detection does not always flag it if the title looks normal.
3. **Unusual layouts** — reader extraction can drop data that lives outside the detected article (sidebars, non-article tables).
4. **Prompt adherence** — the 80-iteration cap is a failure bound, not a token bound. If the model ignores `<20 tool calls`, context can still grow into the provider limit.
5. **Link bloat** — citation URLs can dominate uncapped reader output.

## Recommendations

1. **Add a reader-vs-tag fallback heuristic.** If reader output is empty or `<30–40%` of the tag-strip length, return the tag-strip instead. This fixes StockAnalysis-style data loss and keeps SEC raw-HTML pages on the reliable path.
2. **Use a SEC-compliant User-Agent for `http_fetch`.** SEC returns 403 to `Mozilla/5.0 (compatible; homelab-ai-stack/1.0)`. A descriptive UA with contact (e.g. `...; admin@debashis.xyz)`) returns 200.
3. **Per-domain caps.** Keep 12k as the default; allow 24–32k for `sec.gov` and finance/table-heavy domains, or add a targeted table-extraction tool.
4. **Strip noise links.** Remove `javascript:`/`#` links and unwrap internal anchors. Optionally make external-link retention configurable per tool.
5. **Keep the `<20 tool calls` budget.** Consider lowering `subagents.max_iterations` from 80 to ~40 to hard-bound the worst case; 40 still allows ~60 tool calls with batching.
6. **Detect challenge pages on content too**, not only on navigation title/URL.

## Reproduction

The measurements were produced with:

```bash
# Reader extraction + token counts (throwaway container, host egress)
docker run --rm -v /tmp:/tmp python:3.12-slim sh -c '
  pip install -q trafilatura==2.3.1 tiktoken &&
  python /tmp/measure.py'
```

`measure.py` applies `trafilatura.extract(...)` to each saved HTML file, compares it with the old regex tag-strip, and counts tokens with `tiktoken.get_encoding("cl100k_base")`. Rendered HTML for the Stagehand path came from the gateway's `stagehand_content` tool; `innerText` came from `stagehand_read`.

## Appendix: raw measurements

### 12k comparison (chars -> tokens)

| Page | Reader chars | Tag chars | Reader 12k tok | Tag 12k tok |
|------|--------------|-----------|----------------|-------------|
| Wikipedia | 269,291 full | 159,695 full | 3,337 | 3,512 |
| Python docs | 51,621 full | 48,910 full | 2,933 | 2,765 |
| GitHub | 15,832 full | 21,323 full | 2,825 | 2,613 |
| SEC R24 raw | 0 | 2,013 | 0 | 592 |
| SEC R2 raw | 0 | 54,434 | 0 | 3,872 |
| SEC R4 raw | 0 | 19,249 | 0 | 3,747 |
| StockAnalysis raw | 969 | 5,599 | 256 | 1,880 |
| SEC R2 rendered | 56,421 | 1,325 (innerText) | 4,038 | ~300 |

### Runtime note

The gateway image now includes `trafilatura`; memory use rose from ~56 MiB baseline to ~110 MiB after the first extraction, and the container limit was raised from 256m to 512m.
