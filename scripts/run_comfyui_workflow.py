"""Submit a MiniMax H3 ComfyUI API workflow and collect its video output.

This is intentionally a small project-level adapter. It does not edit the
ChatCut timeline; callers import the collected MP4 and record its asset/item
IDs after the video stream has been checked.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


VIDEO_EXTENSIONS = {".mp4", ".webm", ".mov", ".mkv", ".gif"}


def request_json(url: str, method: str = "GET", payload: dict[str, Any] | None = None) -> Any:
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(url, data=body, method=method, headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def directory_from_stats(system: dict[str, Any], flag: str) -> str | None:
    direct = system.get(f"{flag}_directory")
    if isinstance(direct, str) and direct:
        return direct
    argv = system.get("argv", [])
    if isinstance(argv, list):
        for index, value in enumerate(argv[:-1]):
            if value == f"--{flag}-directory" and isinstance(argv[index + 1], str):
                return argv[index + 1]
    return None


def numeric_key(value: str) -> tuple[int, ...]:
    parts = []
    for part in str(value).split(":"):
        try:
            parts.append(int(part))
        except ValueError:
            parts.append(10**9)
    return tuple(parts)


def copy_input(path: Path, input_dir: Path, token: str, label: str) -> str:
    input_dir.mkdir(parents=True, exist_ok=True)
    target = input_dir / f"codex_{token}_{label}{path.suffix.lower()}"
    shutil.copy2(path, target)
    return target.name


def nodes_of(workflow: dict[str, Any], class_name: str) -> list[tuple[str, dict[str, Any]]]:
    return [
        (node_id, node)
        for node_id, node in sorted(workflow.items(), key=lambda item: numeric_key(item[0]))
        if node.get("class_type") == class_name
    ]


def video_node(workflow: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    candidates = [
        (node_id, node)
        for node_id, node in workflow.items()
        if node.get("class_type") in {
            "MiniMaxH3ImageToVideo", "MiniMaxH3ReferenceToVideo",
            "MiniMaxH3AudioConditioningT8",
        }
    ]
    if not candidates:
        raise ValueError("工作流中没有 MiniMaxH3 视频节点")
    return sorted(candidates, key=lambda item: numeric_key(item[0]))[0]


def set_common_inputs(node: dict[str, Any], prompt: str, length: int | None, width: int | None, height: int | None) -> None:
    inputs = node.setdefault("inputs", {})
    if "prompt" in inputs:
        inputs["prompt"] = prompt
    if length is not None and "length" in inputs:
        inputs["length"] = length
    if width is not None and "width" in inputs:
        inputs["width"] = width
    if height is not None and "height" in inputs:
        inputs["height"] = height


def set_seed(workflow: dict[str, Any], seed: int | None) -> None:
    if seed is None:
        return
    for _, node in workflow.items():
        class_name = str(node.get("class_type", ""))
        inputs = node.get("inputs", {})
        if class_name == "RandomNoise" and "noise_seed" in inputs:
            inputs["noise_seed"] = seed
            return
    for _, node in workflow.items():
        if "seed" in node.get("inputs", {}):
            node["inputs"]["seed"] = seed
            return


def set_output_prefix(workflow: dict[str, Any], prefix: str) -> None:
    for _, node in workflow.items():
        if node.get("class_type") in {"SaveVideo", "VHS_VideoCombine"}:
            inputs = node.setdefault("inputs", {})
            if "filename_prefix" in inputs:
                inputs["filename_prefix"] = prefix


def configure_workflow(
    workflow: dict[str, Any],
    first_frame: str | None,
    last_frame: str | None,
    reference_frames: list[str],
    prompt: str,
    length: int | None,
    width: int | None,
    height: int | None,
    seed: int | None,
    output_prefix: str,
) -> None:
    if (width is None) != (height is None):
        raise ValueError("--width 和 --height 必须同时提供")
    if width is not None and (width <= 0 or height <= 0):
        raise ValueError("宽高必须为正数")
    for candidate in workflow.values():
        class_type = str(candidate.get("class_type", ""))
        if "upscal" in class_type.lower() or class_type.startswith("SeedVR2"):
            raise ValueError("当前视频流水线已停用放大/超分节点")
    video_id, node = video_node(workflow)
    class_name = str(node.get("class_type"))
    if class_name == "MiniMaxH3AudioConditioningT8":
        inputs = node.get("inputs", {})
        if inputs.get("task_type") != "Ref2VA" or inputs.get("audio_mode") != "native":
            raise ValueError("当前 T8 执行器仅支持 Ref2VA + native 音视频工作流")
        if first_frame or last_frame:
            raise ValueError("Ref2VA 图片不是精确首尾帧，请使用 --reference-frame")
        if not reference_frames:
            raise ValueError("Ref2VA 必须提供 --reference-frame")
    set_common_inputs(node, prompt, length, width, height)
    set_seed(workflow, seed)
    set_output_prefix(workflow, output_prefix)
    loads = nodes_of(workflow, "LoadImage")

    if class_name == "MiniMaxH3ImageToVideo":
        if not first_frame:
            raise ValueError("图生视频工作流必须提供 --first-frame")
        if not loads:
            raise ValueError("图生视频工作流没有 LoadImage 节点")
        loads[0][1].setdefault("inputs", {})["image"] = first_frame
        if "last_frame" in node.get("inputs", {}):
            if not last_frame:
                raise ValueError("FL2V 工作流必须提供 --last-frame")
            if len(loads) < 2:
                raise ValueError("FL2V 工作流需要两个 LoadImage 节点")
            loads[1][1].setdefault("inputs", {})["image"] = last_frame
        return

    if class_name in {"MiniMaxH3ReferenceToVideo", "MiniMaxH3AudioConditioningT8"}:
        ref_slots = sorted(
            (
                (int(match.group(1)), value[0])
                for key, value in node.get("inputs", {}).items()
                if (match := re.fullmatch(r"ref_images\.ref_image_(\d+)", key))
                and isinstance(value, list)
                and len(value) == 2
            ),
            key=lambda item: item[0],
        )
        if not ref_slots:
            raise ValueError("参考图工作流没有连接 ref_images 输入槽")
        if not reference_frames and not first_frame:
            raise ValueError("参考图工作流必须提供 --reference-frame 或 --first-frame")
        refs = reference_frames or [first_frame] * len(ref_slots)
        if len(refs) != len(ref_slots):
            raise ValueError(f"参考图工作流需要 {len(ref_slots)} 张参考图，当前提供 {len(refs)} 张")
        for (_, load_id), image_name in zip(ref_slots, refs):
            load = workflow.get(load_id)
            if not isinstance(load, dict) or load.get("class_type") != "LoadImage":
                raise ValueError(f"参考图输入槽没有连接 LoadImage：{load_id}")
            load.setdefault("inputs", {})["image"] = image_name
        return

    raise ValueError(f"不支持的 MiniMax H3 节点：{class_name}（节点 {video_id}）")


def output_files(value: Any) -> list[Path]:
    found: list[Path] = []
    if isinstance(value, dict):
        if isinstance(value.get("filename"), str) and Path(value["filename"]).suffix.lower() in VIDEO_EXTENSIONS:
            subfolder = value.get("subfolder") or ""
            found.append(Path(subfolder) / value["filename"])
        for child in value.values():
            found.extend(output_files(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(output_files(child))
    return found


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="运行 MiniMax H3 ComfyUI API 工作流")
    parser.add_argument("--url", default="http://127.0.0.1:8188")
    parser.add_argument("--workflow", type=Path, required=True)
    parser.add_argument("--first-frame", type=Path)
    parser.add_argument("--last-frame", type=Path)
    parser.add_argument("--reference-frame", type=Path, action="append", default=[])
    prompt_group = parser.add_mutually_exclusive_group(required=True)
    prompt_group.add_argument("--prompt")
    prompt_group.add_argument("--prompt-file", type=Path)
    parser.add_argument("--length", type=int)
    parser.add_argument("--width", type=int)
    parser.add_argument("--height", type=int)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--output-prefix", default="codex/minimax_h3")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.workflow.suffix.lower() != ".json":
        raise SystemExit("只允许提交 .json 工作流；.removed 备份已停用")
    for path in [args.workflow, args.first_frame, args.last_frame, args.prompt_file, *args.reference_frame]:
        if path is not None and not path.is_file():
            raise SystemExit(f"文件不存在：{path}")
    prompt = args.prompt if args.prompt is not None else args.prompt_file.read_text(encoding="utf-8-sig")
    if not prompt.strip():
        raise SystemExit("运动提示词不能为空")
    base_url = args.url.rstrip("/")
    stats = {} if args.dry_run else request_json(f"{base_url}/system_stats")
    system = stats.get("system", {}) if isinstance(stats, dict) else {}
    input_directory = directory_from_stats(system, "input")
    output_directory = directory_from_stats(system, "output")
    if not args.dry_run and (not isinstance(input_directory, str) or not isinstance(output_directory, str)):
        raise SystemExit("/system_stats 没有返回 input_directory/output_directory")
    input_dir = Path(input_directory) if input_directory else None
    output_dir = Path(output_directory) if output_directory else None

    token = uuid.uuid4().hex[:12]
    if args.dry_run:
        first_name = args.first_frame.name if args.first_frame else None
        last_name = args.last_frame.name if args.last_frame else None
        ref_names = [path.name for path in args.reference_frame]
    else:
        first_name = copy_input(args.first_frame, input_dir, token, "first") if args.first_frame else None
        last_name = copy_input(args.last_frame, input_dir, token, "last") if args.last_frame else None
        ref_names = [copy_input(path, input_dir, token, f"ref{index}") for index, path in enumerate(args.reference_frame)]
    workflow = json.loads(args.workflow.read_text(encoding="utf-8"))
    configure_workflow(
        workflow,
        first_name,
        last_name,
        ref_names,
        prompt,
        args.length,
        args.width,
        args.height,
        args.seed,
        args.output_prefix,
    )
    request_payload = {"prompt": workflow, "client_id": f"codex-{token}"}
    args.out_dir.mkdir(parents=True, exist_ok=True)
    request_path = args.out_dir / f"comfyui-request-{token}.json"
    request_path.write_text(json.dumps(request_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.dry_run:
        print(json.dumps({"status": "dry-run", "request": str(request_path), "input_directory": None, "environment_checked": False}, ensure_ascii=False))
        return 0

    queued = request_json(f"{base_url}/prompt", method="POST", payload=request_payload)
    prompt_id = queued.get("prompt_id")
    if not prompt_id:
        raise SystemExit(f"ComfyUI 未返回 prompt_id：{queued}")
    deadline = time.monotonic() + args.timeout
    history = None
    while time.monotonic() < deadline:
        try:
            history = request_json(f"{base_url}/history/{prompt_id}")
        except (HTTPError, URLError):
            history = None
        if isinstance(history, dict) and prompt_id in history:
            entry = history[prompt_id]
            if entry.get("status", {}).get("status_str") == "error":
                error_path = args.out_dir / f"comfyui-error-{prompt_id}.json"
                error_path.write_text(json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8")
                raise SystemExit(f"ComfyUI 执行失败：{prompt_id}；详情：{error_path}")
            files = output_files(entry.get("outputs", {}))
            if files:
                source = output_dir.joinpath(*files[0].parts)
                if source.is_file():
                    target = args.out_dir / source.name
                    shutil.copy2(source, target)
                    report = {"status": "completed", "prompt_id": prompt_id, "output": str(target), "request": str(request_path)}
                    (args.out_dir / f"comfyui-result-{prompt_id}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
                    print(json.dumps(report, ensure_ascii=False))
                    return 0
        time.sleep(2)
    raise SystemExit(f"ComfyUI 任务超时：{prompt_id}")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (HTTPError, URLError) as exc:
        raise SystemExit(f"ComfyUI 请求失败：{exc}") from exc
