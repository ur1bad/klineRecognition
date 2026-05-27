from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from collections import defaultdict
from datetime import datetime

import matplotlib
import mplfinance as mpf
import numpy as np
import pandas as pd
from PIL import Image

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from kline_core.labeling import (
    check_ascending_triangle,
    check_descending_triangle,
    check_double_bottom,
    check_double_top,
    check_head_and_shoulders_bottom,
    check_head_and_shoulders_top,
)

matplotlib.use("Agg")

WINDOW_SIZE = 30
IMAGE_SIZE = (448, 448)
TMP_FIGSIZE = (8, 8)
TMP_DPI = 100
DEFAULT_TARGET_PER_PATTERN = 150
MANIFEST_FILENAME = ".synthetic_signature_manifest.json"

PATTERN_CONFIG = {
    "double_bottom": {
        "folder": "double_bottom",
        "prefix": "DoubleBottom",
        "validator": check_double_bottom,
    },
    "double_top": {
        "folder": "double_top",
        "prefix": "DoubleTop",
        "validator": check_double_top,
    },
    "head_and_shoulders_top": {
        "folder": "head_and_shoulders_top",
        "prefix": "HeadAndShouldersTop",
        "validator": check_head_and_shoulders_top,
    },
    "head_and_shoulders_bottom": {
        "folder": "head_and_shoulders_bottom",
        "prefix": "HeadAndShouldersBottom",
        "validator": check_head_and_shoulders_bottom,
    },
    "ascending_triangle": {
        "folder": "ascending_triangle",
        "prefix": "AscendingTriangle",
        "validator": check_ascending_triangle,
    },
    "descending_triangle": {
        "folder": "descending_triangle",
        "prefix": "DescendingTriangle",
        "validator": check_descending_triangle,
    },
}


def moving_average(values, window=3):
    arr = np.asarray(values, dtype=float)
    win = max(1, int(window))
    if win <= 1 or arr.size < win:
        return arr.copy()
    if win % 2 == 0:
        win += 1
    pad = win // 2
    padded = np.pad(arr, (pad, pad), mode="edge")
    kernel = np.ones(win, dtype=float) / win
    return np.convolve(padded, kernel, mode="valid")


def build_style():
    return mpf.make_mpf_style(
        base_mpf_style="yahoo",
        gridstyle="",
        rc={"font.size": 0, "lines.linewidth": 1.0},
    )


def save_and_resize_chart(df_subset, save_path, style):
    tmp_file = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_file = tmp.name

        mpf.plot(
            df_subset,
            type="candle",
            style=style,
            volume=False,
            axisoff=True,
            figsize=TMP_FIGSIZE,
            savefig={
                "fname": tmp_file,
                "dpi": TMP_DPI,
                "bbox_inches": "tight",
                "pad_inches": 0,
            },
        )

        with Image.open(tmp_file) as img:
            img = img.convert("RGB")
            img = img.resize(IMAGE_SIZE, Image.Resampling.LANCZOS)
            img.save(save_path)
    finally:
        if tmp_file and os.path.exists(tmp_file):
            os.remove(tmp_file)


def linear_interpolate_skeleton(points, length):
    points = sorted(points, key=lambda item: item[0])
    x_points = np.array([p[0] for p in points], dtype=float)
    y_points = np.array([p[1] for p in points], dtype=float)
    x_grid = np.arange(length, dtype=float)
    interpolated = np.interp(x_grid, x_points, y_points)
    return moving_average(interpolated, window=3)


