"""Decode every frame and flag black frames and large adjacent-frame changes for review."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

from media_evidence import digest, probe_video


def scan(path: Path, black_level: int = 20, black_fraction: float = 0.98, difference: float = 35) -> dict:
    if not 0 <= black_level <= 255 or not 0 < black_fraction <= 1 or not 0 < difference <= 255:
        raise ValueError("扫描阈值越界")
    executable = shutil.which("ffmpeg")
    if not executable:
        raise ValueError("未找到 ffmpeg，无法逐帧扫描")
    initial_hash = digest(path)
    media = probe_video(path)
    width, height = 160, 90
    size = width * height
    candidates, previous, count = [], None, 0
    # Decode every frame; spatial reduction bounds memory and makes the detector reproducible.
    command = [executable, "-v", "error", "-xerror", "-i", str(path), "-map", "0:V:0", "-an",
               "-vf", f"scale={width}:{height}:flags=area,format=gray", "-fps_mode", "passthrough",
               "-f", "rawvideo", "pipe:1"]
    with tempfile.TemporaryFile() as log:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=log)
        try:
            while True:
                frame = bytearray()
                while len(frame) < size:
                    chunk = process.stdout.read(size - len(frame))
                    if not chunk:
                        break
                    frame.extend(chunk)
                if not frame:
                    break
                if len(frame) != size:
                    raise ValueError("解码得到不完整帧")
                reasons = []
                fraction = sum(value <= black_level for value in frame) / size
                delta = sum(abs(a - b) for a, b in zip(frame, previous)) / size if previous is not None else 0
                if fraction >= black_fraction:
                    reasons.append("black")
                if delta >= difference:
                    reasons.append("adjacent-change")
                if reasons:
                    candidates.append({"frame": count, "time_ms": round(count * 1000 / media["fps"], 3),
                                       "reasons": reasons, "black_fraction": round(fraction, 5),
                                       "mean_absolute_difference": round(delta, 3), "review": None})
                previous, count = frame, count + 1
            process.wait(timeout=30)
            log.seek(0)
            stderr = log.read().decode("utf-8", errors="replace").strip()
            if process.returncode or stderr:
                raise ValueError(f"逐帧解码失败：{stderr[:1000]}")
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            process.stdout.close()
    if count != media["decoded_frames"] or initial_hash != digest(path):
        raise ValueError("扫描帧数不一致或扫描期间文件发生变化")
    return {"schema_version": "1.0", "artifact_path": str(path.resolve()), "artifact_sha256": initial_hash,
            "scanned_at": datetime.now(timezone.utc).isoformat(), "scan_complete": True,
            "fps": media["fps"], "decoded_frames": count, "media": media,
            "detector": {"name": "grayscale-adjacent-v1", "width": width, "height": height,
                         "black_level": black_level, "black_fraction": black_fraction, "difference": difference},
            "candidates": candidates}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("报告已存在；使用新文件名，保留历史扫描与审阅记录")
    try:
        report = scan(args.video)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"scan_complete": True, "candidates": len(report["candidates"]), "out": str(args.out)}))
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        parser.exit(2, str(exc) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
