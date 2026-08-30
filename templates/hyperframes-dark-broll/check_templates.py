#!/usr/bin/env python3
"""Run HyperFrames check against every dark B-roll template in this directory."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default="0.8.19")
    args = parser.parse_args()
    templates_dir = Path(__file__).resolve().parent
    sources = sorted(templates_dir.glob("*-dark-v1.html"))
    failed: list[str] = []
    npx = shutil.which("npx.cmd") or shutil.which("npx")
    if not npx:
        print(json.dumps({"status": "fail", "error": "找不到 npx"}, ensure_ascii=False))
        return 2

    with tempfile.TemporaryDirectory(prefix="knowledge-abroll-hf-") as temporary:
        for source in sources:
            project = Path(temporary) / source.stem
            project.mkdir()
            shutil.copy2(source, project / "index.html")
            shutil.copy2(templates_dir / "shared.css", project / "shared.css")
            shutil.copy2(templates_dir / "hyperframes.json", project / "hyperframes.json")
            completed = subprocess.run(
                [npx, "--yes", f"hyperframes@{args.version}", "check", str(project), "--json"],
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                check=False,
            )
            if completed.returncode:
                failed.append(source.stem)
                print(completed.stdout)
                print(completed.stderr)

    report = {
        "status": "pass" if not failed and sources else "fail",
        "template_count": len(sources),
        "passed_count": len(sources) - len(failed),
        "failed": failed,
    }
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
