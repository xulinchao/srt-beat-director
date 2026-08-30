#!/usr/bin/env python3
"""Inspect image dimensions, hashes, and approximate subtitle-safe-area occupancy."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from pathlib import Path

from PIL import Image


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("images", nargs="+", type=Path)
    parser.add_argument("--bottom-fraction", type=float, default=0.22)
    parser.add_argument("--threshold", type=int, default=75)
    parser.add_argument("--out", type=Path)
    return parser.parse_args()


def inspect(path: Path, bottom_fraction: float, threshold: int) -> dict:
    image = Image.open(path).convert("RGB")
    width, height = image.size
    pixels = image.load()
    sample_points = [
        (0, 0),
        (width - 1, 0),
        (0, height - 1),
        (width - 1, height - 1),
        (width // 2, height - 1),
    ]
    samples = [pixels[x, y] for x, y in sample_points]
    background = tuple(
        int(statistics.median(sample[channel] for sample in samples)) for channel in range(3)
    )
    start_y = int(height * (1 - bottom_fraction))
    total = width * (height - start_y)
    active = 0
    for y in range(start_y, height):
        for x in range(width):
            distance = sum(abs(pixels[x, y][channel] - background[channel]) for channel in range(3))
            if distance > threshold:
                active += 1

    return {
        "file": str(path.resolve()),
        "width": width,
        "height": height,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "bottom_fraction": bottom_fraction,
        "bottom_active_fraction": round(active / total, 6),
        "estimated_background_rgb": background,
        "note": "Occupancy is an approximate pixel check; visual inspection remains required.",
    }


def main() -> int:
    args = parse_args()
    report = {
        "schema_version": "0.1",
        "images": [inspect(path, args.bottom_fraction, args.threshold) for path in args.images],
    }
    output = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(output, encoding="utf-8")
    print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
