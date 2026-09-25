"""Submit a ComfyUI API image workflow and collect its image output."""

from __future__ import annotations

import argparse
import json
import shutil
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


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
    result = []
    for part in str(value).split(":"):
        try:
            result.append(int(part))
        except ValueError:
            result.append(10**9)
    return tuple(result)


def copy_input(path: Path, input_dir: Path, token: str, label: str) -> str:
    input_dir.mkdir(parents=True, exist_ok=True)
    target = input_dir / f"codex_{token}_{label}{path.suffix.lower()}"
    shutil.copy2(path, target)
    return target.name


def nodes_of(workflow: dict[str, Any], class_names: set[str]) -> list[tuple[str, dict[str, Any]]]:
    return [
        (node_id, node)
        for node_id, node in sorted(workflow.items(), key=lambda item: numeric_key(item[0]))
        if node.get("class_type") in class_names
    ]


def set_prompt(workflow: dict[str, Any], prompt: str, negative_prompt: str | None) -> None:
    prompt_slots: list[dict[str, Any]] = []
    positive_replaced = False
    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs") or {}
        if "prompt" in inputs:
            prompt_slots.append(inputs)
            if str(inputs.get("prompt") or "").strip():
                inputs["prompt"] = prompt
                positive_replaced = True
        if "text" in inputs:
            prompt_slots.append(inputs)
            if str(inputs.get("text") or "").strip():
                inputs["text"] = prompt
                positive_replaced = True
        if negative_prompt is not None and "negative_prompt" in inputs:
            inputs["negative_prompt"] = negative_prompt
    if not positive_replaced and prompt_slots:
        slot = prompt_slots[0]
        slot["prompt" if "prompt" in slot else "text"] = prompt


def set_resolution(workflow: dict[str, Any], width: int | None, height: int | None) -> None:
    if width is None and height is None:
        return
    if width is None or height is None:
        raise ValueError("--width 和 --height 必须同时提供")
    if width <= 0 or height <= 0 or width % 32 or height % 32:
        raise ValueError("宽高必须为正数且是 32 的倍数")
    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        class_name = node.get("class_type")
        inputs = node.get("inputs") or {}
        if class_name in {"EmptyLatentImage", "EmptySD3LatentImage"}:
            if "width" in inputs:
                inputs["width"] = width
            if "height" in inputs:
                inputs["height"] = height
        if class_name == "ComfySwitchNode":
            selected = inputs.get("on_true")
            if isinstance(selected, list) and selected and workflow.get(selected[0], {}).get("class_type") in {"EmptyLatentImage", "EmptySD3LatentImage"}:
                inputs["switch"] = True


def set_seed(workflow: dict[str, Any], seed: int | None) -> None:
    if seed is None:
        return
    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs") or {}
        if "seed" in inputs:
            inputs["seed"] = seed
        if node.get("class_type") == "RandomNoise" and "noise_seed" in inputs:
            inputs["noise_seed"] = seed


def set_output_prefix(workflow: dict[str, Any], prefix: str) -> None:
    for node in workflow.values():
        if isinstance(node, dict) and node.get("class_type") in {"SaveImage", "SaveImageAdvanced"}:
            inputs = node.setdefault("inputs", {})
            if "filename_prefix" in inputs:
                inputs["filename_prefix"] = prefix


def configure_workflow(
    workflow: dict[str, Any],
    input_names: list[str],
    mask_name: str | None,
    prompt: str,
    negative_prompt: str | None,
    width: int | None,
    height: int | None,
    seed: int | None,
    output_prefix: str,
) -> None:
    loads = nodes_of(workflow, {"LoadImage"})
    masks = nodes_of(workflow, {"LoadImageMask"})
    if len(input_names) != len(loads):
        if loads:
            raise ValueError(f"工作流需要 {len(loads)} 张输入图，当前提供 {len(input_names)} 张")
        if input_names:
            raise ValueError("该工作流不接收输入图")
    for (_, node), image_name in zip(loads, input_names):
        node.setdefault("inputs", {})["image"] = image_name
    if masks:
        if not mask_name:
            raise ValueError("工作流包含 LoadImageMask，必须提供 --mask")
        for _, node in masks:
            node.setdefault("inputs", {})["image"] = mask_name
    elif mask_name:
        raise ValueError("该工作流不接收 mask")
    set_prompt(workflow, prompt, negative_prompt)
    set_resolution(workflow, width, height)
    set_seed(workflow, seed)
    set_output_prefix(workflow, output_prefix)


