# Benchmark fixtures

Pinned, trimmed pages used by the offline reader benchmark and tests. The
committed files are the source of truth; `scripts/capture_fixtures.py` refreshes
or adds fixtures only with `--allow-network`.

## What each fixture contains

```
<slug>/
  meta.json        source URL/oldid, capture date, license, type, tags, hashes
  page.html[.gz]   original HTML (gzipped above 250 KB)
  page.pdf         PDF fixture only
  rendered.html    SPA/challenge rendered DOM where applicable
  innertext.txt    visible-text baseline (lxml-visible-text or pdf-text)
  reference.md     hand-marked main content (curated selector + spot check)
  questions.json   3-5 ground-truth questions with evidence
```

`manifest.json` lists all metadata and hashes.

## Licenses

| Fixture | Source / license |
|---|---|
| `wikipedia-*` | Wikipedia, CC BY-SA 4.0, pinned oldid |
| `news-public-domain` | NASA press release, U.S. government work |
| `blog-longform-cc` | EFF Deeplinks, CC BY |
| `docs-reference`, `tutorial-code` | Python documentation, PSF license |
| `forum-hackernews` | Hacker News user content; excerpt for testing |
| `qa-stackoverflow` | Stack Exchange, CC BY-SA 4.0 |
| `github-readme`, `github-issue` | Repository content, Other/NOASSERTION; excerpt |
| `paper-arxiv-html`, `paper-arxiv-pdf` | arXiv non-exclusive distribution license 1.0; excerpt |
| `xbrl-statement` | Synthetic, modelled on public SEC IDEA/XBRL markup |
| `product-reviews`, `listing-search`, `paywall-cookie`, `challenge-bot` | Synthetic test data |
| `spa-rendered` | Synthetic raw shell + rendered DOM |

Real pages are stored as trimmed excerpts for testing; the source and capture
date are in `meta.json`. If a license is unclear, a synthetic page is used
instead. This is not legal advice.

## Capture policy

- Pin Wikipedia by oldid; store the revision id.
- Use a descriptive User-Agent from `FETCH_USER_AGENT`; never commit it.
- Redact emails, private/link-local IPs and phone-like strings in stored
  content. The test suite fails if a real email or private IP remains.
- Remove only third-party analytics scripts and very large data URIs; keep the
  DOM structure needed for challenge/SPA tests.
- Do not refresh a fixture silently. A refresh is a data change with a new
  capture date and review of the questions/reference.

## Adding a fixture

1. Add the source to `scripts/capture_fixtures.py` (pinned URL/oldid, selector,
   license).
2. Capture with `--allow-network --only <slug>`.
3. Add questions to `scripts/build_questions.py`, then run it.
4. Run `pytest -q tests/test_fixtures.py tests/test_ground_truth.py`.
5. Add the slug to `manifest.json` by re-running the capture or manifest step.

## Synthetic fixtures

Synthetic pages are labelled `synthetic: true` and say "No source license" in
`meta.json`. They exist for categories where storing a real page would be
license-risky (product/reviews, listing/search, paywall, bot challenge) and for
a controlled SPA raw-vs-rendered pair. They are realistic enough to test
structure, not to claim real-site coverage.
