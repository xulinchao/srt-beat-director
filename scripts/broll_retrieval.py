"""Offline hybrid retrieval; optional precomputed embeddings, never implicit API calls."""

from __future__ import annotations

from collections import Counter
import hashlib
import json
import math
import re


RETRIEVAL_VERSION = "hybrid-rank-v1"
CAPABILITIES = {
    "preserves_position", "preserves_content", "preserves_carrier",
    "retains_previous", "final_overview", "retains_source",
}


def validate_capabilities(value: object) -> bool:
    return isinstance(value, dict) and all(key in CAPABILITIES and isinstance(item, bool) for key, item in value.items())


GENERIC_MOTION_TERMS = {"content", "text", "reveal", "state", "关系", "文字", "信息", "状态"}
STOP_WORDS = set("""
a an the and or to of in on at for from by with without while then that this
these those is are be been being as it its their them they each both all any
one two three four five six first second third different new old result
keeping keep kept using use used should must can will would into after before
""".split())
# Small morphology table, not substring stemming (face must not match facet).
WORD_FORMS = {
    "cards": "card", "items": "item", "positions": "position", "phases": "phase",
    "steps": "step", "sources": "source", "objects": "object", "rows": "row",
    "flips": "flip", "flipping": "flip", "flipped": "flip", "rotation": "rotate",
    "rotating": "rotate", "rotates": "rotate", "replacing": "replace",
    "replacement": "replace", "replaced": "replace", "revealing": "reveal",
    "reveals": "reveal", "revealed": "reveal", "retaining": "retain",
    "retained": "retain", "preserving": "preserve", "preserved": "preserve",
    "counting": "count", "counts": "count", "numbers": "number",
}
TOKEN_PATTERN = re.compile(r"[a-z0-9]+|[\u3400-\u9fff]+", re.I)
# Controlled bilingual vocabulary expansion, not an embedding or inferred relation.
CHINESE_TERMS = {
    "翻面": "flip", "翻转": "flip", "旋转": "rotate", "正面": "front", "背面": "back",
    "侧棱": "edge", "卡片": "card", "列表": "list", "清单": "list", "条目": "item",
    "逐项": "progressive", "逐条": "progressive", "错峰": "stagger", "保留": "retain",
    "保持": "preserve", "落定": "settle", "可读": "readable", "位置": "position",
    "对应": "correspondence", "替换": "replace", "文档": "document", "来源": "source",
    "驻留": "park", "结论": "conclusion", "汇入": "converge", "汇聚": "converge",
    "合并": "merge", "节点": "node", "路径": "path", "中心": "center", "选中": "select",
    "筛选": "filter", "退场": "dismiss", "弱化": "dim", "前后": "before-after",
    "分割": "divider", "边界": "boundary", "计数": "count", "数字": "number",
    "原文": "source", "放大": "enlarge", "选区": "region", "定位": "locate",
}


def tokenize(value: str) -> list[str]:
    """Whole English words and Chinese bigrams; no language package dependency."""
    tokens = []
    for word in TOKEN_PATTERN.findall(value.lower()):
        if re.fullmatch(r"[\u3400-\u9fff]+", word):
            tokens.extend(word[i:i + 2] for i in range(len(word) - 1))
            tokens.extend(alias for phrase, alias in CHINESE_TERMS.items() if phrase in word)
        elif word not in STOP_WORDS and len(word) > 1:
            tokens.append(WORD_FORMS.get(word, word))
    return tokens


def keyword_matches(text: str, keywords: list[str]) -> list[str]:
    words = set(tokenize(text))
    return [keyword for keyword in keywords
            if tokenize(keyword) and set(tokenize(keyword)).issubset(words)]


def query_text(expression: dict | None) -> str:
    # Topic-specific subjects are deliberately excluded from motion retrieval.
    expression = expression or {}
    return "\n".join([
        str(expression.get("element_relation") or ""),
        str(expression.get("main_motion") or ""),
        *expression.get("phase_order", []), *expression.get("invariants", []),
        *expression.get("motion_tags", []), *expression.get("search_queries", []),
    ])


