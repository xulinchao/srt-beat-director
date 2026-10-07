#!/usr/bin/env python3
"""Measure candidate recall on labeled queries; does not measure final visual quality."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from broll_expression import validate_expression
from select_broll_template import collect_reference_candidates
from broll_retrieval import rank_candidates


def evaluate(corpus: list[dict], cases: dict) -> dict:
    rows = []
    for case in cases["cases"]:
        expression = case["expression_brief"]
        errors = validate_expression(expression)
        if errors:
            raise ValueError(f"{case['id']}: {'; '.join(errors)}")
        expected = set(case["expected_candidates"])
        available = {f"{item['reference_source']}:{item['id']}" for item in corpus}
        if not expected or not expected.issubset(available):
            raise ValueError(f"{case['id']}: 标注候选不在当前语料中：{sorted(expected - available)}")
        result, info = rank_candidates(corpus, expression)
        returned = [f"{item['reference_source']}:{item['id']}" for item in result]
        rank = next((i for i, key in enumerate(returned, 1) if key in expected), None)
        rows.append({"id": case["id"], "first_relevant_rank": rank,
                     "expected_candidates": sorted(expected), "top_5": returned[:5],
                     "semantic_enabled": info["semantic"]["enabled"]})
    count = len(rows)
    return {"schema_version": "1.0", "status": "measured", "scope": cases.get("scope"),
            "summary": {"cases": count, "corpus_size": len(corpus),
                        "recall_at_1": sum(row["first_relevant_rank"] == 1 for row in rows) / count if count else 0,
                        "recall_at_5": sum(0 < (row["first_relevant_rank"] or 0) <= 5 for row in rows) / count if count else 0,
                        "recall_at_10": sum(0 < (row["first_relevant_rank"] or 0) <= 10 for row in rows) / count if count else 0,
                        "mean_reciprocal_rank": sum(1 / row["first_relevant_rank"] if row["first_relevant_rank"] else 0 for row in rows) / count if count else 0},
            "cases": rows}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repositories-root", required=True, type=Path)
    parser.add_argument("--semantic-map", required=True, type=Path)
    parser.add_argument("--cases", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    try:
        mapping = json.loads(args.semantic_map.read_text(encoding="utf-8"))
        cases = json.loads(args.cases.read_text(encoding="utf-8"))
        corpus = collect_reference_candidates(args.repositories_root, "", mapping)
        report = evaluate(corpus, cases)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError, KeyError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(report["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
