# Plan 15 - PDF and non-HTML content types

- **Workstream:** B6
- **Depends on:** plans 08-10
- **Gate:** PDF text with page markers; scanned/encrypted PDF returns a clean
  message; binary garbage is rejected without reaching the model; non-English
  text decodes correctly.

## Goal

Handle the content types research agents actually meet, with clean failure
modes instead of HTML parsing binary data.

## Content classification

Add a small classifier based on `Content-Type` **and** magic bytes:

- HTML/XHTML: `text/html`, `application/xhtml+xml`, `<!doctype html`, `<html`.
- PDF: `application/pdf` or `%PDF-` magic.
- Plain text: `text/plain`, `text/markdown`, `text/csv`, `application/json`,
  `application/xml`, `text/xml`.
- Unknown binary: NUL bytes or undecodable bytes above a threshold, or a
  content-type not in the list.
- Images/media: clean "not text" message; no OCR and no base64 dump.

Use the HTTP charset when present, then meta charset, then UTF-8 with
replacement. Record the chosen encoding and replacement count.

## PDF extraction

- Use `pypdf` (new runtime dependency; logged in `decision.md`).
- Extract per page and join with `\n\n[page N]\n`; keep the page count and a
  `[pages M-N of T]` marker when truncated by budget.
- Encrypted PDF: return `[pdf encrypted: password required; not loaded]`.
- No extractable text (scanned/image PDF): return
  `[pdf has no extractable text; OCR is not supported]` plus page count.
- Corrupt PDF: return a clean error with exception type; never a traceback.
- Run extraction in the worker thread already used for HTML; keep the gateway
  responsive.

## Non-HTML text

- JSON/XML/CSV/plain text: return as text with the page-type budget and
  truncation marker; do not tag-strip.
- Very large text: budget and marker; no NUL bytes.

## Tests (`tests/test_content_types.py`)

- arXiv PDF fixture: page markers, key facts from at least two pages, budget.
- Scanned/no-text PDF: clean message; no junk.
- Encrypted PDF: clean message.
- Binary garbage (random bytes, PNG header): clean rejection, no model-visible
  junk.
- Plain text/JSON/CSV: passthrough with budget.
- Charset: non-English UTF-8 and a declared ISO-8859-1 sample.
- Gateway route uses the classifier; content-type wins over URL suffix.

## Verification

```bash
.venv/bin/python -m pytest -q tests/test_content_types.py
.venv/bin/python -m pytest -q
```

Acceptance: all content-type tests pass; PDF page markers and facts present;
binary never reaches the model; default suite green.

## Risks / notes

- `pypdf` does not OCR; state that limitation in the output and docs.
- Adding `pypdf` to the gateway image is a deliberate runtime dependency; log
  size/reason and keep it lazy-imported.
- Content-type spoofing: magic bytes take precedence for PDF/HTML; still enforce
  the SSRF/security boundary before parsing.