def add_noise_and_derive_ohlc(base_close, rng):
    n = len(base_close)
    close = np.asarray(base_close, dtype=float)

    noise_scale = rng.uniform(0.22, 0.55)
    close = close + rng.normal(0.0, noise_scale, n)
    close = close + np.cumsum(rng.normal(0.0, noise_scale * 0.03, n))
    close = np.maximum(close, 1.0)

    opens = np.empty(n, dtype=float)
    opens[0] = close[0] * (1 + rng.normal(0.0, 0.0025))
    for i in range(1, n):
        opens[i] = close[i - 1] * (1 + rng.normal(0.0, 0.004))

    upper_wick = np.abs(rng.normal(0.0055, 0.002, n))
    lower_wick = np.abs(rng.normal(0.0055, 0.002, n))

    highs = np.maximum(opens, close) * (1 + upper_wick)
    lows = np.minimum(opens, close) * (1 - lower_wick)
    lows = np.maximum(lows, 0.01)

    volumes = rng.integers(800_000, 8_500_000, size=n, endpoint=False)
    dates = pd.date_range("2024-01-01", periods=n, freq="B")

    return pd.DataFrame(
        {
            "Open": opens,
            "High": highs,
            "Low": lows,
            "Close": close,
            "Volume": volumes,
        },
        index=dates,
    )


def skeleton_double_bottom(rng, length):
    b1 = rng.uniform(84.0, 90.0)
    b2 = b1 * (1 + rng.uniform(-0.025, 0.025))
    neck = rng.uniform(97.0, 103.0)
    start = neck + rng.uniform(4.0, 8.0)
    post_break = neck * (1 + rng.uniform(0.012, 0.04))
    ending = post_break + rng.uniform(1.5, 5.0)

    return [
        (0, start),
        (4, start - rng.uniform(4.0, 7.0)),
        (8, b1),
        (12, neck),
        (18, b2),
        (22, neck + rng.uniform(0.6, 2.0)),
        (26, post_break),
        (length - 1, ending),
    ]


def skeleton_double_top(rng, length):
    t1 = rng.uniform(108.0, 116.0)
    t2 = t1 * (1 + rng.uniform(-0.025, 0.02))
    neck = rng.uniform(93.0, 99.5)
    start = neck - rng.uniform(7.0, 10.0)
    ending = neck - rng.uniform(7.0, 12.0)

    return [
        (0, start),
        (4, start + rng.uniform(4.0, 8.0)),
        (8, t1),
        (12, neck),
        (18, t2),
        (22, neck - rng.uniform(1.0, 3.0)),
        (26, neck - rng.uniform(3.5, 6.5)),
        (length - 1, ending),
    ]


def skeleton_head_shoulders_top(rng, length):
    left_shoulder = rng.uniform(108.0, 113.0)
    right_shoulder = left_shoulder * (1 + rng.uniform(-0.045, 0.045))
    head = max(left_shoulder, right_shoulder) * (1 + rng.uniform(0.04, 0.09))
    neck1 = rng.uniform(95.0, 101.0)
    neck2 = neck1 * (1 + rng.uniform(-0.02, 0.02))
    ending = min(neck1, neck2) - rng.uniform(5.0, 9.0)

    return [
        (0, neck1 - rng.uniform(6.0, 10.0)),
        (3, neck1 + rng.uniform(1.0, 3.5)),
        (7, left_shoulder),
        (10, neck1),
        (15, head),
        (19, neck2),
        (23, right_shoulder),
        (26, min(neck1, neck2) - rng.uniform(2.0, 5.0)),
        (length - 1, ending),
    ]


def skeleton_head_shoulders_bottom(rng, length):
    left_shoulder = rng.uniform(87.0, 92.0)
    right_shoulder = left_shoulder * (1 + rng.uniform(-0.045, 0.045))
    head = min(left_shoulder, right_shoulder) * (1 - rng.uniform(0.04, 0.09))
    neck1 = rng.uniform(100.0, 106.0)
    neck2 = neck1 * (1 + rng.uniform(-0.02, 0.02))
    ending = max(neck1, neck2) + rng.uniform(5.0, 9.0)

    return [
        (0, neck1 + rng.uniform(5.0, 9.0)),
        (3, neck1 - rng.uniform(1.0, 3.0)),
        (7, left_shoulder),
        (10, neck1),
        (15, head),
        (19, neck2),
        (23, right_shoulder),
        (26, max(neck1, neck2) + rng.uniform(2.0, 5.0)),
        (length - 1, ending),
    ]


