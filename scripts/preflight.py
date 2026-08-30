#!/usr/bin/env python3
"""Validate an SRT/MP3 pair and emit JSON plus Markdown preflight reports."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path


TIMESTAMP_RE = re.compile(
    r"^(?P<sh>\d{1,3}):(?P<sm>\d{2}):(?P<ss>\d{2})[,.](?P<sms>\d{3})\s*-->\s*"
    r"(?P<eh>\d{1,3}):(?P<em>\d{2}):(?P<es>\d{2})[,.](?P<ems>\d{3})(?:\s+.*)?$"
)


@dataclass
class Cue:
    id: int
    start_ms: int
    end_ms: int
    text: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--srt", required=True, type=Path)
    parser.add_argument("--audio", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--duration-tolerance-ms", type=int, default=250)
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_text(path: Path) -> tuple[str, str]:
    data = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-16", "gb18030"):
        try:
            return data.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise ValueError("无法识别 SRT 编码；支持 UTF-8、UTF-16 和 GB18030")


def to_ms(hours: str, minutes: str, seconds: str, millis: str) -> int:
    return ((int(hours) * 60 + int(minutes)) * 60 + int(seconds)) * 1000 + int(millis)


def parse_srt(text: str) -> tuple[list[Cue], list[str]]:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    cues: list[Cue] = []
    errors: list[str] = []
    position = 0

    while position < len(lines):
        if not lines[position].strip():
            position += 1
            continue

        index_line = lines[position].strip()
        if index_line.isdigit():
            position += 1
        if position >= len(lines):
            errors.append(f"字幕块 {index_line} 缺少时间行")
            break

        match = TIMESTAMP_RE.match(lines[position].strip())
        if not match:
            errors.append(f"第 {position + 1} 行不是有效时间戳：{lines[position].strip()}")
            position += 1
            continue

        values = match.groupdict()
        start_ms = to_ms(values["sh"], values["sm"], values["ss"], values["sms"])
        end_ms = to_ms(values["eh"], values["em"], values["es"], values["ems"])
        position += 1
        text_lines: list[str] = []
        while position < len(lines) and lines[position].strip():
            text_lines.append(lines[position].strip())
            position += 1

        cue_id = int(index_line) if index_line.isdigit() else len(cues) + 1
        cues.append(Cue(cue_id, start_ms, end_ms, "\n".join(text_lines)))

    return cues, errors


def audio_duration_ms(path: Path) -> int:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise RuntimeError("未找到 ffprobe，无法读取 MP3 时长")
    completed = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or "未知 ffprobe 错误"
        raise RuntimeError(f"无法读取音频：{detail}")
    value = json.loads(completed.stdout)["format"]["duration"]
    return round(float(value) * 1000)


def build_report(args: argparse.Namespace) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    cues: list[Cue] = []
    encoding = None
    duration_ms = None

    if not args.srt.is_file():
        errors.append(f"SRT 不存在：{args.srt}")
    else:
        try:
            text, encoding = read_text(args.srt)
            cues, parse_errors = parse_srt(text)
            errors.extend(parse_errors)
        except (OSError, ValueError) as exc:
            errors.append(str(exc))

    if not args.audio.is_file():
        errors.append(f"音频不存在：{args.audio}")
    else:
        try:
            duration_ms = audio_duration_ms(args.audio)
        except (OSError, RuntimeError, KeyError, ValueError, json.JSONDecodeError) as exc:
            errors.append(str(exc))

    if not cues and args.srt.is_file():
        errors.append("SRT 中没有有效 cue")

    previous: Cue | None = None
    total_gap_ms = 0
    for cue in cues:
        if not cue.text:
            errors.append(f"cue {cue.id} 文本为空")
        if cue.end_ms <= cue.start_ms:
            errors.append(f"cue {cue.id} 结束时间不晚于开始时间")
        if previous:
            if cue.start_ms < previous.start_ms:
                errors.append(f"cue {cue.id} 时间逆序")
            if cue.start_ms < previous.end_ms:
                errors.append(f"cue {cue.id} 与 cue {previous.id} 重叠")
            elif cue.start_ms > previous.end_ms:
                total_gap_ms += cue.start_ms - previous.end_ms
        previous = cue

    last_end_ms = cues[-1].end_ms if cues else None
    if last_end_ms is not None and duration_ms is not None:
        delta_ms = last_end_ms - duration_ms
        if delta_ms > args.duration_tolerance_ms:
            errors.append(
                f"最后字幕结束时间超过音频 {delta_ms}ms，容差为 {args.duration_tolerance_ms}ms"
            )
        elif abs(delta_ms) > args.duration_tolerance_ms:
            warnings.append(f"音频比最后字幕长 {abs(delta_ms)}ms，请确认尾部留白是否符合预期")

    if total_gap_ms:
        warnings.append(f"字幕 cue 之间共有 {total_gap_ms}ms 空隙；空隙允许存在，但需在分镜时确认")
    warnings.append("本报告只校验结构和时长，未执行音频转写与 SRT 语义一致性核对")

    return {
        "schema_version": "0.1",
        "status": "pass" if not errors else "fail",
        "inputs": {
            "srt": str(args.srt.resolve()),
            "audio": str(args.audio.resolve()),
            "srt_sha256": sha256(args.srt) if args.srt.is_file() else None,
            "audio_sha256": sha256(args.audio) if args.audio.is_file() else None,
        },
        "srt": {
            "encoding": encoding,
            "cue_count": len(cues),
            "first_start_ms": cues[0].start_ms if cues else None,
            "last_end_ms": last_end_ms,
            "total_gap_ms": total_gap_ms,
            "cues": [asdict(cue) for cue in cues],
        },
        "audio": {"duration_ms": duration_ms},
        "checks": {"duration_tolerance_ms": args.duration_tolerance_ms},
        "errors": errors,
        "warnings": warnings,
    }


def markdown(report: dict) -> str:
    def items(values: list[str], empty: str) -> str:
        return "\n".join(f"- {value}" for value in values) if values else f"- {empty}"

    return f"""# 预检报告

- 状态：`{report['status']}`
- SRT cue 数：{report['srt']['cue_count']}
- SRT 编码：{report['srt']['encoding'] or '未知'}
- 最后字幕结束：{report['srt']['last_end_ms']} ms
- 音频时长：{report['audio']['duration_ms']} ms
- cue 间空隙合计：{report['srt']['total_gap_ms']} ms

## 阻塞项

{items(report['errors'], '无')}

## 提醒

{items(report['warnings'], '无')}
"""


def main() -> int:
    args = parse_args()
    report = build_report(args)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "preflight-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (args.out_dir / "preflight-report.md").write_text(markdown(report), encoding="utf-8")
    print(json.dumps({"status": report["status"], "out_dir": str(args.out_dir)}, ensure_ascii=False))
    return 0 if report["status"] == "pass" else 2


if __name__ == "__main__":
    sys.exit(main())
