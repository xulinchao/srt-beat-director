#!/usr/bin/env python3
"""Explicit OpenAI-compatible embedding call, with model/text-hash cache reuse.

Run only against a configured and authorized endpoint. No endpoint is assumed.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from broll_expression import validate_expression
from broll_retrieval import expression_hash, query_text, valid_vector


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("embedding 服务重定向被拒绝，请配置最终服务地址")


def embed(texts: list[str], *, api_base: str, model: str, api_key: str | None = None) -> list[list[float]]:
    parsed = urlparse(api_base)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("api-base 必须为不含凭据、查询或片段的 HTTP(S) 地址")
    if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("远程 embedding 服务须使用 HTTPS")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = Request(api_base.rstrip("/") + "/embeddings",
                      data=json.dumps({"model": model, "input": texts}).encode("utf-8"), headers=headers)
    try:
        with build_opener(NoRedirect).open(request, timeout=60) as response:
            data = json.load(response)
    except HTTPError as exc:
        # Do not print remote error bodies; they can contain request contents.
        raise ValueError(f"embedding 服务返回 HTTP {exc.code}") from None
    items = data.get("data") if isinstance(data, dict) else None
    if not isinstance(items, list) or len(items) != len(texts):
        raise ValueError("embedding 服务返回条目数与输入不一致")
    indexed = {item.get("index"): item.get("embedding") for item in items if isinstance(item, dict)}
    if set(indexed) != set(range(len(texts))):
        raise ValueError("embedding 服务返回 index 缺失或重复")
    vectors = [indexed[i] for i in range(len(texts))]
    if any(not valid_vector(vector, len(vectors[0])) for vector in vectors):
        raise ValueError("embedding 服务返回无效向量或维度不一致")
    return vectors


def prepare(catalog: dict, expression: dict, *, api_base: str, model: str,
            api_key: str | None = None, cache: dict | None = None) -> dict:
    if validate_expression(expression):
        raise ValueError("; ".join(validate_expression(expression)))
    if catalog.get("schema_version") != "1.0" or not isinstance(catalog.get("candidates"), list):
        raise ValueError("catalog 必须为 build_broll_catalog.py 生成的 1.0 目录")
    cache = cache or {}
    can_reuse = cache.get("model") == model and cache.get("api_base") == api_base
    existing = cache.get("candidates", {}) if can_reuse else {}
    candidates, pending = {}, []
    seen = set()
    for item in catalog["candidates"]:
        key = item["retrieval_key"]
        if key in seen:
            raise ValueError("catalog 候选 retrieval_key 重复")
        seen.add(key)
        prior = existing.get(key, {})
        if prior.get("text_sha256") == item["text_sha256"] and valid_vector(prior.get("vector")):
            candidates[key] = prior
        else:
            pending.append(item)
    query = cache.get("query", {}) if can_reuse else {}
    if query.get("expression_sha256") != expression_hash(expression) or not valid_vector(query.get("vector")):
        query = {"expression_sha256": expression_hash(expression),
                 "vector": embed([query_text(expression)], api_base=api_base, model=model, api_key=api_key)[0]}
    for start in range(0, len(pending), 32):
        batch = pending[start:start + 32]
        vectors = embed([item["retrieval_text"] for item in batch], api_base=api_base, model=model, api_key=api_key)
        for item, vector in zip(batch, vectors):
            candidates[item["retrieval_key"]] = {"text_sha256": item["text_sha256"], "vector": vector}
    if any(not valid_vector(item["vector"], len(query["vector"])) for item in candidates.values()):
        raise ValueError("缓存与当前模型的向量维度不一致；保留旧文件，使用新的输出路径重建")
    return {"schema_version": "1.0", "model": model, "api_base": api_base,
            "query": query, "candidates": candidates}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--expression-brief", required=True, type=Path)
    parser.add_argument("--api-base", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--api-key-env", help="从该环境变量读取密钥，不在参数或日志中写密钥")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    try:
        key = os.environ.get(args.api_key_env) if args.api_key_env else None
        if args.api_key_env and not key:
            raise ValueError("指定的密钥环境变量未设置")
        catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
        expression = json.loads(args.expression_brief.read_text(encoding="utf-8"))
        cache = json.loads(args.out.read_text(encoding="utf-8")) if args.out.is_file() else None
        report = prepare(catalog, expression, api_base=args.api_base, model=args.model, api_key=key, cache=cache)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.out.with_suffix(args.out.suffix + ".tmp")
        temporary.write_text(json.dumps(report, ensure_ascii=False) + "\n", encoding="utf-8")
        temporary.replace(args.out)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps({"candidate_count": len(report["candidates"]), "model": args.model, "out": str(args.out)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
