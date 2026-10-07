#!/usr/bin/env python3
"""Rank local B-roll templates and expose licensed external fallbacks on a miss."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from broll_runtime import RUNTIMES, template_runtime, template_status
from broll_expression import MATCHING_POLICY, REFERENCE_FRAMEWORKS, motion_matches, validate_expression
from broll_retrieval import (candidate_key, constraint_check, keyword_matches,
                             rank_candidates, tokenize)
from validate_template_index import validate as validate_index


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", required=True, type=Path)
    parser.add_argument("--semantic-structure", required=True)
    parser.add_argument("--semantic-pattern")
    parser.add_argument("--item-count", required=True, type=int)
    parser.add_argument("--duration-ms", required=True, type=int)
    parser.add_argument("--aspect-ratio", required=True)
    parser.add_argument("--material-type", choices=("verified-media", "no-material", "text-only"))
    parser.add_argument("--presentation-type", choices=("verified-media", "infographic", "text-motion"))
    parser.add_argument("--semantic-map", type=Path)
    parser.add_argument("--external-sources", type=Path)
    parser.add_argument("--visual-style", type=Path, help="Bind selection to the current design_ref")
    parser.add_argument("--expression-brief", required=True, type=Path, help="JSON describing subjects, relation, core motion, phases and searches")
    parser.add_argument("--project", type=Path, help="config/project.json，用于读取 repositories_root 字段")
    parser.add_argument("--repositories-root", type=str, default=None,
                        help="参考仓库根目录路径（覆盖 project.json 中的 repositories_root）")
    parser.add_argument("--retrieval-vectors", type=Path, help="可选真实 embedding 缓存；不提供时明确使用离线检索")
    parser.add_argument("--out", required=True, type=Path)
    return parser.parse_args()


def load(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def readiness(status: str) -> tuple[int, bool, bool]:
    value = status.lower()
    if "superseded" in value or value == "stale":
        return (-1000, True, False)
    if "animation-verified" in value or value == "verified":
        return (30, False, True)
    if "implementation-required" in value:
        return (10, True, False)
    return (0, True, False)


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Split a `---` fenced YAML frontmatter block without a YAML dependency."""
    stripped = text.lstrip("\ufeff")
    if not stripped.startswith("---"):
        return {}, text
    sections = stripped.split("---", 2)
    if len(sections) < 3:
        return {}, text
    meta: dict[str, str] = {}
    for line in sections[1].splitlines():
        key, separator, value = line.partition(":")
        if separator and key.strip():
            meta[key.strip()] = value.strip()
    return meta, sections[2]


def expression_keywords(expression: dict | None) -> tuple[list[str], list[str]]:
    """Return (phrases, tokens): full motion/query strings and their word tokens."""
    if not expression:
        return [], []
    phrases: list[str] = []
    tokens: list[str] = []
    for phrase in list(expression.get("motion_tags") or []) + list(expression.get("search_queries") or []):
        normalized = str(phrase).strip().lower()
        if normalized and normalized not in phrases:
            phrases.append(normalized)
        for token in tokenize(normalized):
            if token not in tokens and token not in phrases:
                tokens.append(token)
    return phrases, tokens


NON_SHOT_CARD_NAMES = {"attribution", "readme", "index", "license", "changelog"}


