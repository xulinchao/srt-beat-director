#!/usr/bin/env python3
"""Read-only ComfyUI environment and workflow capability probe."""
from __future__ import annotations
import argparse, json, os, urllib.request
from pathlib import Path

def get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))

def directory_from_argv(system: dict, flag: str) -> str | None:
    direct = system.get(f"{flag}_directory")
    if isinstance(direct, str) and direct:
        return direct
    argv = system.get("argv", [])
    if isinstance(argv, list):
        for index, value in enumerate(argv[:-1]):
            if value == f"--{flag}-directory" and isinstance(argv[index + 1], str):
                return argv[index + 1]
    return None

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8188")
    parser.add_argument("--workflow", action="append", default=[])
    parser.add_argument("--out-dir", type=Path)
    args = parser.parse_args()
    report = {"url": args.url.rstrip("/"), "status": "failed", "system": None, "workflows": []}
    object_cache = {}

    def object_info(class_name: str) -> dict:
        if class_name not in object_cache:
            object_cache[class_name] = get_json(report["url"] + "/object_info/" + class_name).get(class_name, {})
        return object_cache[class_name]

    try:
        report["system"] = get_json(report["url"] + "/system_stats")
        system = report["system"].get("system", {})
        devices = report["system"].get("devices", [])
        input_dir = directory_from_argv(system, "input")
        output_dir = directory_from_argv(system, "output")
        report["paths"] = {
            "input": {"path": input_dir, "exists": bool(input_dir and os.path.isdir(input_dir)), "writable": bool(input_dir and os.access(input_dir, os.W_OK))},
            "output": {"path": output_dir, "exists": bool(output_dir and os.path.isdir(output_dir)), "writable": bool(output_dir and os.access(output_dir, os.W_OK))},
        }
        report["cuda_devices"] = [device for device in devices if device.get("type") == "cuda"]
        checks = [
            bool(report["cuda_devices"]),
            report["paths"]["input"]["exists"] and report["paths"]["input"]["writable"],
            report["paths"]["output"]["exists"] and report["paths"]["output"]["writable"],
        ]
        report["status"] = "pass" if all(checks) else "failed"
        if report["status"] != "pass":
            report["error"] = "CUDA 或 ComfyUI input/output 目录检查未通过"
    except Exception as exc:
        report["error"] = str(exc)
    for raw in args.workflow:
        path = Path(raw)
        item = {"path": str(path), "exists": path.is_file()}
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                nodes = [
                    {"id": node_id, "class_type": node.get("class_type"), "inputs": sorted((node.get("inputs") or {}).keys())}
                    for node_id, node in data.items() if isinstance(node, dict) and node.get("class_type")
                ]
                item["nodes"] = nodes
                item["required_classes"] = sorted({node["class_type"] for node in nodes if node.get("class_type")})
                item["missing_classes"] = [
                    class_name for class_name in item["required_classes"] if not object_info(class_name)
                ]
                model_fields = {"unet_name": "UNETLoader", "clip_name": "CLIPLoader", "vae_name": "VAELoader", "lora_name": "LoraLoaderModelOnly"}
                missing_models = {}
                for node in data.values():
                    if not isinstance(node, dict):
                        continue
                    for field, class_name in model_fields.items():
                        value = (node.get("inputs") or {}).get(field)
                        if not isinstance(value, str):
                            continue
                        required = object_info(class_name).get("input", {}).get("required", {})
                        choices = required.get(field, [[]])
                        choices = choices[0] if isinstance(choices, list) and choices else []
                        if isinstance(choices, list) and value not in choices:
                            missing_models.setdefault(field, []).append(value)
                item["missing_models"] = {key: sorted(set(values)) for key, values in missing_models.items()}
                item["has_first_frame"] = any("first_frame" in (node.get("inputs") or {}) for node in data.values() if isinstance(node, dict))
                item["has_last_frame"] = any("last_frame" in (node.get("inputs") or {}) for node in data.values() if isinstance(node, dict))
                item["has_first_last_frame"] = item["has_first_frame"] and item["has_last_frame"]
                item["has_reference_images"] = any("ref_images" in key for node in data.values() if isinstance(node, dict) for key in (node.get("inputs") or {}))
                item["has_prompt"] = any("prompt" in (node.get("inputs") or {}) for node in data.values() if isinstance(node, dict))
                if item["missing_classes"] or item["missing_models"]:
                    report["status"] = "failed"
            except Exception as exc:
                item["error"] = str(exc)
                report["status"] = "failed"
        report["workflows"].append(item)
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out_dir:
        args.out_dir.mkdir(parents=True, exist_ok=True)
        (args.out_dir / "environment-report.json").write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0 if report["status"] == "pass" else 2

if __name__ == "__main__":
    raise SystemExit(main())
