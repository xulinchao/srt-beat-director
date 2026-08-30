#!/usr/bin/env python3
"""Check every standalone HyperFrames B-roll template through a temporary index project."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--templates-dir", required=True, type=Path)
    parser.add_argument("--version", default="0.8.19")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    templates_dir = args.templates_dir.resolve()
    html_files = sorted(path for path in templates_dir.glob("*-dark-v1.html") if path.is_file())
    if not html_files:
        print(json.dumps({"status": "fail", "error": "未找到 *-dark-v1.html"}, ensure_ascii=False))
        return 2

    results: list[dict] = []
    npx = shutil.which("npx.cmd") or shutil.which("npx")
    if not npx:
        print(json.dumps({"status": "fail", "error": "找不到 npx"}, ensure_ascii=False))
        return 2
    with tempfile.TemporaryDirectory(prefix="knowledge-abroll-hf-") as temporary:
        root = Path(temporary)
        for source in html_files:
            project = root / source.stem
            project.mkdir()
            shutil.copy2(source, project / "index.html")
            shutil.copy2(templates_dir / "shared.css", project / "shared.css")
            shutil.copy2(templates_dir / "hyperframes.json", project / "hyperframes.json")
            command = [
                npx,
                "--yes",
                f"hyperframes@{args.version}",
                "check",
                str(project),
                "--json",
            ]
            completed = subprocess.run(
                command,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                check=False,
            )
            results.append(
                {
                    "template": source.stem,
                    "passed": completed.returncode == 0,
                    "exit_code": completed.returncode,
                    "stdout": completed.stdout,
                    "stderr": completed.stderr,
                }
            )

    failed = [item for item in results if not item["passed"]]
    report = {
        "status": "pass" if not failed else "fail",
        "template_count": len(results),
        "passed_count": len(results) - len(failed),
        "failed": [item["template"] for item in failed],
    }
    print(json.dumps(report, ensure_ascii=False))
    if failed:
        for item in failed:
            print(item["stdout"])
            print(item["stderr"])
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