def search_video_shotcraft(root: Path, expression: dict | None, semantic_structure: str) -> list[dict]:
    """Rank shot recipe cards under shots/ (or references/shots/) by keyword hits."""
    shots_root = next(
        (path for path in (root / "shots", root / "references" / "shots") if path.is_dir()),
        None,
    )
    if shots_root is None:
        return []
    phrases, tokens = expression_keywords(expression)
    structure = semantic_structure.strip().lower()
    candidates: list[dict] = []
    for card in sorted(shots_root.rglob("*.md")):
        if card.stem.lower() in NON_SHOT_CARD_NAMES:
            continue
        try:
            meta, body = parse_frontmatter(card.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        category = str(meta.get("category") or meta.get("标签") or card.parent.name).strip().lower()
        haystack = "\n".join(
            str(meta.get(key) or "") for key in ("description", "一句话", "适用", "name")
        ).lower()
        body_text = body.lower()
        matched = keyword_matches(haystack + "\n" + body_text, phrases + tokens)
        phrase_hits = sum(1 for phrase in phrases if phrase in matched)
        category_match = bool(structure) and (structure in category or category in structure)
        if expression is not None and not matched and not category_match:
            continue
        candidates.append({
            "id": str(meta.get("name") or card.stem),
            "category": category,
            "description": haystack,
            "search_text": body,
            "score": round(phrase_hits * 15 + len(matched) * 10 + (5 if category_match else 0), 3),
            "matched_keywords": matched,
            "category_match": category_match,
            "match_basis": "motion" if matched else "semantic-only",
            "reference_path": card.as_posix(),
            "reference_source": "video-shotcraft",
            "status": "recalled",
        })
    candidates.sort(key=lambda item: (-item["score"], item["reference_path"]))
    return candidates[:REFERENCE_REPO_CANDIDATE_LIMIT] if expression is not None else candidates


def search_hyperframes_launches(root: Path, expression: dict | None) -> list[dict]:
    """List compositions/ files from each launch subdirectory as candidates."""
    if not root.is_dir():
        return []
    phrases, tokens = expression_keywords(expression)
    keywords = phrases + tokens
    candidates: list[dict] = []
    for launch in sorted(path for path in root.iterdir() if path.is_dir()):
        for composition in sorted((launch / "compositions").glob("*") if (launch / "compositions").is_dir() else []):
            if not composition.is_file():
                continue
            haystack = f"{launch.name} {composition.stem}".lower()
            matched = keyword_matches(haystack, keywords)
            candidates.append({
                "id": f"{launch.name}/{composition.name}",
                "description": f"{launch.name} {composition.stem} {_leading_comment(composition)}",
                "score": round(len(matched) * 10, 3),
                "matched_keywords": matched,
                "match_basis": "motion" if matched else "semantic-only",
                "reference_path": composition.as_posix(),
                "reference_source": "hyperframes-launches",
                "status": "recalled",
            })
    candidates.sort(key=lambda item: (-item["score"], item["reference_path"]))
    return candidates[:REFERENCE_REPO_CANDIDATE_LIMIT] if expression is not None else candidates


REFERENCE_REPO_CANDIDATE_LIMIT = 50
LEADING_COMMENT_PATTERN = re.compile(
    r"^\s*(?://\s*(?P<line>.+?)\s*$|/\*+\s*(?P<block>.*?)\s*\*/)",
    re.MULTILINE | re.DOTALL,
)


def matched_reference_keywords(haystack_parts: list[str], keywords: list[str]) -> list[str]:
    """Return keywords contained in the joined lowercase haystack."""
    haystack = " ".join(part for part in haystack_parts if part).lower()
    return keyword_matches(haystack, keywords)


def reference_candidate(
    name: str,
    category: str,
    description: str,
    source: str,
    path: Path,
    keywords: list[str],
) -> dict | None:
    """Build a uniformly shaped candidate; None when no keyword matches."""
    matched = matched_reference_keywords([name, category, description], keywords)
    if keywords and not matched:
        return None
    return {
        "id": name,
        "category": category,
        "description": " ".join(description.split()),
        "score": round(len(matched) * 10, 3),
        "matched_keywords": matched,
        "match_basis": "motion",
        "reference_path": path.as_posix(),
        "reference_source": source,
        "status": "recalled",
    }


def _load_json(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _leading_comment(path: Path) -> str:
    """Extract the first //-line or /* */ block comment as a description."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")[:4096]
    except OSError:
        return ""
    match = LEADING_COMMENT_PATTERN.search(text)
    if not match:
        return ""
    raw = match.group("line") or match.group("block") or ""
    raw = raw.lstrip("*").strip()
    return "" if raw.lower().startswith(("eslint", "tslint", "prettier", "@ts-", "!")) else raw


def search_hyperframes_registry(root: Path, keywords: list[str]) -> list[dict]:
    """Parse registry/{blocks,components,examples}/*/registry-item.json metadata."""
    registry_root = root / "registry"
    if not registry_root.is_dir():
        return []
    candidates: list[dict] = []
    for group in ("blocks", "components", "examples"):
        group_root = registry_root / group
        if not group_root.is_dir():
            continue
        for item_dir in sorted(path for path in group_root.iterdir() if path.is_dir()):
            meta = _load_json(item_dir / "registry-item.json")
            if not meta:
                continue
            name = str(meta.get("name") or item_dir.name)
            description = str(meta.get("description") or meta.get("title") or "")
            tags = [str(tag) for tag in meta.get("tags") or [] if isinstance(tag, str)]
            compositions = sorted(item_dir.glob("*.html"))
            target = compositions[0] if compositions else item_dir / "registry-item.json"
            candidate = reference_candidate(
                name, f"{group[:-1]}", " ".join([description, " ".join(tags)]),
                "hyperframes", target, keywords,
            )
            if candidate:
                candidates.append(candidate)
    candidates.sort(key=lambda item: (-item["score"], item["reference_path"]))
    return candidates[:REFERENCE_REPO_CANDIDATE_LIMIT] if keywords else candidates


def search_remotion_templates(root: Path, keywords: list[str]) -> list[dict]:
    """List packages/template-* official Remotion templates as candidates."""
    packages = root / "packages"
    if not packages.is_dir():
        return []
    candidates: list[dict] = []
    for template_dir in sorted(path for path in packages.iterdir() if path.is_dir() and path.name.startswith("template-")):
        package = _load_json(template_dir / "package.json") or {}
        candidate = reference_candidate(
            template_dir.name, "template", str(package.get("description") or ""),
            "remotion", template_dir / "package.json", keywords,
        )
        if candidate:
            candidates.append(candidate)
    candidates.sort(key=lambda item: (-item["score"], item["reference_path"]))
    return candidates[:REFERENCE_REPO_CANDIDATE_LIMIT] if keywords else candidates


def search_remocn_registry(root: Path, keywords: list[str]) -> list[dict]:
    """Parse every registry/*/registry.json (shadcn-style) item list."""
    registry_root = root / "registry"
    if not registry_root.is_dir():
        return []
    candidates: list[dict] = []
    seen: set[str] = set()
    for registry_file in sorted(registry_root.rglob("registry.json")):
        data = _load_json(registry_file)
        if not data:
            continue
        category = registry_file.parent.name
        for item in data.get("items") or []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            files = [entry for entry in item.get("files") or [] if isinstance(entry, dict) and entry.get("path")]
            if files:
                target = registry_file.parent / str(files[0]["path"])
            else:
                target = registry_file.parent / name
            candidate = reference_candidate(
                name, category, str(item.get("description") or item.get("title") or ""),
                "remocn", target, keywords,
            )
            if candidate:
                candidates.append(candidate)
    candidates.sort(key=lambda item: (-item["score"], item["reference_path"]))
    return candidates[:REFERENCE_REPO_CANDIDATE_LIMIT] if keywords else candidates


def search_motion_canvas(root: Path, keywords: list[str]) -> list[dict]:
    """List packages/examples/src scenes plus the starter template project."""
    candidates: list[dict] = []
    examples_src = root / "packages" / "examples" / "src"
    if examples_src.is_dir():
        for scene in sorted(examples_src.rglob("*.ts")):
            if scene.name.endswith((".meta", ".d.ts")):
                continue
            candidate = reference_candidate(
                scene.stem, "example-scene", _leading_comment(scene),
                "motion-canvas", scene, keywords,
            )
            if candidate:
                candidates.append(candidate)
    template_src = root / "packages" / "template" / "src"
    if template_src.is_dir():
        candidate = reference_candidate(
            "starter-template", "template", "Motion Canvas starter project template",
            "motion-canvas", template_src, keywords,
        )
        if candidate:
            candidates.append(candidate)
    candidates.sort(key=lambda item: (-item["score"], item["reference_path"]))
    return candidates[:REFERENCE_REPO_CANDIDATE_LIMIT] if keywords else candidates


def search_motion_canvas_examples(root: Path, keywords: list[str]) -> list[dict]:
    """List each examples/<project> as one candidate using its package.json."""
    examples_root = root / "examples"
    if not examples_root.is_dir():
        return []
    candidates: list[dict] = []
    for project in sorted(path for path in examples_root.iterdir() if path.is_dir()):
        package = _load_json(project / "package.json") or {}
        description = str(package.get("description") or "")
        entry = project / "src" / "project.ts"
        candidate = reference_candidate(
            project.name, "example-project", description,
            "motion-canvas-examples", entry if entry.is_file() else project, keywords,
        )
        if candidate:
            candidates.append(candidate)
    candidates.sort(key=lambda item: (-item["score"], item["reference_path"]))
    return candidates[:REFERENCE_REPO_CANDIDATE_LIMIT] if keywords else candidates


def search_vibe_motion_skills(root: Path, keywords: list[str]) -> list[dict]:
    """Parse each skill directory's SKILL.md frontmatter (name/description)."""
    if not root.is_dir():
        return []
    candidates: list[dict] = []
    for skill_dir in sorted(path for path in root.iterdir() if path.is_dir() and not path.name.startswith(".")):
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.is_file():
            continue
        try:
            meta, _ = parse_frontmatter(skill_file.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        candidate = reference_candidate(
            str(meta.get("name") or skill_dir.name), "skill",
            str(meta.get("description") or ""), "vibe-motion-skills", skill_file, keywords,
        )
        if candidate:
            candidates.append(candidate)
    candidates.sort(key=lambda item: (-item["score"], item["reference_path"]))
    return candidates[:REFERENCE_REPO_CANDIDATE_LIMIT] if keywords else candidates


def collect_reference_candidates(
    repositories_root: Path | str | None,
    semantic_structure: str,
    semantic_mapping: dict | None = None,
) -> list[dict]:
    """Build one corpus before retrieval; no per-source keyword cutoffs."""
    if not repositories_root:
        return []
    root = Path(str(repositories_root))
    if not root.is_dir():
        raise ValueError(f"配置的参考仓库目录不存在：{root}")
    candidates: list[dict] = []
    shotcraft = root / "video-shotcraft"
    if shotcraft.is_dir():
        candidates.extend(search_video_shotcraft(shotcraft, None, semantic_structure))
    launches = root / "hyperframes-launches"
    if launches.is_dir():
        candidates.extend(search_hyperframes_launches(launches, None))
    for repo_name, scanner in (
        ("hyperframes", search_hyperframes_registry),
        ("remotion", search_remotion_templates),
        ("remocn", search_remocn_registry),
        ("motion-canvas", search_motion_canvas),
        ("motion-canvas-examples", search_motion_canvas_examples),
        ("vibe-motion-skills", search_vibe_motion_skills),
    ):
        repo_root = root / repo_name
        if repo_root.is_dir():
            candidates.extend(scanner(repo_root, []))
    by_path = {}
    for structure in (semantic_mapping or {}).get("structures", []):
        for item in structure.get("external_candidates", []):
            path = (root / item["repository"] / item["path"]).resolve().as_posix()
            by_path.setdefault(path, []).append(item)
    for candidate in candidates:
        candidate["reference_path"] = Path(candidate["reference_path"]).resolve().as_posix()
        candidate["framework"] = REFERENCE_FRAMEWORKS.get(candidate["reference_source"])
        descriptors = by_path.get(candidate["reference_path"], [])
        if descriptors:
            # One file may have multiple roles. Do not merge their assertions.
            candidate["catalog_descriptors"] = descriptors
            candidate["motion_tags"] = sorted({tag for item in descriptors for tag in item.get("motion_tags", [])})
            candidate["semantic_fit"] = "\n".join(item.get("semantic_fit", "") for item in descriptors)
            candidate["search_text"] = (candidate.get("search_text", "") + "\n" +
                                       "\n".join(json.dumps(item.get("skeleton", {}), ensure_ascii=False) for item in descriptors))
            if len(descriptors) == 1:
                candidate["skeleton"] = descriptors[0].get("skeleton", {})
                candidate["capabilities"] = descriptors[0].get("capabilities", {})
        # Preserve actual registry tags as explicit metadata, not inferred motion.
        if candidate["reference_source"] == "hyperframes":
            meta = _load_json(Path(candidate["reference_path"]).parent / "registry-item.json") or {}
            tags = [tag for tag in meta.get("tags") or [] if isinstance(tag, str)]
            candidate["motion_tags"] = sorted(set(candidate.get("motion_tags", [])) | set(tags))
        candidate["retrieval_key"] = candidate_key(candidate)
    return candidates


def search_reference_repositories(repositories_root: Path | str | None, expression: dict | None,
                                  semantic_structure: str, semantic_mapping: dict | None = None,
                                  retrieval_vectors: dict | None = None) -> list[dict]:
    candidates = collect_reference_candidates(repositories_root, semantic_structure, semantic_mapping)
    return rank_candidates(candidates, expression, vectors=retrieval_vectors,
                           limit=REFERENCE_REPO_CANDIDATE_LIMIT)[0]


def resolve_structure(mapping: dict | None, value: str) -> dict | None:
    if not mapping:
        return None
    normalized = value.strip().lower()
    for structure in mapping.get("structures") or []:
        names = {str(structure.get("id", "")).lower()}
        names.update(str(alias).lower() for alias in structure.get("aliases") or [])
        if normalized in names:
            return structure
    return None


def select(
    index: dict,
    semantic_structure: str,
    item_count: int,
    duration_ms: int,
    aspect_ratio: str,
    external_sources: dict | None = None,
    semantic_mapping: dict | None = None,
    material_type: str | None = None,
    presentation_type: str | None = None,
    semantic_pattern: str | None = None,
    expression_brief: dict | None = None,
    repositories_root: Path | str | None = None,
    retrieval_vectors: dict | None = None,
) -> dict:
    if expression_brief is not None and validate_expression(expression_brief):
        raise ValueError("; ".join(validate_expression(expression_brief)))
    mapped_structure = resolve_structure(semantic_mapping, semantic_structure)
    mapped_template_ids = set((mapped_structure or {}).get("local_template_ids") or [])
    candidates: list[dict] = []
    for template in index.get("templates") or []:
        exact_semantic_match = template.get("semantic_structure") == semantic_structure
        mapped_template_match = template.get("id") in mapped_template_ids
        exact_pattern_match = (exact_semantic_match or mapped_template_match) and bool(semantic_pattern) and template.get("semantic_pattern") == semantic_pattern
        motion_match = motion_matches(expression_brief, template)
        constraint_fit = constraint_check(expression_brief, template)
        if not exact_pattern_match and not exact_semantic_match and not mapped_template_match and not motion_match:
            continue
        item_range = template.get("item_range") or [0, 0]
        duration_range = template.get("duration_ms") or [0, 0]
        aspect_ratios = template.get("aspect_ratios") or []
        capacity_fit = (item_range[0] <= item_count <= item_range[1]
                        and duration_range[0] <= duration_ms <= duration_range[1]
                        and aspect_ratio in aspect_ratios)
        if not capacity_fit and not expression_brief:
            continue
        bonus, implementation_required, status_qualified = readiness(
            template_status(template)
        )
        if bonus <= -1000:
            continue
        animation_phases = template.get("animation_phases") or []
        source_file = str(template.get("source_file") or "")
        qualified_for_reuse = (
            status_qualified
            and template_runtime(template) in RUNTIMES
            and bool(template.get("preview"))
            and len(animation_phases) >= 3
            and not source_file.lower().endswith(".svg")
            and capacity_fit
            and (expression_brief is None or bool(motion_match))
            and not constraint_fit["conflicts"]
        )
        span_penalty = (item_range[1] - item_range[0]) + (duration_range[1] - duration_range[0]) / 10000
        semantic_bonus = 60 if exact_pattern_match else (40 if exact_semantic_match else 15)
        motion_bonus = 100 * len(motion_match) / len(expression_brief["motion_tags"]) if expression_brief else 0
        score = round(100 + motion_bonus + semantic_bonus + bonus - span_penalty, 3)
        candidates.append(
            {
                "template_id": template.get("id"),
                "score": score,
                "implementation_required": implementation_required,
                "qualified_for_reuse": qualified_for_reuse,
                "hyperframes_status": template.get("hyperframes_status"),
                "runtime": template_runtime(template),
                "animation_status": template_status(template),
                "source_file": template.get("source_file"),
                "animation_phases": animation_phases,
                "known_limits": template.get("known_limits") or [],
                "matched_motion_tags": motion_match,
                "match_basis": "motion" if motion_match else "semantic-only",
                "capacity_fit": capacity_fit,
                "adaptation_required": not capacity_fit,
                "constraint_fit": constraint_fit,
            }
        )
    candidates.sort(key=lambda candidate: (-candidate["score"], candidate["template_id"] or ""))
    qualified_candidates = [candidate for candidate in candidates if candidate["qualified_for_reuse"]]
    reference_candidates: list[dict] = []
    retrieval = None

    if qualified_candidates:
        status = "local-match"
        selected = qualified_candidates[0]
    else:
        corpus = collect_reference_candidates(repositories_root, semantic_structure, semantic_mapping)
        reference_candidates, retrieval = rank_candidates(corpus, expression_brief, vectors=retrieval_vectors)
        if any(candidate["matched"] for candidate in reference_candidates):
            status = "candidates-recalled"
        else:
            status = "external-research-required"
        selected = None

    # 始终收集登记目录/外部来源
    external = []
    external_candidates = []
    pool = [(mapped_structure or {}).get("id"), (mapped_structure or {}).get("external_candidates") or []]
    structures = (semantic_mapping or {}).get("structures", []) if expression_brief else [
        {"id": pool[0], "external_candidates": pool[1]}]
    for candidate_structure in structures:
        for candidate in candidate_structure.get("external_candidates") or []:
            motion_match = motion_matches(expression_brief, candidate)
            same_structure = candidate_structure.get("id") == (mapped_structure or {}).get("id")
            if not same_structure and not motion_match:
                continue
            material_types = candidate.get("material_types") or []
            presentation_types = candidate.get("presentation_types") or []
            if material_type and material_types and material_type not in material_types:
                continue
            if presentation_type and presentation_types and presentation_type not in presentation_types:
                continue
            external_candidates.append({**candidate, "matched_motion_tags": motion_match,
                                        "match_basis": "motion" if motion_match else "semantic-only",
                                        "constraint_fit": constraint_check(expression_brief, candidate),
                                        "catalog_structure": candidate_structure.get("id")})
    external_candidates.sort(key=lambda item: (-len(item["matched_motion_tags"]), item["id"]))
    if external_sources:
        for source in external_sources.get("sources") or []:
            external.append(
                {
                    "id": source.get("id"),
                    "url": source.get("url"),
                    "license": source.get("license"),
                    "usage_policy": source.get("usage_policy"),
                    "original_framework": source.get("original_framework"),
                }
            )

    required_reviews = min(1 if expression_brief else 2, len(external_candidates))
    selection_warnings = [] if expression_brief else ["缺少动作表达简报；仅粗分类候选，不作为新制作的最终选型"]
    if status == "candidates-recalled":
        selection_warnings.append("融合排名只用于召回；关系、阶段与不变量须实际查看预览后确认，分数不是成功概率")
    if retrieval:
        selection_warnings.extend(retrieval["semantic"]["warnings"])
        if not repositories_root:
            selection_warnings.append("未配置 repositories_root，参考仓库检索未执行；不能记录为已搜索无结果")
    if expression_brief and status == "external-research-required" and not any(
        item["matched_motion_tags"] for item in candidates + external_candidates
    ):
        selection_warnings.append("当前目录没有动作标签命中；所列同类候选仅供探索，须按动作查询实际演示，不能直接选用")

    return {
        "schema_version": "0.2",
        "selection_policy": "single-source-per-shot",
        "runtime_policy": "references/broll-runtime-selection.md",
        "selection_is_provisional": True,
        "matching_policy": MATCHING_POLICY,
        "expression_brief": expression_brief,
        "selection_warnings": selection_warnings,
        "retrieval": retrieval,
        "status": status,
        "query": {
            "semantic_structure": semantic_structure,
            "semantic_pattern": semantic_pattern,
            "item_count": item_count,
            "duration_ms": duration_ms,
            "aspect_ratio": aspect_ratio,
            "material_type": material_type,
            "presentation_type": presentation_type,
            "canonical_structure": (mapped_structure or {}).get("id"),
        },
        "selected": selected,
        "local_candidates": candidates,
        "reference_candidates": reference_candidates,
        "external_sources": external,
        "external_candidates": external_candidates,
        "required_external_candidate_reviews": required_reviews,
        "reference_confirmation": None,
        "custom_build_allowed": False,
        "expanded_search_required_before_custom": status != "local-match",
        "reference_confirmation_or_research_required_before_implementation": status == "candidates-recalled",
        "research_record_required_before_implementation": status == "external-research-required",
        "confirmation_required_before_implementation": True,
    }


def markdown(report: dict) -> str:
    expression = report.get("expression_brief")
    if expression:
        expression_summary = (
            "\n## 动作表达\n\n"
            f"- 主体：{'、'.join(expression['subjects'])}\n"
            f"- 关系：{expression['element_relation']}\n"
            f"- 核心动作：{expression['main_motion']}\n"
            f"- 阶段：{' → '.join(expression['phase_order'])}\n"
            f"- 不变量：{'；'.join(expression['invariants'])}\n"
            f"- 动作标签：{', '.join(expression['motion_tags'])}\n"
            "- 扩大搜索查询：\n" + "\n".join(f"  - {query}" for query in expression['search_queries']) + "\n"
        )
    else:
        expression_summary = "\n旧粗分类报告缺少动作简报，不能用于新制作的最终选型。\n"
    if report["selected"]:
        selected = report["selected"]
        result = (
            f"- 模板：`{selected['template_id']}`\n"
            f"- 需要实现动画：`{str(selected['implementation_required']).lower()}`\n"
            f"- 状态：`{selected['animation_status']}`\n"
            f"- 原生制作工具：`{selected['runtime']}`\n"
        )
        if selected.get("reference_path"):
            result += (
                f"- 参考来源：`{selected['reference_source']}`\n"
                f"- 参考路径：`{selected['reference_path']}`\n"
            )
        result += "- 此结果是候选推荐；检查预览、语义和节拍后记录 runtime_decision。"
    else:
        prototype_lines = [
            f"- `{item['template_id']}`：`{item['animation_status']}`（{'容量需适配' if item.get('adaptation_required') else '待检查动作与实现'}，不能阻断外部研究）"
            for item in report.get("local_candidates") or []
            if not item.get("qualified_for_reuse")
        ]
        matched_ref_lines = [
            f"- `{item['id']}`：`{item['reference_source']}` / `{item['reference_path']}`（RRF={item['score']}，依据={item['match_basis']}，约束={item['constraint_fit']['status']}；仍须动态预览）"
            for item in report.get("reference_candidates") or [] if item.get("matched")
        ]
        browse_ref_lines = [
            f"- `{item['id']}`：`{item['reference_source']}` / `{item['reference_path']}`（依据={item['match_basis']}，冲突={item['constraint_fit']['conflicts']}，待核={item['constraint_fit']['unknown']}）"
            for item in report.get("reference_candidates") or [] if not item.get("matched")
        ]
        candidate_lines = [
            f"- `{item['id']}`：`{item['repository']}/{item['path']}`（{item['status']}，{'动作标签命中' if item.get('matched_motion_tags') else '仅语义同类，动作未命中'}）"
            for item in report.get("external_candidates") or []
        ]
        source_lines = [
            f"- `{item['id']}`：{item['license']} / {item['usage_policy']}"
            for item in report["external_sources"]
        ]
        if report["status"] == "candidates-recalled":
            fallback = candidate_lines or source_lines or ["- 已召回参考仓库候选（见下方列表），需人工审阅后确认"]
        else:
            fallback = candidate_lines or source_lines or ["- 未配置外部来源"]
        gate = (
            "- 当前只有召回候选；实际检查预览、动作、阶段、源码与许可后，在 JSON 中填写 reference_confirmation\n"
            "- 选中参考仓库来源可走轻量确认；未选中时须完成外部研究记录，不能直接使用 `new:`\n"
            if report["status"] == "candidates-recalled"
            else "- 实现前检查动作适配、预览与源码，完成逐镜外部研究记录；不能按候选数量凑完成\n"
        )
        gate += "- 候选比较后只能选一个最终来源，其他候选只保留拒绝理由\n"
        gate += "- 自建前用至少两种动作查询、两个搜索来源扩大检索；粗分类候选被拒绝不代表无可用参考\n"
        prototypes = "\n## 本地未完成候选\n\n" + "\n".join(prototype_lines) if prototype_lines else ""
        references = "\n## 参考仓库候选\n\n" + "\n".join(matched_ref_lines) if matched_ref_lines else ""
        browse_references = (
            "\n## 仅供探索或有明确约束冲突的候选\n\n" + "\n".join(browse_ref_lines)
            if browse_ref_lines else ""
        )
        result = "- 本地无合格匹配\n" + "\n".join(fallback) + "\n" + gate + prototypes + references + browse_references
    warning_lines = "".join("- 选型提醒：" + warning + "\n" for warning in report.get("selection_warnings") or [])
    return f"""# B-roll 模板选择

- 状态：`{report['status']}`
- 匹配策略：`{report.get('matching_policy', MATCHING_POLICY)}`
- 语义结构：`{report['query']['semantic_structure']}`
- 信息项：{report['query']['item_count']}
- 时长：{report['query']['duration_ms']} ms
- 画幅：`{report['query']['aspect_ratio']}`
{expression_summary}
{warning_lines}

## 结果

{result}
"""


def main() -> int:
    args = parse_args()
    if args.item_count <= 0 or args.duration_ms <= 0:
        print("item-count 和 duration-ms 必须为正整数", file=sys.stderr)
        return 2
    try:
        validation = validate_index(args.index)
        if validation["status"] != "pass":
            print(json.dumps(validation, ensure_ascii=False), file=sys.stderr)
            return 2
        index = load(args.index)
        external = load(args.external_sources) if args.external_sources else None
        semantic_mapping = load(args.semantic_map) if args.semantic_map else None
        visual = load(args.visual_style) if args.visual_style else {}
        expression = load(args.expression_brief) if args.expression_brief else None
        vectors = load(args.retrieval_vectors) if args.retrieval_vectors else None
        if expression is not None and validate_expression(expression):
            raise ValueError("; ".join(validate_expression(expression)))
        repositories_root = args.repositories_root
        if not repositories_root and args.project:
            repositories_root = load(args.project).get("repositories_root")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    try:
        report = select(
            index,
            args.semantic_structure,
            args.item_count,
            args.duration_ms,
            args.aspect_ratio,
            external,
            semantic_mapping,
            args.material_type,
            args.presentation_type,
            args.semantic_pattern,
            expression,
            repositories_root,
            vectors,
        )
    except (ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.visual_style:
        if not isinstance(visual.get("design_ref"), dict) or not all(visual["design_ref"].get(k) for k in ("path", "version", "sha256")):
            print("visual-style 缺少完整 design_ref", file=sys.stderr)
            return 2
        report["design_ref"] = visual["design_ref"]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.out.with_suffix(".md").write_text(markdown(report), encoding="utf-8")
    print(json.dumps({"status": report["status"], "out": str(args.out)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