def skeleton_ascending_triangle(rng, length):
    resistance = rng.uniform(108.0, 114.0)
    low1 = resistance - rng.uniform(18.0, 23.0)
    low2 = low1 + rng.uniform(4.0, 7.0)
    low3 = low2 + rng.uniform(3.0, 6.0)
    breakout = resistance + rng.uniform(2.8, 6.5)
    ending = breakout + rng.uniform(1.0, 4.0)

    return [
        (0, low1 + rng.uniform(2.0, 5.0)),
        (4, low1),
        (7, resistance * (1 + rng.uniform(-0.006, 0.006))),
        (11, low2),
        (15, resistance * (1 + rng.uniform(-0.006, 0.006))),
        (19, low3),
        (23, resistance * (1 + rng.uniform(-0.006, 0.006))),
        (25, low3 + rng.uniform(1.0, 3.0)),
        (27, breakout),
        (length - 1, ending),
    ]


def skeleton_descending_triangle(rng, length):
    support = rng.uniform(86.0, 92.0)
    high1 = support + rng.uniform(18.0, 24.0)
    high2 = high1 - rng.uniform(4.0, 7.0)
    high3 = high2 - rng.uniform(3.0, 6.0)
    breakdown = support - rng.uniform(2.6, 6.2)
    ending = breakdown - rng.uniform(1.0, 4.0)

    return [
        (0, high1 - rng.uniform(2.0, 5.0)),
        (4, high1),
        (7, support * (1 + rng.uniform(-0.006, 0.006))),
        (11, high2),
        (15, support * (1 + rng.uniform(-0.006, 0.006))),
        (19, high3),
        (23, support * (1 + rng.uniform(-0.006, 0.006))),
        (25, high3 - rng.uniform(1.0, 3.0)),
        (27, breakdown),
        (length - 1, ending),
    ]


SKELETON_BUILDERS = {
    "double_bottom": skeleton_double_bottom,
    "double_top": skeleton_double_top,
    "head_and_shoulders_top": skeleton_head_shoulders_top,
    "head_and_shoulders_bottom": skeleton_head_shoulders_bottom,
    "ascending_triangle": skeleton_ascending_triangle,
    "descending_triangle": skeleton_descending_triangle,
}


def build_synthetic_ohlc(pattern_name, rng, length):
    points = SKELETON_BUILDERS[pattern_name](rng, length)
    base_close = linear_interpolate_skeleton(points, length=length)
    return add_noise_and_derive_ohlc(base_close, rng)


def calc_signature(df):
    arr = np.round(df[["Open", "High", "Low", "Close"]].to_numpy(dtype=np.float32), 4)
    return hashlib.sha1(arr.tobytes()).hexdigest()


def get_manifest_path(output_root):
    return os.path.join(output_root, MANIFEST_FILENAME)


def load_manifest(manifest_path):
    if not os.path.exists(manifest_path):
        return defaultdict(set)

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        return defaultdict(set)

    pattern_data = raw.get("patterns", raw)
    data = defaultdict(set)
    for pattern_name, signatures in pattern_data.items():
        if isinstance(signatures, list):
            data[pattern_name].update(signatures)
    return data


def save_manifest(manifest_path, signatures_by_pattern):
    payload = {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "patterns": {
            pattern_name: sorted(list(signatures))
            for pattern_name, signatures in sorted(signatures_by_pattern.items())
        },
    }
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def next_file_index(folder_path):
    max_idx = 0
    for name in os.listdir(folder_path):
        if not name.lower().endswith(".png"):
            continue
        stem = os.path.splitext(name)[0]
        parts = stem.split("_")
        if parts and parts[-1].isdigit():
            max_idx = max(max_idx, int(parts[-1]))
    return max_idx + 1


