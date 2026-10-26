# Plan 01 - Benchmark corpus

- **Workstream:** A1
- **Depends on:** none
- **Gate:** fixture manifest validates, all fixtures are offline-readable, and
  no fixture contains emails, phone numbers, private IPs or internal hostnames.

## Goal

Create a small, pinned, license-aware corpus that represents the research
loader's real inputs. Everything after this is judged on this corpus.

## Corpus

21 fixtures. Each fixture has one primary `page_type` plus tags. Real captures
are preferred where the license is clear; license-risky categories use
synthetic pages with realistic structure and are marked `synthetic: true`.

| Slug | Primary type | Source strategy |
|---|---|---|
| `wikipedia-encyclopedia` | encyclopedia | Wikipedia oldid permalink |
| `news-public-domain` | news | public-domain government/agency release |
| `blog-longform-cc` | blog | long-form post with an explicit CC license |
| `docs-reference` | docs | official API/reference docs with a clear license |
| `tutorial-code` | tutorial | official tutorial with code blocks |
| `forum-hackernews` | thread | Hacker News thread |
| `qa-stackoverflow` | thread | Stack Overflow Q&A (CC BY-SA) |
| `github-readme` | docs (tag `github_readme`) | README of a permissively licensed repo |
| `github-issue` | thread | issue thread from the same repo |
| `paper-arxiv-html` | paper | arXiv HTML for a CC-licensed paper |
| `paper-arxiv-pdf` | pdf | the same paper as PDF |
| `product-reviews` | product | synthetic product page with reviews |
| `listing-search` | listing | synthetic search/listing page |
| `spa-rendered` | spa | public docs SPA; raw shell + rendered DOM |
| `data-table` | table | public-domain/bulk data table page |
| `xbrl-statement` | table | one SEC IDEA/XBRL statement page |
| `paywall-cookie` | paywall | synthetic cookie/paywall overlay |
| `challenge-bot` | challenge | synthetic bot-challenge page |
| `captcha-mention` | article | long page that merely mentions CAPTCHA |
| `non-english` | article | Wikipedia oldid in a non-English language |
| `large-page` | article | Wikipedia oldid with >1 MB raw HTML |

A synthetic fixture records `synthetic: true`, `modeled_on` (public URL or
"observed structure"), and "no source license; synthetic test data" in meta.
Real captures record the exact source URL, capture date, license and method.

## Fixture layout

```
tests/fixtures/
  README.md                 # license matrix, capture policy, synthetic list
  manifest.json             # generated; sha256 + required fields
  <slug>/
    meta.json               # url/oldid, captured_at, license, type, tags,
                            # synthetic, capture_method, content_type, sha256,
                            # bytes_raw, bytes_removed, innertext_source
    page.html               # or page.html.gz when > 250 KB
    innertext.txt           # captured body.innerText (Stagehand path)
    rendered.html           # only for SPA/challenge fixtures
    page.pdf                # only for the PDF fixture
```

- Wikipedia is pinned with an oldid permalink; the revision id is recorded.
- `innertext.txt` comes from the browser service's `/read` (or, when the
  browser is unavailable, lxml `text_content`; `innertext_source` records
  which, and the benchmark labels non-browser captures).
- Pages over 250 KB are stored gzipped; the >1 MB fixture must remain >1 MB
  uncompressed. No fixture is silently truncated to fit a budget.
- `scripts/capture_fixtures.py` (network, explicit `--allow-network`) captures
  by slug, scrubs PII, removes third-party analytics and base64 images over
  50 KB, records bytes removed, writes meta, and regenerates `manifest.json`.
  It is never run by the default test suite or CI.

## License and privacy rules

- Prefer public domain, CC, PSF, OSS and government sources. For copyrighted
  pages, store only the trimmed excerpt needed for structure; record why.
- Synthetic fixtures are used where a real capture's license is unclear:
  product/reviews, paywall/cookie wall, bot challenge, search listing.
- The capture script redacts emails, phone numbers, private IP ranges and
  internal hostname suffixes in stored HTML/text with `[redacted-*]` markers,
  and fails if a pattern remains.
- A fixture test checks the manifest, hashes, decompression, required fields,
  allowed page types, at least one >1 MB page, at least one PDF, and the absence
  of the redaction violations. It also asserts the fixture set covers every
  required category.

## Steps

1. Add `tests/fixtures/` layout, `scripts/capture_fixtures.py`, and
   `tests/fixtures/README.md`.
2. Capture the real fixtures with pinned oldids/URLs; create the synthetic
   fixtures; record meta for every file.
3. Generate `manifest.json`; add `tests/test_fixtures.py`.
4. Verify offline. If a source changes or disappears, the pinned copy is the
   fixture; do not silently refresh it.

## Verification

```bash
.venv/bin/python -m pytest -q tests/test_fixtures.py
.venv/bin/python -m pytest -q
```

Acceptance: all fixture tests pass; no network is used; every required category
is present; no fixture contains a real email, phone number, private IP or
internal hostname.

## Risks / notes

- License analysis is not legal advice; unclear sources become synthetic rather
  than being copied wholesale.
- A synthetic challenge page may not match tomorrow's real challenge markup;
  plan 17 keeps separate positive/negative cases and the capture policy allows
  adding a new pinned real sample later.
- Large fixtures grow the repo; gzip and the pre-commit large-file limit are
  configured in plan 20.
