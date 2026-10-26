#!/usr/bin/env python3
"""Offline reader benchmark.

Runs extractor/config candidates over the pinned fixture corpus and reports
tokens, main-content precision/recall, evidence presence and (optional)
LLM-graded answer accuracy per page type.

Examples:
  .venv/bin/python scripts/bench_reader.py --runs 3 --json /tmp/bench.json
  .venv/bin/python scripts/bench_reader.py --fixtures qa-stackoverflow \
      --extractors reader-default,tag-strip --runs 2
  .venv/bin/python scripts/bench_reader.py --grade --fixtures wikipedia-encyclopedia
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
for path in (ROOT, ROOT / "tests"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from fixture_utils import (
    load_innertext,
    load_meta,
    load_page_bytes,
    load_page_text,
    load_questions,
    load_reference,
)

from shared.reader import (
    ReaderConfig,
    _strip_tags,
    content_budget,
    detect_page_type,
    extract_pdf,
    read_html,
)

CACHE_DIR = ROOT / ".bench-cache"


@dataclass(frozen=True)
class ExtractResult:
    text: str
    method: str


def _tokenizer(name: str):
    if name == "chars4":
        return "chars/4 estimate", lambda text: len(text) // 4
    if name == "deepseek":
        path = os.environ.get("BENCH_DEEPSEEK_TOKENIZER", "")
        if not path or not Path(path).exists():
            raise SystemExit(
                "deepseek tokenizer requested but BENCH_DEEPSEEK_TOKENIZER is not set "
                "to a tokenizer.json file"
            )
        from tokenizers import Tokenizer

        tok = Tokenizer.from_file(path)
        return f"deepseek:{path}", lambda text: len(tok.encode(text).ids)
    import tiktoken

    enc = tiktoken.get_encoding("cl100k_base")
    return "tiktoken:cl100k_base", lambda text: len(enc.encode(text))


def _words(text: str) -> Counter[str]:
    import re

    return Counter(re.findall(r"[a-z0-9]+", text.lower()))


def _pr(extracted: str, reference: str) -> tuple[float, float]:
    got = _words(extracted)
    want = _words(reference)
    if not got or not want:
        return 0.0, 0.0
    common = got & want
    matched = sum(common.values())
    return matched / sum(got.values()), matched / sum(want.values())


def _truncate(text: str, budget: int | None) -> str:
    if not budget or len(text) <= budget:
        return text
    return text[:budget].rstrip() + "\n\n[content truncated]"


def _extract(name: str, slug: str, budget: int | None, top_n: int) -> ExtractResult:
    if slug.endswith("-pdf"):
        if name in {
            "reader-default",
            "reader-recall",
            "reader-precision",
            "reader-no-tables",
            "reader-comments",
            "reader-links-inline",
        }:
            result = extract_pdf(load_page_bytes(slug), budget)
            return ExtractResult(result.text, result.method)
        return ExtractResult("", "skipped:non-html")
    raw = load_page_text(slug)
    if load_meta(slug).get("page_type") == "spa":
        from fixture_utils import load_rendered

        raw = load_rendered(slug) or raw
    if name in {"readability", "tag-strip"} and not raw.strip():
        return ExtractResult("", "empty")
    if name == "reader-default":
        result = read_html(raw, load_meta(slug)["source_url"], budget)
        return ExtractResult(result.text, result.method)
    if name == "reader-recall":
        cfg = ReaderConfig(favor_recall=True, favor_precision=False)
        return ExtractResult(
            read_html(raw, load_meta(slug)["source_url"], budget, config=cfg).text,
            "reader-recall",
        )
    if name == "reader-precision":
        cfg = ReaderConfig(favor_recall=False, favor_precision=True)
        return ExtractResult(
            read_html(raw, load_meta(slug)["source_url"], budget, config=cfg).text,
            "reader-precision",
        )
    if name == "reader-no-tables":
        cfg = ReaderConfig(include_tables=False)
        return ExtractResult(
            read_html(raw, load_meta(slug)["source_url"], budget, config=cfg).text,
            "reader-no-tables",
        )
    if name == "reader-comments":
        cfg = ReaderConfig(include_comments=True)
        return ExtractResult(
            read_html(raw, load_meta(slug)["source_url"], budget, config=cfg).text,
            "reader-comments",
        )
    if name == "reader-links-inline":
        return ExtractResult(
            read_html(
                raw,
                load_meta(slug)["source_url"],
                budget,
                include_links="inline",
            ).text,
            "reader-links-inline",
        )
    if name == "readability":
        try:
            from markdownify import markdownify
            from readability import Document
        except ImportError:
            return ExtractResult("", "skipped:readability")
        try:
            summary = Document(raw).summary()
            text = markdownify(summary)
        except Exception:  # noqa: BLE001 - benchmark candidate
            text = ""
        return ExtractResult(_truncate(text, budget), "readability")
    if name == "tag-strip":
        return ExtractResult(_truncate(_strip_tags(raw), budget), "tag-strip")
    if name == "stagehand-innertext":
        return ExtractResult(
            _truncate(load_innertext(slug), budget), "stagehand-innertext"
        )
    raise SystemExit(f"unknown extractor: {name}")


def _fact_presence(text: str, slug: str) -> tuple[int, int]:
    """Count questions whose evidence tokens survive (bag of words, >=80%).

    This is a deterministic recall proxy, not answer accuracy: table rows and
    infoboxes can satisfy it without the answer being readable in order. LLM
    grading (`--grade`) is the accuracy metric when enabled.
    """
    import re

    questions = load_questions(slug)
    if load_meta(slug).get("expected_needs_human"):
        return 0, len(questions)
    got = Counter(re.findall(r"[a-z0-9]+", text.lower()))
    found = 0
    for q in questions:
        need = re.findall(r"[a-z0-9]+", q["evidence"].lower())
        if not need:
            continue
        hits = sum(min(got.get(word, 0), need.count(word)) for word in set(need))
        if hits / len(need) >= 0.8:
            found += 1
    return found, len(questions)


def _cache_path() -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / "grades.json"


def _grade(
    slug: str, extractor: str, text: str, model: str, enabled: bool, use_cache: bool
) -> dict[str, Any]:
    if not enabled:
        return {"status": "not_measured"}
    if load_meta(slug).get("expected_needs_human"):
        return {"status": "not_applicable"}
    import httpx

    base = os.environ.get("LITELLM_URL", "http://localhost:4000")
    key = os.environ.get("LITELLM_MASTER_KEY", "")
    cache = {}
    path = _cache_path()
    if use_cache and path.exists():
        cache = json.loads(path.read_text())
    correct = 0
    total = 0
    for q in load_questions(slug):
        ck = hashlib.sha256(
            f"{model}|{slug}|{extractor}|{q['id']}|{q['question']}|{text[:2000]}".encode()
        ).hexdigest()
        if use_cache and ck in cache:
            verdict = cache[ck]
        else:
            try:
                with httpx.Client(timeout=120.0) as client:
                    answer_prompt = (
                        "Answer the question using only the page text. If the answer "
                        "is not present, reply exactly NOT_FOUND. Keep it under 80 words.\n\n"
                        f"Question: {q['question']}\n\nPage text:\n{text[:60000]}"
                    )
                    answer = client.post(
                        f"{base}/v1/chat/completions",
                        headers={"Authorization": f"Bearer {key}"},
                        json={
                            "model": model,
                            "messages": [{"role": "user", "content": answer_prompt}],
                            "temperature": 0,
                        },
                    ).json()["choices"][0]["message"]["content"]
                    grade_prompt = (
                        "Grade the candidate answer against the ground truth. Reply "
                        "with exactly CORRECT or INCORRECT.\n\n"
                        f"Question: {q['question']}\nGround truth: {q['answer']}\n"
                        f"Candidate: {answer}"
                    )
                    verdict = client.post(
                        f"{base}/v1/chat/completions",
                        headers={"Authorization": f"Bearer {key}"},
                        json={
                            "model": model,
                            "messages": [{"role": "user", "content": grade_prompt}],
                            "temperature": 0,
                        },
                    ).json()["choices"][0]["message"]["content"]
                verdict = (
                    "CORRECT"
                    if verdict.strip().upper().startswith("CORRECT")
                    else "INCORRECT"
                )
            except Exception as exc:  # noqa: BLE001 - benchmark must not crash
                verdict = f"ERROR:{type(exc).__name__}"
            if use_cache:
                cache[ck] = verdict
                path.write_text(json.dumps(cache, indent=2))
        total += 1
        correct += verdict == "CORRECT"
    return {"status": "measured", "correct": correct, "total": total}


def _mean(values: list[float]) -> float:
    return round(statistics.fmean(values), 4) if values else 0.0


def _run(args) -> dict[str, Any]:
    tokenizer_name, count = _tokenizer(args.tokenizer)
    fixtures = args.fixtures or [
        p.parent.name for p in sorted((ROOT / "tests" / "fixtures").glob("*/meta.json"))
    ]
    results: list[dict[str, Any]] = []
    for slug in fixtures:
        meta = load_meta(slug)
        budget = (
            args.budget
            if args.budget is not None
            else content_budget(meta["source_url"], page_type=meta["page_type"])
        )
        if budget == 0:
            budget = None
        reference = load_reference(slug)
        for extractor in args.extractors:
            runs = []
            for _ in range(max(1, args.runs)):
                result = _extract(extractor, slug, budget, args.top_n)
                precision, recall = _pr(result.text, reference)
                facts, fact_total = _fact_presence(result.text, slug)
                runs.append(
                    {
                        "tokens": count(result.text),
                        "chars": len(result.text),
                        "precision": round(precision, 4),
                        "recall": round(recall, 4),
                        "facts": facts,
                        "fact_total": fact_total,
                        "method": result.method,
                        "hash": hashlib.sha256(result.text.encode()).hexdigest()[:16],
                    }
                )
            grade = _grade(
                slug,
                extractor,
                _extract(extractor, slug, budget, args.top_n).text,
                args.model,
                args.grade,
                not args.no_cache,
            )
            results.append(
                {
                    "fixture": slug,
                    "page_type": meta["page_type"],
                    "extractor": extractor,
                    "runs": runs,
                    "grade": grade,
                }
            )
    aggregates: dict[str, dict[str, Any]] = defaultdict(dict)
    by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in results:
        by_type[row["page_type"]].append(row)
    for page_type, rows in sorted(by_type.items()):
        for extractor in args.extractors:
            selected = [r for r in rows if r["extractor"] == extractor]
            if not selected:
                continue

            def med(key, rows=selected):
                return _mean(
                    [
                        statistics.median([run[key] for run in row["runs"]])
                        for row in rows
                    ]
                )

            grades = [
                r["grade"] for r in selected if r["grade"]["status"] == "measured"
            ]
            aggregates[page_type][extractor] = {
                "tokens": med("tokens"),
                "chars": med("chars"),
                "precision": med("precision"),
                "recall": med("recall"),
                "facts": int(
                    sum(
                        statistics.median([run["facts"] for run in r["runs"]])
                        for r in selected
                    )
                ),
                "fact_total": int(sum(r["runs"][0]["fact_total"] for r in selected)),
                "grade_correct": sum(g["correct"] for g in grades),
                "grade_total": sum(g["total"] for g in grades),
                "runs": args.runs,
            }
    return {
        "meta": {
            "commit": os.environ.get("BENCH_COMMIT", "unknown"),
            "tokenizer": tokenizer_name,
            "runs": args.runs,
            "budget": args.budget,
            "extractors": args.extractors,
            "fixtures": fixtures,
            "grade_model": args.model if args.grade else None,
        },
        "aggregates": aggregates,
        "results": results,
    }


def _markdown(data: dict[str, Any]) -> str:
    lines = [
        "# Reader benchmark",
        "",
        f"- tokenizer: `{data['meta']['tokenizer']}`",
        f"- runs: {data['meta']['runs']}",
        f"- budget: {data['meta']['budget'] if data['meta']['budget'] is not None else 'per-page default'}",
        f"- extractors: {', '.join(data['meta']['extractors'])}",
        "",
    ]
    for page_type, by_extractor in data["aggregates"].items():
        lines.append(f"## {page_type}")
        lines.append("")
        lines.append("| extractor | tokens | precision | recall | facts | grade |")
        lines.append("|---|---:|---:|---:|---:|---:|")
        for extractor, row in sorted(by_extractor.items()):
            grade = (
                f"{row['grade_correct']}/{row['grade_total']}"
                if row["grade_total"]
                else "not measured"
            )
            lines.append(
                f"| {extractor} | {row['tokens']:.0f} | {row['precision']:.3f} | "
                f"{row['recall']:.3f} | {row['facts']:.0f}/{row['fact_total']:.0f} | {grade} |"
            )
        lines.append("")
    lines.append("## Per fixture")
    lines.append("")
    lines.append("| fixture | type | extractor | tokens | P | R | facts |")
    lines.append("|---|---|---|---:|---:|---:|---:|")
    for row in data["results"]:
        run = row["runs"][0]
        lines.append(
            f"| {row['fixture']} | {row['page_type']} | {row['extractor']} | "
            f"{run['tokens']} | {run['precision']:.3f} | {run['recall']:.3f} | "
            f"{run['facts']}/{run['fact_total']} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", nargs="*", default=[])
    parser.add_argument(
        "--extractors",
        nargs="*",
        default=[
            "reader-default",
            "reader-recall",
            "reader-precision",
            "reader-no-tables",
            "reader-comments",
            "reader-links-inline",
            "readability",
            "tag-strip",
            "stagehand-innertext",
        ],
    )
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument(
        "--top-n", type=int, default=8, help="number of fixtures to show"
    )
    parser.add_argument("--budget", type=int, default=None, help="0 means full output")
    parser.add_argument(
        "--tokenizer", choices=["tiktoken", "chars4", "deepseek"], default="tiktoken"
    )
    parser.add_argument(
        "--grade", action="store_true", help="LLM-grade answers (network/LLM)"
    )
    parser.add_argument("--model", default="deepseek-flash")
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--json", type=Path)
    parser.add_argument("--markdown", type=Path)
    parser.add_argument(
        "--page-type-report", action="store_true", help="reserved for plan 08"
    )
    args = parser.parse_args()
    if args.page_type_report:
        from collections import Counter

        rows = []
        for meta_path in sorted((ROOT / "tests" / "fixtures").glob("*/meta.json")):
            slug = meta_path.parent.name
            meta = load_meta(slug)
            raw = load_page_text(slug) if not slug.endswith("-pdf") else ""
            predicted = detect_page_type(raw, meta["source_url"])
            rows.append((slug, meta["page_type"], predicted))
        correct = sum(1 for _, expected, predicted in rows if expected == predicted)
        counts = Counter((expected, predicted) for _, expected, predicted in rows)
        print(f"page-type accuracy: {correct}/{len(rows)}")
        print("| fixture | expected | predicted |")
        print("|---|---|---|")
        for slug, expected, predicted in rows:
            mark = "" if expected == predicted else " **MISS**"
            print(f"| {slug} | {expected} | {predicted}{mark} |")
        print("\nconfusion (expected,predicted):")
        for (expected, predicted), count in sorted(counts.items()):
            print(f"  {expected} -> {predicted}: {count}")
        return 0
    data = _run(args)
    markdown = _markdown(data)
    if args.json:
        args.json.write_text(json.dumps(data, indent=2) + "\n")
    if args.markdown:
        args.markdown.write_text(markdown)
    print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