def generate_one_pattern(
    pattern_name,
    target_per_pattern,
    output_root,
    style,
    rng,
    signatures_by_pattern,
    global_signatures,
    window_size,
    max_attempt_factor,
):
    cfg = PATTERN_CONFIG[pattern_name]
    folder = os.path.join(output_root, cfg["folder"])
    os.makedirs(folder, exist_ok=True)

    existing_png_count = sum(
        1 for name in os.listdir(folder) if name.lower().endswith(".png")
    )
    remaining = max(0, target_per_pattern - existing_png_count)
    if remaining == 0:
        print(f"[{pattern_name}] already has {existing_png_count} images, skip generation.")
        return 0, 0

    validator = cfg["validator"]
    file_idx = next_file_index(folder)
    generated = 0
    attempts = 0
    max_attempts = max(remaining * max_attempt_factor, remaining + 200)

    while generated < remaining and attempts < max_attempts:
        attempts += 1
        df = build_synthetic_ohlc(pattern_name, rng=rng, length=window_size)

        is_valid, _ = validator(df)
        if not is_valid:
            continue

        signature = calc_signature(df)
        if signature in global_signatures:
            continue

        while True:
            filename = f"{cfg['prefix']}_ART_{file_idx:05d}.png"
            save_path = os.path.join(folder, filename)
            if not os.path.exists(save_path):
                break
            file_idx += 1

        save_and_resize_chart(df, save_path, style)
        signatures_by_pattern[pattern_name].add(signature)
        global_signatures.add(signature)
        generated += 1
        file_idx += 1

    print(
        f"[{pattern_name}] generated {generated}/{remaining}, attempts={attempts}, "
        f"total_now={existing_png_count + generated}"
    )
    return generated, attempts


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate synthetic K-line images for minority chart patterns."
    )
    parser.add_argument(
        "--output-root",
        default="artificial",
        help="Root output folder for synthetic images.",
    )
    parser.add_argument(
        "--target-per-pattern",
        type=int,
        default=DEFAULT_TARGET_PER_PATTERN,
        help="Target total image count per pattern (must be between 100 and 200).",
    )
    parser.add_argument(
        "--window-size",
        type=int,
        default=WINDOW_SIZE,
        help="OHLC window length used to synthesize each sample.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed. Omit for non-deterministic generation.",
    )
    parser.add_argument(
        "--max-attempt-factor",
        type=int,
        default=50,
        help="Max attempts multiplier for each pattern.",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    if args.target_per_pattern < 100 or args.target_per_pattern > 200:
        raise ValueError("--target-per-pattern must be in [100, 200].")
    if args.window_size < 24:
        raise ValueError("--window-size must be >= 24.")
    if args.max_attempt_factor < 5:
        raise ValueError("--max-attempt-factor must be >= 5.")

    output_root = os.path.abspath(args.output_root)
    os.makedirs(output_root, exist_ok=True)

    manifest_path = get_manifest_path(output_root)
    signatures_by_pattern = load_manifest(manifest_path)
    for key in PATTERN_CONFIG:
        signatures_by_pattern[key] = set(signatures_by_pattern.get(key, set()))
    global_signatures = set()
    for signatures in signatures_by_pattern.values():
        global_signatures.update(signatures)

    style = build_style()
    rng = np.random.default_rng(args.seed)

    print(f"Output root: {output_root}")
    print(f"Manifest: {manifest_path}")
    print(f"Target per pattern: {args.target_per_pattern}")
    print(f"Window size: {args.window_size}")
    print(f"Seed: {args.seed}")
    print("-" * 60)

    total_generated = 0
    total_attempts = 0
    for pattern_name in PATTERN_CONFIG:
        generated, attempts = generate_one_pattern(
            pattern_name=pattern_name,
            target_per_pattern=args.target_per_pattern,
            output_root=output_root,
            style=style,
            rng=rng,
            signatures_by_pattern=signatures_by_pattern,
            global_signatures=global_signatures,
            window_size=args.window_size,
            max_attempt_factor=args.max_attempt_factor,
        )
        total_generated += generated
        total_attempts += attempts

    save_manifest(manifest_path, signatures_by_pattern)
    print("-" * 60)
    print(
        f"Done. New images: {total_generated}, total attempts: {total_attempts}, "
        f"patterns: {len(PATTERN_CONFIG)}"
    )


if __name__ == "__main__":
    main()