def output_files(value: Any) -> list[Path]:
    found: list[Path] = []
    if isinstance(value, dict):
        filename = value.get("filename")
        if isinstance(filename, str) and Path(filename).suffix.lower() in IMAGE_EXTENSIONS:
            found.append(Path(value.get("subfolder") or "") / filename)
        for child in value.values():
            found.extend(output_files(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(output_files(child))
    return found


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="运行 ComfyUI 本地图片工作流")
    parser.add_argument("--url", default="http://127.0.0.1:8188")
    parser.add_argument("--workflow", type=Path, required=True)
    parser.add_argument("--input", type=Path, action="append", default=[])
    parser.add_argument("--mask", type=Path)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--negative-prompt")
    parser.add_argument("--width", type=int)
    parser.add_argument("--height", type=int)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--output-prefix", default="codex/local-image")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    for path in [args.workflow, *args.input, args.mask]:
        if path is not None and not path.is_file():
            raise SystemExit(f"文件不存在：{path}")
    base_url = args.url.rstrip("/")
    stats = request_json(f"{base_url}/system_stats")
    system = stats.get("system", {}) if isinstance(stats, dict) else {}
    input_directory = directory_from_stats(system, "input")
    output_directory = directory_from_stats(system, "output")
    if not isinstance(input_directory, str) or not isinstance(output_directory, str):
        raise SystemExit("/system_stats 没有返回 input_directory/output_directory")
    input_dir = Path(input_directory)
    output_dir = Path(output_directory)
    token = uuid.uuid4().hex[:12]
    if args.dry_run:
        input_names = [path.name for path in args.input]
        mask_name = args.mask.name if args.mask else None
    else:
        input_names = [copy_input(path, input_dir, token, f"input{index}") for index, path in enumerate(args.input)]
        mask_name = copy_input(args.mask, input_dir, token, "mask") if args.mask else None
    workflow = json.loads(args.workflow.read_text(encoding="utf-8"))
    configure_workflow(workflow, input_names, mask_name, args.prompt, args.negative_prompt, args.width, args.height, args.seed, args.output_prefix)
    request_payload = {"prompt": workflow, "client_id": f"codex-image-{token}"}
    args.out_dir.mkdir(parents=True, exist_ok=True)
    request_path = args.out_dir / f"comfyui-image-request-{token}.json"
    request_path.write_text(json.dumps(request_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.dry_run:
        print(json.dumps({"status": "dry-run", "request": str(request_path), "input_directory": str(input_dir)}, ensure_ascii=False))
        return 0
    queued = request_json(f"{base_url}/prompt", method="POST", payload=request_payload)
    prompt_id = queued.get("prompt_id")
    if not prompt_id:
        raise SystemExit(f"ComfyUI 未返回 prompt_id：{queued}")
    deadline = time.monotonic() + args.timeout
    while time.monotonic() < deadline:
        try:
            history = request_json(f"{base_url}/history/{prompt_id}")
        except (HTTPError, URLError):
            history = None
        if isinstance(history, dict) and prompt_id in history:
            files = output_files(history[prompt_id])
            if files:
                source = output_dir.joinpath(*files[0].parts)
                if source.is_file():
                    target = args.out_dir / source.name
                    shutil.copy2(source, target)
                    report = {"status": "completed", "prompt_id": prompt_id, "output": str(target), "request": str(request_path)}
                    (args.out_dir / f"comfyui-image-result-{prompt_id}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
                    print(json.dumps(report, ensure_ascii=False))
                    return 0
        time.sleep(2)
    raise SystemExit(f"ComfyUI 任务超时：{prompt_id}")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (HTTPError, URLError) as exc:
        raise SystemExit(f"ComfyUI 请求失败：{exc}") from exc