def text_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def expression_hash(expression: dict | None) -> str:
    return text_hash(json.dumps(expression, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def candidate_key(candidate: dict) -> str:
    return f"{candidate['reference_source']}:{candidate['id']}:{candidate['reference_path']}"


def candidate_summary(candidate: dict) -> str:
    skeleton = candidate.get("skeleton") or {}
    return "\n".join([
        str(candidate.get("id") or ""), str(candidate.get("description") or ""),
        str(candidate.get("semantic_fit") or ""),
        str(skeleton.get("element_relation") or ""),
        str(skeleton.get("main_motion") or ""),
        *skeleton.get("phase_order", []), *skeleton.get("invariants", []),
        *candidate.get("motion_tags", []),
    ])


def candidate_text(candidate: dict) -> str:
    return candidate_summary(candidate) + "\n" + str(candidate.get("search_text") or "")


def constraint_check(expression: dict | None, candidate: dict) -> dict:
    required = (expression or {}).get("requirements") or {}
    capabilities = candidate.get("capabilities") or {}
    supported, conflicts, unknown = [], [], []
    for key, value in required.items():
        if key not in capabilities:
            unknown.append(key)
        elif capabilities[key] == value:
            supported.append(key)
        else:
            conflicts.append(key)
    return {"status": "conflict" if conflicts else ("unknown" if unknown else "compatible"),
            "supported": supported, "conflicts": conflicts, "unknown": unknown}


def bm25_scores(texts: list[str], query: str) -> list[float]:
    documents = [Counter(tokenize(text)) for text in texts]
    lengths = [sum(document.values()) for document in documents]
    average = sum(lengths) / len(lengths) if lengths else 0
    if not average:
        return [0.0] * len(texts)
    terms = set(tokenize(query))
    frequencies = Counter(term for document in documents for term in terms if term in document)
    scores = []
    for document, length in zip(documents, lengths):
        score = 0.0
        for term in terms:
            frequency = document.get(term, 0)
            if not frequency:
                continue
            inverse = math.log(1 + (len(documents) - frequencies[term] + 0.5) / (frequencies[term] + 0.5))
            score += inverse * frequency * 2.2 / (frequency + 1.2 * (0.25 + 0.75 * length / average))
        scores.append(score)
    return scores


def valid_vector(value: object, dimensions: int | None = None) -> bool:
    return (isinstance(value, list) and bool(value)
            and (dimensions is None or len(value) == dimensions)
            and all(isinstance(x, (float, int)) and not isinstance(x, bool) and math.isfinite(x) for x in value)
            and 0 < math.hypot(*value) < math.inf)


def cosine(left: list[float], right: list[float]) -> float:
    left_norm, right_norm = math.hypot(*left), math.hypot(*right)
    return sum((a / left_norm) * (b / right_norm) for a, b in zip(left, right))


def semantic_scores(candidates: list[dict], expression: dict | None, bundle: dict | None) -> tuple[list[float], dict]:
    scores = [0.0] * len(candidates)
    info = {"enabled": False, "model": None, "valid_candidates": 0, "warnings": []}
    if bundle is None:
        info["warnings"].append("未提供真实向量，当前使用 BM25、动作标签与显式约束；语义向量检索未启用")
        return scores, info
    if not isinstance(bundle, dict) or bundle.get("schema_version") != "1.0" or not isinstance(bundle.get("model"), str) or not bundle["model"].strip():
        raise ValueError("retrieval-vectors 缺少 schema_version=1.0 或 model")
    query = bundle.get("query") or {}
    if not isinstance(query, dict):
        raise ValueError("retrieval-vectors.query 必须为对象")
    if query.get("expression_sha256") != expression_hash(expression):
        raise ValueError("retrieval-vectors 的查询简报已过期")
    vector = query.get("vector")
    if not valid_vector(vector):
        raise ValueError("retrieval-vectors 查询向量无效")
    entries = bundle.get("candidates")
    if not isinstance(entries, dict):
        raise ValueError("retrieval-vectors.candidates 必须为对象")
    stale = 0
    for i, candidate in enumerate(candidates):
        entry = entries.get(candidate_key(candidate))
        if entry is None:
            continue
        if not isinstance(entry, dict):
            raise ValueError("retrieval-vectors 候选条目无效")
        if entry.get("text_sha256") != text_hash(candidate_text(candidate)):
            stale += 1
            continue
        if not valid_vector(entry.get("vector"), len(vector)):
            raise ValueError("retrieval-vectors 候选向量维度不一致或无效")
        scores[i] = cosine(vector, entry["vector"])
        info["valid_candidates"] += 1
    info.update(enabled=info["valid_candidates"] > 0, model=bundle["model"])
    if stale:
        info["warnings"].append(f"{stale} 个候选描述已变化，跳过其旧向量")
    if info["valid_candidates"] < len(candidates):
        info["warnings"].append("向量未覆盖全部候选，未覆盖项继续使用其他召回通道")
    return scores, info


def rank_candidates(candidates: list[dict], expression: dict | None, *, vectors: dict | None = None,
                    limit: int = 50) -> tuple[list[dict], dict]:
    """RRF fusion followed by explicit compatibility ranking; no approval decisions."""
    texts = [candidate_text(candidate) for candidate in candidates]
    # A long implementation/known-pitfalls body must not drown the motion summary.
    summary_scores = bm25_scores([candidate_summary(item) for item in candidates], query_text(expression))
    body_scores = bm25_scores(texts, query_text(expression))
    lexical = [2 * summary + body for summary, body in zip(summary_scores, body_scores)]
    semantic, info = semantic_scores(candidates, expression, vectors)
    tags = {tag.lower() for tag in (expression or {}).get("motion_tags", [])}
    tag_scores = [len(tags & {tag.lower() for tag in candidate.get("motion_tags", [])}) for candidate in candidates]
    lanes = {}
    fused = [0.0] * len(candidates)
    for name, values in (("bm25", lexical), ("motion_tags", tag_scores), ("semantic", semantic)):
        order = sorted((i for i, score in enumerate(values) if score > 0),
                       key=lambda i: (-values[i], candidate_key(candidates[i])))
        # Keep ties at the same rank; path order must not manufacture relevance.
        ranks, previous, rank = {}, None, 0
        for position, i in enumerate(order, 1):
            if values[i] != previous:
                rank = position
            ranks[i] = rank
            previous = values[i]
            fused[i] += 1 / (60 + rank)
        lanes[name] = ranks
    results = []
    terms = sorted(set(tokenize(query_text(expression))))
    core_terms = set(tokenize(str((expression or {}).get("main_motion", "")) + " " +
                              " ".join((expression or {}).get("motion_tags", [])))) - GENERIC_MOTION_TERMS
    for i, candidate in enumerate(candidates):
        category_match = candidate.get("category_match", False)
        if not fused[i] and not category_match:
            continue
        item = {**candidate}
        item.pop("search_text", None)
        item["matched_keywords"] = sorted(set(tokenize(texts[i])) & set(terms))
        item["matched_motion_tags"] = sorted(tags & {tag.lower() for tag in item.get("motion_tags", [])})
        check = constraint_check(expression, item)
        item["constraint_fit"] = check
        item["retrieval_scores"] = {"bm25": round(lexical[i], 6), "semantic": round(semantic[i], 6),
                                    "rrf": round(fused[i], 8)}
        item["retrieval_ranks"] = {name: ranks[i] for name, ranks in lanes.items() if i in ranks}
        item["score"] = round(fused[i], 8)
        item["match_basis"] = ("motion" if tag_scores[i] else
                               "semantic" if semantic[i] > 0 else
                               "lexical" if lexical[i] > 0 else "semantic-only")
        item["core_motion_overlap"] = sorted(core_terms & set(tokenize(texts[i])))
        item["matched"] = bool(tag_scores[i] or semantic[i] > 0 or item["core_motion_overlap"]) and not check["conflicts"]
        item["review_required"] = ["element_relation", "main_motion", "phase_order", "invariants", "actual_preview"]
        results.append(item)
    def order_key(item):
        return (bool(item["constraint_fit"]["conflicts"]), not item["matched"],
                -len(item["constraint_fit"]["supported"]), -item["score"], candidate_key(item))
    results.sort(key=order_key)
    # Reserve the best relevant result from each source, then fill globally.
    best = {}
    for item in results:
        if item["matched"]:
            best.setdefault(item["reference_source"], item)
    reserved = list(best.values())[:limit]
    keys = {candidate_key(item) for item in reserved}
    retained = reserved + [item for item in results if candidate_key(item) not in keys][:max(0, limit - len(reserved))]
    retained.sort(key=order_key)
    return retained, {"version": RETRIEVAL_VERSION, "semantic": info,
                      "scanned_candidates": len(candidates), "recalled_candidates": len(results),
                      "returned_candidates": len(retained), "source_coverage": sorted({item["reference_source"] for item in retained}),
                      "reranking": "explicit-constraints; prose relations and temporal order require preview review"}
