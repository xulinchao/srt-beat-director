"""Shared runtime metadata and explicit per-shot production decision checks."""

from pathlib import Path


RUNTIMES = {"hyperframes", "remotion"}
VIDEO_RUNTIMES = {
    "comfyui-minimax-h3-fl2v",
    "comfyui-minimax-h3-i2v",
    "comfyui-minimax-h3-r2v",
    "comfyui-minimax-h3-multi-reference",
}
IMAGE_RUNTIMES = {
    "comfyui-qwen21-t2i",
    "comfyui-qwen21-edit",
    "comfyui-qwen21-multi2",
    "comfyui-qwen21-multi4",
    "comfyui-qwen21-multi6",
    "comfyui-qwen-edit-2509",
    "comfyui-qwen-edit-2509-faceswap",
    "comfyui-qwen-edit-masked",
    "comfyui-qwen-edit-multi",
    "comfyui-qwen-edit-multi-hq",
    "comfyui-z-image-base",
    "comfyui-z-image-turbo",
    "comfyui-crop-image",
}


def template_runtime(template: dict) -> str:
    # Legacy entries describe HyperFrames readiness, not the source framework.
    return str(template.get("runtime") or "hyperframes").lower()


def template_status(template: dict) -> str:
    return str(template.get("animation_status") or template.get("hyperframes_status") or "")


def validate_runtime_decision(shot: dict, project_dir: Path, template_index: dict | None = None) -> list[str]:
    production = shot.get("production") or {}
    runtime = production.get("primary_tool")
    if runtime in VIDEO_RUNTIMES:
        decision = production.get("runtime_decision") or {}
        errors = []
        if decision.get("mode") not in {"user-request", "capability-exception", "fallback"}:
            errors.append(f"{shot.get('id')} ComfyUI 视频必须记录 user-request 或 capability-exception")
        if not str(decision.get("reason") or "").strip():
            errors.append(f"{shot.get('id')} ComfyUI 视频缺少 runtime_decision.reason")
        generation = production.get("video_generation") or {}
        for key in ("workflow", "motion_prompt"):
            if not str(generation.get(key) or "").strip():
                errors.append(f"{shot.get('id')} video_generation 缺少 {key}")
        if runtime in {"comfyui-minimax-h3-fl2v", "comfyui-minimax-h3-i2v"} and not str(generation.get("first_frame") or "").strip():
            errors.append(f"{shot.get('id')} video_generation 缺少 first_frame")
        if runtime == "comfyui-minimax-h3-fl2v" and not str(generation.get("last_frame") or "").strip():
            errors.append(f"{shot.get('id')} fl2v 必须提供 last_frame")
        reference_count = {"comfyui-minimax-h3-r2v": 2, "comfyui-minimax-h3-multi-reference": 3}.get(runtime)
        if reference_count is not None:
            references = generation.get("reference_frames")
            if not isinstance(references, list) or len(references) != reference_count or any(not isinstance(ref, str) or not ref.strip() for ref in references):
                errors.append(f"{shot.get('id')} video_generation.reference_frames 必须提供 {reference_count} 张参考图")
        return errors
    if runtime in IMAGE_RUNTIMES:
        decision = production.get("runtime_decision") or {}
        errors = []
        if decision.get("mode") not in {"user-request", "capability-exception", "fallback"}:
            errors.append(f"{shot.get('id')} 本地图片生成必须记录 user-request、fallback 或 capability-exception")
        if not str(decision.get("reason") or "").strip():
            errors.append(f"{shot.get('id')} 本地图片生成缺少 runtime_decision.reason")
        generation = production.get("image_generation") or {}
        if not str(generation.get("workflow") or "").strip():
            errors.append(f"{shot.get('id')} image_generation 缺少 workflow")
        if runtime != "comfyui-crop-image" and not str(generation.get("prompt") or "").strip():
            errors.append(f"{shot.get('id')} image_generation 缺少 prompt")
        if decision.get("mode") == "fallback" and decision.get("source_runtime") != "gpt-image2":
            errors.append(f"{shot.get('id')} fallback 必须声明 source_runtime=gpt-image2")
        return errors
    if runtime not in RUNTIMES:
        return []
    label = f"{shot.get('id')} runtime_decision"
    decision = production.get("runtime_decision")
    if not isinstance(decision, dict):
        return [f"{label} 缺失，必须记录制作工具决策"]
    errors = []
    mode = decision.get("mode")
    if mode not in {"new-default", "native-reuse", "port", "user-request", "capability-exception", "fallback"}:
        errors.append(f"{label}.mode 无效")
    if not str(decision.get("reason") or "").strip():
        errors.append(f"{label} 缺少 reason")
    source = decision.get("source_runtime")
    source_ref = decision.get("source_ref")
    if mode == "new-default":
        if runtime != "hyperframes":
            errors.append(f"{label} 新制作默认必须使用 hyperframes")
        if source is not None or source_ref is not None:
            errors.append(f"{label} new-default 不能同时声明复用来源")
    if mode in {"native-reuse", "port"}:
        if source not in RUNTIMES:
            errors.append(f"{label} 缺少有效 source_runtime")
        if not source_ref or source_ref != shot.get("template_id"):
            errors.append(f"{label}.source_ref 必须绑定当前 template_id")
        if mode == "native-reuse" and source != runtime:
            errors.append(f"{label} 原生复用的源框架与 primary_tool 不一致")
        if mode == "port" and source == runtime:
            errors.append(f"{label} 移植必须具有不同的源与目标框架")
        template = next((item for item in (template_index or {}).get("templates", []) if item.get("id") == source_ref), None)
        if template is not None and template_runtime(template) != source:
            errors.append(f"{label}.source_runtime 与模板当前实现框架不一致")
    if mode != "new-default" and not str(decision.get("alternative_reason") or "").strip():
        errors.append(f"{label} 缺少 alternative_reason")
    if mode == "user-request" and not str(decision.get("user_request") or "").strip():
        errors.append(f"{label} 缺少用户指定工具的原话 user_request")
    evidence = decision.get("evidence", [])
    if not isinstance(evidence, list):
        errors.append(f"{label}.evidence 必须为数组")
    else:
        if mode != "new-default" and not evidence:
            errors.append(f"{label} 缺少 evidence")
        for value in evidence:
            if not isinstance(value, str) or not value.strip():
                errors.append(f"{label} evidence 路径无效")
                continue
            path = Path(value)
            resolved = (project_dir / path).resolve()
            if path.is_absolute() or not resolved.is_relative_to(project_dir.resolve()) or not resolved.is_file():
                errors.append(f"{label} evidence 必须为存在的项目相对文件：{value}")
    return errors
