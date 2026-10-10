"""Resolve visual cuts without moving semantic ranges or narration beats."""
from __future__ import annotations

import math


def cut_ms(shot: dict) -> int:
    transition = shot.get("transition") or {}
    if not isinstance(transition, dict):
        raise ValueError(f"{shot.get('id')} transition 必须为对象")
    offset = 0
    if "visual_cut" in transition:
        cut = transition["visual_cut"]
        if not isinstance(cut, dict) or type(cut.get("offset_ms")) is not int:
            raise ValueError(f"{shot.get('id')} visual_cut.offset_ms 必须为整数毫秒")
        offset = cut["offset_ms"]
    if type(shot.get("start_ms")) is not int:
        raise ValueError(f"{shot.get('id')} start_ms 必须为整数毫秒")
    return shot["start_ms"] + offset


def display_ranges(shots: list[dict], end_ms: float) -> list[list[float]]:
    """One boundary per seam; first/tail holds retain their existing behavior."""
    starts = [0 if i == 0 else cut_ms(shot) for i, shot in enumerate(shots)]
    return [[start, starts[i + 1] if i + 1 < len(starts) else end_ms]
            for i, start in enumerate(starts)]


def validate_visual_cuts(plan: dict, fps: float, end_ms: float | None = None) -> list[str]:
    shots = plan.get("shots") or []
    declared = [i for i, s in enumerate(shots)
                if isinstance(s.get("transition"), dict) and "visual_cut" in s["transition"]]
    if not declared:
        return []  # Legacy plans keep their existing validation contract.
    errors = []
    if type(fps) not in (int, float) or not math.isfinite(fps) or fps <= 0:
        return ["visual_cut 校验需要有效 fps"]
    try:
        for i in declared:
            shot = shots[i]
            cut_ms(shot)
            cut = shot["transition"]["visual_cut"]
            if i == 0:
                errors.append("首镜不能声明 visual_cut；从第 0 帧开始")
            for key in ("reason", "bridge"):
                if not isinstance(cut.get(key), str) or not cut[key].strip():
                    errors.append(f"{shot.get('id')} visual_cut 缺少 {key}")
        end_ms = end_ms if end_ms is not None else shots[-1]["end_ms"]
        if type(end_ms) not in (int, float) or not math.isfinite(end_ms) or end_ms <= 0:
            raise ValueError("visual_cut 校验需要有效总时长")
        ranges = display_ranges(shots, end_ms)
        frame = lambda ms: math.floor(ms * fps / 1000 + 0.5)
        for i, (shot, (start, end)) in enumerate(zip(shots, ranges)):
            if not 0 <= start < end <= end_ms or frame(end) <= frame(start):
                errors.append(f"{shot.get('id')} visual_cut 导致范围越界、倒序或不足一帧")
            if i not in declared and i + 1 not in declared:
                continue
            for beat in shot.get("narration_beats") or []:
                at = beat.get("at_ms") if isinstance(beat, dict) else None
                if type(at) is not int or not (start <= at < end and frame(start) <= frame(at) < frame(end)):
                    errors.append(f"{shot.get('id')} visual_cut 遮掉旁白节拍 {at}；不能平移或删除节拍来迁就切点")
    except (ValueError, KeyError, TypeError) as exc:
        errors.append(str(exc))
    return errors
