"""Read actual media streams and validate frame-scan evidence. No third-party dependencies."""
from __future__ import annotations

import hashlib
import json
import math
import shutil
import subprocess
from fractions import Fraction
from pathlib import Path


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def probe_video(path: Path) -> dict:
    executable = shutil.which("ffprobe")
    if not executable:
        raise ValueError("未找到 ffprobe，无法验证实际视频；安装或加入 PATH 后重试")
    result = subprocess.run(
        [executable, "-v", "error", "-count_frames", "-show_streams", "-show_format", "-show_frames",
         "-show_entries", "stream:format:frame=media_type,best_effort_timestamp_time", "-of", "json", str(path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600,
    )
    if result.returncode or result.stderr.strip():
        raise ValueError(f"视频探测/解码失败：{result.stderr.strip()[:1000]}")
    data = json.loads(result.stdout)
    videos = [s for s in data.get("streams", []) if s.get("codec_type") == "video" and not s.get("disposition", {}).get("attached_pic")]
    audios = [s for s in data.get("streams", []) if s.get("codec_type") == "audio"]
    if len(videos) != 1:
        raise ValueError("交付文件必须包含一个主视频流")
    stream = videos[0]
    try:
        fps = float(Fraction(stream["avg_frame_rate"]))
        frames = int(stream["nb_read_frames"])
        duration_ms = float(stream["duration"]) * 1000
        if not all(math.isfinite(v) and v > 0 for v in (fps, frames, duration_ms)):
            raise ValueError("nonpositive metadata")
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
        raise ValueError("视频缺少有效帧率、解码帧数或视频流时长") from exc
    timestamps = [float(f["best_effort_timestamp_time"]) for f in data.get("frames", [])
                  if f.get("media_type") == "video" and "best_effort_timestamp_time" in f]
    if len(timestamps) != frames or any(not math.isfinite(v) for v in timestamps):
        raise ValueError("视频逐帧时间戳缺失或无效")
    if any(abs((value - timestamps[0]) - index / fps) > 0.001 for index, value in enumerate(timestamps)):
        raise ValueError("视频不是稳定固定帧率，不能使用当前帧映射与扫描时间")
    return {
        "width": stream["width"], "height": stream["height"], "fps": fps,
        "decoded_frames": frames, "duration_ms": duration_ms,
        "start_ms": float(stream.get("start_time", 0)) * 1000,
        "audio_streams": len(audios), "codec": stream.get("codec_name"),
        "audio_durations_ms": [float(s["duration"]) * 1000 for s in audios if s.get("duration") not in (None, "N/A")],
    }


def validate_scan(project_dir: Path, reference: object, final_path: Path, media: dict) -> list[str]:
    errors = []
    if not isinstance(reference, dict) or not reference.get("path") or not reference.get("sha256"):
        return ["QA 缺少 frame_scan 的报告路径与 SHA-256"]
    path = project_dir / reference["path"]
    try:
        if digest(path) != reference["sha256"]:
            errors.append("逐帧扫描报告哈希不一致")
        report = json.loads(path.read_text(encoding="utf-8"))
        if report.get("schema_version") != "1.0" or report.get("scan_complete") is not True:
            errors.append("逐帧扫描未完整完成或版本无效")
        if report.get("artifact_sha256") != digest(final_path):
            errors.append("逐帧扫描绑定的不是当前成片")
        scan_fps = float(report.get("fps", 0))
        if report.get("decoded_frames") != media["decoded_frames"] or not math.isfinite(scan_fps) or abs(scan_fps - media["fps"]) > 0.001:
            errors.append("逐帧扫描帧数或帧率与实际视频不一致")
        if not isinstance(report.get("candidates"), list):
            errors.append("逐帧扫描缺少候选帧列表")
        for candidate in report.get("candidates", []):
            frame = candidate.get("frame")
            if type(frame) is not int or not 0 <= frame < media["decoded_frames"]:
                errors.append("逐帧扫描候选帧号无效")
            review = candidate.get("review") or {}
            if review.get("decision") != "accepted" or not str(review.get("reason") or "").strip():
                errors.append(f"异常候选帧 {frame} 尚未解释并接受；坏帧应修复重扫")
            evidence = review.get("evidence")
            if not isinstance(evidence, dict) or not evidence.get("path") or not evidence.get("sha256"):
                errors.append(f"异常候选帧 {frame} 缺少前后帧复核证据")
            elif digest(project_dir / evidence["path"]) != evidence["sha256"]:
                errors.append(f"异常候选帧 {frame} 复核证据哈希不一致")
    except (OSError, ValueError, TypeError, KeyError) as exc:
        errors.append(f"逐帧扫描证据不可验证：{exc}")
    return errors
