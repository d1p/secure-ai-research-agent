# Plan 17 - Golden extraction tests, link compaction and challenge/paywall

- **Workstream:** C2/C3
- **Depends on:** plans 08-15 (finalize after the loader changes they enable)
- **Gate:** golden snapshots are deterministic and reviewable; challenge/paywall
  positives and negatives pass; `needs_human` never leaks junk.

## Goal

Freeze the extraction behavior that the benchmark selected, and prove the
loader distinguishes a challenge/paywall from an article that merely talks
about one.

## Golden tests

- One golden output per fixture for the adopted extractor(s), stored under
  `tests/golden/<fixture>/<config>.md` (gzip above 200 KB). Include the
  trafilatura/lxml/config versions and fixture hash in a header.
- Normalise line endings and trailing whitespace only; do not normalise away
  meaningful structure.
- `UPDATE_GOLDEN=1 pytest ...` regenerates intentionally; a diff is reviewed
  before commit. A guard test fails if the fixture or config version changes
  without a golden update.
- Golden coverage: reader output, link compaction (sources/inline/none), table
  output, code blocks, header fields, omission markers, thread output.
- Fallback boundary tests: just below, at and above `READER_MIN_RATIO=0.35`,
  `READER_FALLBACK_MIN_CHARS=800`, `READER_FALLBACK_MAX_CHARS=4000`; assert the
  chosen method and that fallback does not fire for long articles.
- Link URL-count preservation test (plan 13) lives here too if not already in
  `test_links.py`.

## Challenge/paywall tests

Positive and negative cases on:

- raw HTML,
- rendered content (where the fixture has `rendered.html`),
- visible text.

Cases:

- Cloudflare/bot challenge (title, structural markers, phrases) -> positive;
  article about CAPTCHA/challenges -> negative.
- Cookie wall/consent overlay -> positive only when it blocks the content;
  recipe/shop page with a cookie banner but visible content -> negative.
- Paywall overlay/subscribe wall -> positive; article discussing paywalls or a
  page with a subscribe link but full content -> negative.
- Login wall -> positive if content is replaced; otherwise negative.

Assertions:

- `ReaderResult.challenge` / `reason` is correct.
- The returned text is a short, clean `[needs_human]`/paywall message, never the
  challenge/paywall HTML or a long junk blob.
- Gateway returns `needs_human` and audits the reason.
- No hidden/invisible challenge text leaks into a normal article output.

## Verification

```bash
.venv/bin/python -m pytest -q tests/test_golden.py tests/test_challenge_paywall.py
.venv/bin/python -m pytest -q
```

Acceptance: all golden/challenge tests pass; every golden diff is intentional;
default suite offline and green.

## Risks / notes

- Golden tests are brittle across trafilatura upgrades by design; the version
  header makes the cause explicit. Update deliberately, with a benchmark run.
- Signature-based challenge detection can miss a new layout; adding a new
  pinned sample is a fixture change, not a hotfix.
- Paywall detection must not become a way to drop pages that just have a
  subscribe link; the negative tests are mandatory.
