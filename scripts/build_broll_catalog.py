#!/usr/bin/env python3
"""Export a portable retrieval catalog; does not certify or render any candidate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from broll_retrieval import candidate_text, text_hash
from select_broll_template import collect_reference_candidates


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repositories-root", required=True, type=Path)
    parser.add_argument("--semantic-map", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    try:
        mapping = json.loads(args.semantic_map.read_text(encoding="utf-8")) if args.semantic_map else None
        candidates = collect_reference_candidates(args.repositories_root, "", mapping)
        for item in candidates:
            item["retrieval_text"] = candidate_text(item)
            item["text_sha256"] = text_hash(item["retrieval_text"])
            item.pop("search_text", None)
            for key in ("score", "matched_keywords", "match_basis"):
                item.pop(key, None)
        report = {"schema_version": "1.0", "certified": False, "candidates": candidates}
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError, KeyError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps({"candidate_count": len(candidates), "out": str(args.out)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
