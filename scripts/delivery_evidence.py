"""Validate portable delivery files and an independently captured timeline snapshot."""
from __future__ import annotations

import json
import math
from pathlib import Path

from media_evidence import digest


def pointer_value(document: object, pointer: str) -> object:
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        raise ValueError("原始工程字段需要以 / 开头的 JSON Pointer")
    for token in pointer[1:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        document = document[int(token)] if isinstance(document, list) else document[token]
    return document


def original_value(document: object, reference: object) -> object:
    if isinstance(reference, list):
        return [original_value(document, value) for value in reference]
    if isinstance(reference, str):
        return pointer_value(document, reference)
    if isinstance(reference, dict):
        value = pointer_value(document, reference.get("pointer"))
        if "scale" not in reference and reference.get("round_to_frame") is not True:
            return value
        scale = reference.get("scale", 1)
        if type(value) not in (int, float) or type(scale) not in (int, float) or not math.isfinite(value) or not math.isfinite(scale) or scale <= 0:
            raise ValueError("原始工程数值或换算比例无效")
        value *= scale
        return math.floor(value + 0.5) if reference.get("round_to_frame") is True else value
    raise ValueError("原始工程字段映射无效")


def local_file(root: Path, value: object) -> Path:
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        raise ValueError("证据必须使用项目内相对文件路径")
    path = (root / value).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError(f"证据文件不存在或越界：{value}")
    return path


def validate_manifest(root: Path, manifest: dict, required: set[str]) -> list[str]:
    errors = []
    entries = manifest.get("files")
    if not isinstance(entries, list) or not entries:
        return ["manifest 缺少非空 files 交付清单"]
    listed = set()
    for entry in entries:
        if not isinstance(entry, dict):
            errors.append("manifest.files 每项必须为对象")
            continue
        try:
            path = local_file(root, entry.get("path"))
            if path == (root / "reports/manifest.json").resolve():
                errors.append("manifest 不得包含自身哈希，避免循环依赖")
            if path in listed:
                errors.append(f"manifest 文件重复：{entry.get('path')}")
            listed.add(path)
            if digest(path) != entry.get("sha256"):
                errors.append(f"manifest 文件 SHA-256 不一致：{entry.get('path')}")
        except (OSError, ValueError) as exc:
            errors.append(f"manifest：{exc}")
        for key in ("source", "version", "status"):
            if not isinstance(entry.get(key), str) or not entry[key].strip():
                errors.append(f"manifest 文件 {entry.get('path')} 缺少 {key}")
        if entry.get("status") in {"stale", "rejected", "failed", "missing"}:
            errors.append(f"manifest 包含无效交付文件：{entry.get('path')}")
    for value in sorted(required):
        if (root / value).resolve() not in listed:
            errors.append(f"manifest 未登记必要文件：{value}")
    return errors


def load_timeline_snapshot(root: Path, reference: object, project: dict,
                           final_hash: str, required: set[str], *,
                           expected_plan_sha256: str | None = None) -> tuple[dict, list[str]]:
    errors, items = [], {}
    try:
        if not isinstance(reference, dict):
            raise ValueError("时间线审计缺少 source_snapshot")
        path = local_file(root, reference.get("path"))
        required.add(reference["path"])
        if digest(path) != reference.get("sha256"):
            errors.append("时间线原始快照 SHA-256 不一致")
        snapshot = json.loads(path.read_text(encoding="utf-8"))
        if snapshot.get("schema_version") != "1.0" or not snapshot.get("captured_at"):
            errors.append("时间线快照版本或采集时间缺失")
        expected_project = ((project.get("chatcut") or {}).get("project_id")
                            if project.get("primary_timeline") == "chatcut" else project.get("project_id"))
        if not expected_project or snapshot.get("project_id") != expected_project:
            errors.append("时间线快照 project_id 与当前工程不一致")
        if snapshot.get("timeline_id") != (project.get("final_artifact") or {}).get("timeline_id"):
            errors.append("时间线快照 timeline_id 与成片不一致")
        if snapshot.get("fps") != (project.get("video") or {}).get("fps"):
            errors.append("时间线快照 fps 与项目不一致")
        if snapshot.get("final_sha256") != final_hash:
            errors.append("时间线快照未绑定当前成片")
        if snapshot.get("plan_sha256") != (expected_plan_sha256 or digest(root / "planning/visual-plan.json")):
            errors.append("时间线快照绑定旧视觉计划")
        sources = snapshot.get("sources")
        if not isinstance(sources, list) or not sources:
            errors.append("时间线快照缺少原始工程读取结果 sources")
        raw_documents = {}
        for source in sources if isinstance(sources, list) else []:
            raw = local_file(root, source.get("path"))
            if raw == path or raw == (root / "reports/timeline-audit.json").resolve():
                errors.append("时间线原始来源不能使用快照或审计本身")
            required.add(source["path"])
            if digest(raw) != source.get("sha256"):
                errors.append("时间线原始工程读取结果哈希不一致")
            raw_documents[raw] = json.loads(raw.read_text(encoding="utf-8"))
        rows = snapshot.get("items")
        if not isinstance(rows, list) or not rows:
            errors.append("时间线快照缺少实际素材实例 items")
        for item in rows if isinstance(rows, list) else []:
            item_id = item.get("item_id")
            if not isinstance(item_id, str) or not item_id.strip() or item_id in items:
                errors.append("时间线快照 item_id 缺失或重复")
                continue
            if project.get("primary_timeline") == "chatcut" and not str(item.get("asset_id") or "").strip():
                errors.append(f"时间线快照 {item_id} 缺少 asset_id")
            asset = local_file(root, item.get("artifact"))
            required.add(item["artifact"])
            if digest(asset) != item.get("sha256"):
                errors.append(f"时间线快照 {item_id} 源资产 SHA-256 不一致")
            bounds = item.get("range_frames")
            if not isinstance(bounds, list) or len(bounds) != 2 or any(type(v) is not int for v in bounds) or not 0 <= bounds[0] < bounds[1]:
                errors.append(f"时间线快照 {item_id} 帧区间无效")
            for key in ("source_start_ms", "playback_rate"):
                value = item.get(key)
                if type(value) not in (int, float) or not math.isfinite(value) or value < 0 or (key == "playback_rate" and value == 0):
                    errors.append(f"时间线快照 {item_id} {key} 无效")
            origin = item.get("origin") or {}
            raw_path = local_file(root, origin.get("path"))
            if raw_path not in raw_documents:
                errors.append(f"时间线快照 {item_id} 原始数据未在 sources 登记")
            else:
                fields = origin.get("fields") or {}
                keys = ["item_id", "artifact", "range_frames", "source_start_ms", "playback_rate"]
                if project.get("primary_timeline") == "chatcut":
                    keys.append("asset_id")
                for key in keys:
                    reference = fields.get(key)
                    field_source = raw_path
                    if isinstance(reference, dict) and reference.get("path"):
                        field_source = local_file(root, reference["path"])
                    if field_source not in raw_documents:
                        raise ValueError("原始字段来源必须在 sources 中登记")
                    value = original_value(raw_documents[field_source], reference)
                    if key == "artifact":
                        if not isinstance(value, str) or (root / value).resolve() != asset:
                            errors.append(f"时间线快照 {item_id} 源文件路径与原始工程读取结果不一致")
                    elif value != item.get(key):
                        errors.append(f"时间线快照 {item_id} {key} 与原始工程读取结果不一致")
            items[item_id] = item
    except (OSError, ValueError, TypeError, KeyError, AttributeError, IndexError) as exc:
        errors.append(f"时间线快照不可验证：{exc}")
    return items, errors


def validate_timeline_item(root: Path, item: dict, evidence: dict, at_ms: object,
                           snapshot_items: dict, fps: float) -> list[str]:
    original = snapshot_items.get(item.get("item_id"))
    if original is None:
        return [f"时间线 item_id 不在工程快照中：{item.get('item_id')}"]
    errors = []
    for key in ("asset_id", "range_frames"):
        if original.get(key) != item.get(key):
            errors.append(f"时间线 {item.get('item_id')} {key} 与工程快照不一致")
    if (root / str(original.get("artifact"))).resolve() != (root / str(evidence.get("artifact"))).resolve():
        errors.append(f"时间线 {item.get('item_id')} 实际资产与节拍证据不一致")
    source_time = evidence.get("artifact_time_ms")
    bounds = original.get("range_frames")
    start, rate = original.get("source_start_ms"), original.get("playback_rate")
    if source_time is not None:
        valid = (type(at_ms) is int and type(source_time) is int and isinstance(bounds, list)
                 and len(bounds) == 2 and type(bounds[0]) is int
                 and type(start) in (int, float) and type(rate) in (int, float)
                 and math.isfinite(start) and math.isfinite(rate) and rate > 0)
        if valid:
            mapped = start + (at_ms - bounds[0] * 1000 / fps) * rate
            if abs(mapped - source_time) > 1000 / fps * rate:
                errors.append(f"时间线 {item.get('item_id')} 裁切/速度映射与 artifact_time_ms 不一致")
        else:
            errors.append("时间线素材源时间映射不可验证")
    return errors
