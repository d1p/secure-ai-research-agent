# Reader-loader optimization: plan index and summary

- **Status:** implemented in the working tree (2026-10-26); not committed.
  See `notes/reader-loader-final-2026-10-26.md` for measured results and
  `decision.md` for deferred items (live A/B, LLM grading, CI execution,
  browser-path cache).
- **Scope:** general-purpose research loader (`shared/reader.py`, gateway,
  orchestrator, browser `/content`), its benchmark, tests, observability,
  workflow and documentation.
- **Decision log:** `decision.md` (created for this work).

## Goal

Maximise answer accuracy per token for open-ended research pages (news, docs,
papers, forums, products, reference, data), across every page type, with a
corpus and harness that make every change measurable. Finance/XBRL is one
fixture category, not a special workstream.

## Baseline measured at HEAD `8d51cf3`

| Check | Result |
|---|---|
| `.venv/bin/python -m pytest -q` | **104 passed** |
| `.venv/bin/ruff check .` | clean |
| `.venv/bin/ruff format --check .` | 16 files would be reformatted (pre-existing; plan 20) |
| Python / trafilatura / lxml | 3.13.5 / 2.3.1 / 6.1.3 |

`agent.md` and `decision.md` were absent at HEAD. `decision.md` now exists;
repo guidance used was `README.md` plus the host-level `AGENTS.md`. Confirm
whether a separate `agent.md` exists before execution.

## Execution order and gates

Each plan is independently testable and must pass its verification before the
next starts. A/D come first, then C regression, then B one change at a time,
then the expanded C tests, the end-to-end A/B, and E/F.

| # | Plan | Workstream | Gate |
|---|---|---|---|
| 01 | [Corpus](01-corpus.md) | A1 | manifest validates; fixtures offline; no PII |
| 02 | [Ground truth](02-ground-truth.md) | A2 | 3-5 Qs/fixture; references hand-marked |
| 03 | [Benchmark harness](03-benchmark-harness.md) | A3 | offline run; per-page-type output |
| 04 | [Baseline comparison](04-baseline-comparison.md) | A4 | winner per page type logged |
| 05 | [Observability counters](05-observability.md) | D | counters/log/audit tested; dashboard parses |
| 06 | [Regression stability](06-regression-stability.md) | C1 | 20+ repeats stable; markers default-fail-safe |
| 07 | [Gateway/orchestrator tests](07-gateway-orchestrator-tests.md) | C5/C6 | retry, 502, off-loop, SSRF redirect, envelope |
| 08 | [Page-type detection](08-page-types.md) | B1 | misclassification measured; no blind routing |
| 09 | [Structured content](09-structured-content.md) | B2 | header/tables/code/lists + omission markers |
| 10 | [Page-type budgets](10-budgets.md) | B3 | ceilings measured; no finance-specific logic |
| 11 | [Fetch/extraction cache](11-cache.md) | B7 | TTL/no-store/revalidation/hit-rate tested |
| 12 | [Progressive loading](12-progressive-loading.md) | B3 | fewer total tokens at equal/better accuracy |
| 13 | [Link policy](13-links.md) | B4 | URL preservation; nav/footer/cookie links stripped |
| 14 | [Thread/forum mode](14-threads.md) | B5 | author/order/depth; junk collapsed |
| 15 | [PDF/non-HTML](15-pdf-nonhtml.md) | B6 | PDF page markers; binary rejected cleanly |
| 16 | [Sub-agent output budget](16-subagent-budget.md) | B8 | cumulative cap + forced summarize tested |
| 17 | [Golden + challenge/paywall tests](17-golden-challenge-tests.md) | C2/C3 | deterministic snapshots; no junk leaks |
| 18 | [Property/fuzz + injection tests](18-property-injection.md) | C4/C7 | never raises; hidden text stripped/wrapped |
| 19 | [End-to-end A/B](19-e2e-ab.md) | A5 | N runs, same conditions; estimates replaced |
| 20 | [Workflow tooling](20-workflow.md) | E1-E4 | make/pre-commit/CI/privacy checker pass |
| 21 | [Docs + upstream draft](21-docs-and-upstream.md) | F/E5 | layout/front matter/entries; PII scrub passes |

## How success is judged

1. Answer accuracy first, then tokens/cost. A change is kept only if the
   corpus benchmark (and, for agent-level claims, the A/B) supports it;
   otherwise it is reverted and logged in `decision.md`.
2. Every reported number has a reproduction command, data source, tokenizer and
   environment. Estimates are labelled as estimates. Comparisons use the same
   run and conditions.
3. Metrics are reported per page type, not as one aggregate. Precision/recall
   is reported alongside tokens; a metric that only measures where facts sit in
   a page is not headlined.
4. Tests stay fast and offline by default; network, LLM-graded and slow tests
   are marked and opt-in.
5. No secrets, personal emails, internal IPs or internal hostnames are added.
   Existing tracked infra values are parameterised in plan 21.

## Non-goals and guardrails

- No finance-specific logic. XBRL is one data-table fixture and one page type.
- No unmeasured claims. Unrun end-to-end work stays labelled "not measured".
- No loader change without a benchmark result and a decision-log entry.
- No production dependency without a logged reason and a fallback path.
- No commits until the user asks; one logical change per commit once approved.

## Approval needed

1. Approve the corpus/licensing strategy, especially synthetic fixtures for
   product, paywall, challenge and listing pages.
2. Approve running the end-to-end A/B on the live VM with provider credentials
   (plan 19). If not approved, it stays "not measured".
3. Confirm whether an `agent.md` exists outside the repo.
