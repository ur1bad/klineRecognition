from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
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
DEFAULT_NOISE_LEVEL = 2.2
DEFAULT_DIVERSITY_LEVEL = 3.2
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


def _rand_int(rng, low, high):
    low = int(low)
    high = int(high)
    if high < low:
        return low
    return int(rng.integers(low, high + 1))


def sample_anchor_indices(rng, length, centers, jitter=2, min_gap=2):
    indices = []
    for i, center in enumerate(centers):
        base = int(round(center * (length - 1)))
        remaining = len(centers) - i - 1
        low_bound = (indices[-1] + min_gap) if indices else 1
        high_bound = length - 2 - remaining * min_gap
        low = max(low_bound, base - jitter)
        high = min(high_bound, base + jitter)
        if high < low:
            low = low_bound
            high = max(low_bound, high_bound)
        indices.append(_rand_int(rng, low, high))
    return indices


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


def time_warp_series(values, rng, diversity_level):
    arr = np.asarray(values, dtype=float)
    n = len(arr)
    if n < 8:
        return arr.copy()

    steps = np.exp(rng.normal(0.0, 0.15 * diversity_level, n))
    cursor = 0
    while cursor < n:
        seg_len = _rand_int(rng, 3, 8)
        steps[cursor:cursor + seg_len] *= rng.uniform(0.55, 1.9)
        cursor += seg_len

    warped_x = np.cumsum(steps)
    warped_x = (warped_x - warped_x[0]) / max(warped_x[-1] - warped_x[0], 1e-8)
    warped_x *= (n - 1)
    return np.interp(np.arange(n, dtype=float), warped_x, arr)


def diversify_base_curve(base_close, rng, diversity_level):
    close = np.asarray(base_close, dtype=float).copy()
    n = len(close)
    if n < 8:
        return close

    close = time_warp_series(close, rng, diversity_level=diversity_level)

    std = max(float(np.std(close)), 1e-6)
    x = np.linspace(-1.0, 1.0, n)
    linear_term = rng.normal(0.0, 0.10 * diversity_level) * x
    quad_term = rng.normal(0.0, 0.08 * diversity_level) * (x * x - 0.33)
    close = close + (linear_term + quad_term) * std * rng.uniform(0.55, 1.65)

    bulge_count = _rand_int(rng, 1, max(2, int(round(1 + diversity_level * 1.7))))
    grid = np.arange(n, dtype=float)
    for _ in range(bulge_count):
        center = rng.uniform(0.0, n - 1.0)
        width = rng.uniform(1.8, 6.8)
        amp = rng.normal(0.0, std * rng.uniform(0.10, 0.36) * diversity_level)
        close += amp * np.exp(-((grid - center) ** 2) / (2.0 * width * width))

    if rng.random() < 0.5:
        close = moving_average(close, window=_rand_int(rng, 3, 5))

    return close


def add_noise_and_derive_ohlc(base_close, rng, noise_level, diversity_level):
    n = len(base_close)
    close = np.asarray(base_close, dtype=float)

    # 多源扰动策略：
    # 1）分段波动率，2）多频率波形，3）随机游走漂移，
    # 4）局部冲击与跳空扰动。
    base_scale = (
        rng.uniform(0.24, 0.62)
        * noise_level
        * (0.85 + 0.40 * diversity_level)
    )

    regime = np.ones(n, dtype=float)
    cursor = 0
    while cursor < n:
        seg_len = _rand_int(rng, 2, 7)
        regime[cursor:cursor + seg_len] = rng.uniform(0.45, 2.4)
        cursor += seg_len

    close = close + rng.normal(0.0, base_scale * regime, n)

    x = np.linspace(0.0, 1.0, n)
    phase1 = rng.uniform(0.0, 2.0 * np.pi)
    phase2 = rng.uniform(0.0, 2.0 * np.pi)
    wave1_freq = rng.uniform(1.2, 7.0)
    wave2_freq = rng.uniform(2.5, 11.0)
    wave1_amp = base_scale * rng.uniform(0.12, 0.50)
    wave2_amp = base_scale * rng.uniform(0.08, 0.34)
    close = close + wave1_amp * np.sin(wave1_freq * np.pi * x + phase1)
    close = close + wave2_amp * np.sin(wave2_freq * np.pi * x + phase2)

    close = close + np.cumsum(rng.normal(0.0, base_scale * rng.uniform(0.018, 0.055), n))

    shock_count = _rand_int(
        rng,
        1,
        max(2, int(round(2 + diversity_level * 2.2))),
    )
    for _ in range(shock_count):
        shock_idx = _rand_int(rng, 1, n - 3)
        shock_amp = rng.normal(0.0, base_scale * rng.uniform(2.0, 4.8))
        decay = np.exp(-np.arange(0, n - shock_idx) / rng.uniform(1.2, 5.0))
        close[shock_idx:] += shock_amp * decay

    if rng.random() < 0.35:
        close = moving_average(close, window=_rand_int(rng, 3, 5))

    close = np.maximum(close, 1.0)

    opens = np.empty(n, dtype=float)
    open_sigma0 = 0.0032 * (0.80 + 0.6 * noise_level + 0.25 * diversity_level)
    open_sigma = 0.0055 * (0.80 + 0.6 * noise_level + 0.25 * diversity_level)
    jump_prob = min(0.08 + 0.05 * diversity_level, 0.30)
    opens[0] = close[0] * (1 + rng.normal(0.0, open_sigma0))
    for i in range(1, n):
        gap = rng.normal(0.0, open_sigma)
        if rng.random() < jump_prob:
            gap += rng.normal(0.0, open_sigma * rng.uniform(1.8, 3.8))
        opens[i] = close[i - 1] * (1 + gap)

    close = close * (
        1.0 + rng.normal(0.0, 0.0016 * (0.8 + 0.4 * diversity_level), size=n)
    )

    wick_loc = 0.0054 * (0.90 + 0.5 * noise_level + 0.25 * diversity_level)
    wick_scale = 0.0026 * (0.90 + 0.7 * noise_level + 0.25 * diversity_level)
    upper_wick = np.abs(rng.normal(wick_loc, wick_scale, n))
    lower_wick = np.abs(rng.normal(wick_loc, wick_scale, n))

    long_wick_mask = rng.random(n) < min(0.10 + 0.05 * diversity_level, 0.35)
    if np.any(long_wick_mask):
        upper_wick[long_wick_mask] *= rng.uniform(
            1.6,
            3.5,
            size=np.sum(long_wick_mask),
        )
        lower_wick[long_wick_mask] *= rng.uniform(
            1.6,
            3.5,
            size=np.sum(long_wick_mask),
        )

    highs = np.maximum(opens, close) * (1 + upper_wick)
    lows = np.minimum(opens, close) * (1 - lower_wick)

    spike_prob = min(0.04 + 0.03 * diversity_level, 0.22)
    spike_mask = rng.random(n) < spike_prob
    if np.any(spike_mask):
        highs[spike_mask] *= 1 + np.abs(
            rng.normal(
                0.02,
                0.016,
                size=np.sum(spike_mask),
            )
        )
        lows[spike_mask] *= 1 - np.abs(
            rng.normal(
                0.02,
                0.016,
                size=np.sum(spike_mask),
            )
        )

    lows = np.maximum(lows, 0.01)

    base_volume = int(rng.integers(700_000, 9_500_000))
    volume_shape = np.abs(rng.normal(1.0, 0.48 + 0.12 * diversity_level, size=n))
    volumes = (base_volume * volume_shape).astype(int)
    volumes = np.clip(volumes, 80_000, 16_000_000)
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
    template_choices = [
        [0.16, 0.30, 0.47, 0.66, 0.80, 0.90],
        [0.12, 0.26, 0.42, 0.60, 0.74, 0.88],
        [0.20, 0.34, 0.53, 0.72, 0.83, 0.92],
    ]
    centers = template_choices[_rand_int(rng, 0, len(template_choices) - 1)]
    idx_drop, idx_b1, idx_neck, idx_b2, idx_rebound, idx_break = sample_anchor_indices(
        rng,
        length,
        centers,
        jitter=2,
        min_gap=2,
    )

    b1 = rng.uniform(84.0, 90.0)
    b2 = b1 * (1 + rng.uniform(-0.025, 0.025))
    neck = rng.uniform(97.0, 103.0)
    start = neck + rng.uniform(3.0, 12.0)
    pre_bottom = start - rng.uniform(2.0, 9.0)
    post_break = neck * (1 + rng.uniform(0.01, 0.055))
    ending = post_break + rng.uniform(0.5, 7.0)

    return [
        (0, start),
        (idx_drop, pre_bottom),
        (idx_b1, b1),
        (idx_neck, neck),
        (idx_b2, b2),
        (idx_rebound, neck + rng.uniform(0.2, 3.3)),
        (idx_break, post_break),
        (length - 1, ending),
    ]


def skeleton_double_top(rng, length):
    template_choices = [
        [0.16, 0.30, 0.47, 0.66, 0.80, 0.90],
        [0.12, 0.24, 0.40, 0.57, 0.74, 0.87],
        [0.20, 0.34, 0.52, 0.71, 0.84, 0.93],
    ]
    centers = template_choices[_rand_int(rng, 0, len(template_choices) - 1)]
    idx_rise, idx_t1, idx_neck, idx_t2, idx_pullback, idx_break = sample_anchor_indices(
        rng,
        length,
        centers,
        jitter=2,
        min_gap=2,
    )

    t1 = rng.uniform(108.0, 116.0)
    t2 = t1 * (1 + rng.uniform(-0.025, 0.02))
    neck = rng.uniform(93.0, 99.5)
    start = neck - rng.uniform(4.0, 12.0)
    pre_top = start + rng.uniform(2.0, 9.0)
    ending = neck - rng.uniform(4.0, 14.0)

    return [
        (0, start),
        (idx_rise, pre_top),
        (idx_t1, t1),
        (idx_neck, neck),
        (idx_t2, t2),
        (idx_pullback, neck - rng.uniform(0.4, 4.5)),
        (idx_break, neck - rng.uniform(2.0, 8.5)),
        (length - 1, ending),
    ]


def skeleton_head_shoulders_top(rng, length):
    template_choices = [
        [0.20, 0.34, 0.50, 0.64, 0.78, 0.90],
        [0.17, 0.30, 0.47, 0.62, 0.76, 0.88],
        [0.22, 0.36, 0.53, 0.68, 0.82, 0.92],
    ]
    centers = template_choices[_rand_int(rng, 0, len(template_choices) - 1)]
    idx_ls, idx_neck1, idx_head, idx_neck2, idx_rs, idx_break = sample_anchor_indices(
        rng,
        length,
        centers,
        jitter=2,
        min_gap=2,
    )

    left_shoulder = rng.uniform(108.0, 113.0)
    right_shoulder = left_shoulder * (1 + rng.uniform(-0.045, 0.045))
    head = max(left_shoulder, right_shoulder) * (1 + rng.uniform(0.04, 0.09))
    neck1 = rng.uniform(95.0, 101.0)
    neck2 = neck1 * (1 + rng.uniform(-0.02, 0.02))
    ending = min(neck1, neck2) - rng.uniform(3.0, 12.0)

    return [
        (0, neck1 - rng.uniform(6.0, 10.0)),
        (_rand_int(rng, 1, max(1, idx_ls - 2)), neck1 + rng.uniform(0.2, 5.5)),
        (idx_ls, left_shoulder),
        (idx_neck1, neck1),
        (idx_head, head),
        (idx_neck2, neck2),
        (idx_rs, right_shoulder),
        (idx_break, min(neck1, neck2) - rng.uniform(0.8, 6.0)),
        (length - 1, ending),
    ]


def skeleton_head_shoulders_bottom(rng, length):
    template_choices = [
        [0.20, 0.34, 0.50, 0.64, 0.78, 0.90],
        [0.17, 0.30, 0.47, 0.62, 0.76, 0.88],
        [0.22, 0.36, 0.53, 0.68, 0.82, 0.92],
    ]
    centers = template_choices[_rand_int(rng, 0, len(template_choices) - 1)]
    idx_ls, idx_neck1, idx_head, idx_neck2, idx_rs, idx_break = sample_anchor_indices(
        rng,
        length,
        centers,
        jitter=2,
        min_gap=2,
    )

    left_shoulder = rng.uniform(87.0, 92.0)
    right_shoulder = left_shoulder * (1 + rng.uniform(-0.045, 0.045))
    head = min(left_shoulder, right_shoulder) * (1 - rng.uniform(0.04, 0.09))
    neck1 = rng.uniform(100.0, 106.0)
    neck2 = neck1 * (1 + rng.uniform(-0.02, 0.02))
    ending = max(neck1, neck2) + rng.uniform(3.0, 12.0)

    return [
        (0, neck1 + rng.uniform(5.0, 9.0)),
        (_rand_int(rng, 1, max(1, idx_ls - 2)), neck1 - rng.uniform(0.2, 5.0)),
        (idx_ls, left_shoulder),
        (idx_neck1, neck1),
        (idx_head, head),
        (idx_neck2, neck2),
        (idx_rs, right_shoulder),
        (idx_break, max(neck1, neck2) + rng.uniform(0.8, 6.0)),
        (length - 1, ending),
    ]


def skeleton_ascending_triangle(rng, length):
    template_choices = [
        [0.20, 0.32, 0.44, 0.58, 0.70, 0.82, 0.92],
        [0.16, 0.28, 0.41, 0.55, 0.68, 0.80, 0.90],
        [0.22, 0.35, 0.48, 0.62, 0.74, 0.85, 0.93],
    ]
    centers = template_choices[_rand_int(rng, 0, len(template_choices) - 1)]
    (
        idx_l1,
        idx_h1,
        idx_l2,
        idx_h2,
        idx_l3,
        idx_h3,
        idx_break,
    ) = sample_anchor_indices(
        rng,
        length,
        centers,
        jitter=2,
        min_gap=2,
    )

    resistance = rng.uniform(106.0, 114.0)
    high1 = resistance * (1 + rng.uniform(-0.012, 0.012))
    high2 = resistance * (1 + rng.uniform(-0.012, 0.012))
    high3 = resistance * (1 + rng.uniform(-0.010, 0.010))

    low1 = resistance - rng.uniform(15.0, 21.0)
    low2 = low1 + rng.uniform(2.8, 6.4)
    low3 = low2 + rng.uniform(2.5, 5.6)
    low3 = min(low3, resistance - rng.uniform(2.8, 5.0))

    start = low1 + rng.uniform(1.5, 4.5)
    breakout = resistance + rng.uniform(2.2, 7.5)
    ending = breakout + rng.uniform(0.4, 4.8)

    return [
        (0, start),
        (idx_l1, low1),
        (idx_h1, high1),
        (idx_l2, low2),
        (idx_h2, high2),
        (idx_l3, low3),
        (idx_h3, high3),
        (idx_break, breakout),
        (length - 1, ending),
    ]


def skeleton_descending_triangle(rng, length):
    template_choices = [
        [0.20, 0.32, 0.44, 0.58, 0.70, 0.82, 0.92],
        [0.16, 0.28, 0.41, 0.55, 0.68, 0.80, 0.90],
        [0.22, 0.35, 0.48, 0.62, 0.74, 0.85, 0.93],
    ]
    centers = template_choices[_rand_int(rng, 0, len(template_choices) - 1)]
    (
        idx_h1,
        idx_l1,
        idx_h2,
        idx_l2,
        idx_h3,
        idx_l3,
        idx_break,
    ) = sample_anchor_indices(
        rng,
        length,
        centers,
        jitter=2,
        min_gap=2,
    )

    support = rng.uniform(86.0, 94.0)
    low1 = support * (1 + rng.uniform(-0.012, 0.012))
    low2 = support * (1 + rng.uniform(-0.012, 0.012))
    low3 = support * (1 + rng.uniform(-0.010, 0.010))

    high1 = support + rng.uniform(16.0, 22.0)
    high2 = high1 - rng.uniform(2.6, 6.3)
    high3 = high2 - rng.uniform(2.3, 5.8)
    high3 = max(high3, support + rng.uniform(2.8, 5.0))

    start = high1 - rng.uniform(1.0, 4.2)
    breakdown = support - rng.uniform(2.0, 6.8)
    ending = breakdown - rng.uniform(0.4, 4.8)

    return [
        (0, start),
        (idx_h1, high1),
        (idx_l1, low1),
        (idx_h2, high2),
        (idx_l2, low2),
        (idx_h3, high3),
        (idx_l3, low3),
        (idx_break, breakdown),
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


def build_synthetic_ohlc(pattern_name, rng, length, noise_level, diversity_level):
    points = SKELETON_BUILDERS[pattern_name](rng, length)
    base_close = linear_interpolate_skeleton(points, length=length)
    diversified = diversify_base_curve(
        base_close,
        rng=rng,
        diversity_level=diversity_level,
    )
    return add_noise_and_derive_ohlc(
        diversified,
        rng,
        noise_level=noise_level,
        diversity_level=diversity_level,
    )


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


def reset_output_folder(output_root):
    removed_dirs = 0
    failed_targets = []
    for cfg in PATTERN_CONFIG.values():
        folder = os.path.join(output_root, cfg["folder"])
        if os.path.isdir(folder):
            try:
                shutil.rmtree(folder)
                removed_dirs += 1
            except Exception as exc:
                failed_targets.append(f"{folder} ({exc})")

    manifest_path = get_manifest_path(output_root)
    if os.path.exists(manifest_path):
        try:
            os.remove(manifest_path)
        except Exception as exc:
            failed_targets.append(f"{manifest_path} ({exc})")

    print(
        f"[reset] removed {removed_dirs} pattern folders and manifest from {output_root}"
    )
    if failed_targets:
        print("[reset] failed to remove:")
        for item in failed_targets:
            print(f"  - {item}")


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


def _tag_filename_regex(prefix, name_tag):
    return re.compile(rf"^{re.escape(prefix)}_{re.escape(name_tag)}_(\d+)\.png$", re.IGNORECASE)


def count_tagged_images(folder_path, prefix, name_tag):
    pattern = _tag_filename_regex(prefix, name_tag)
    count = 0
    for name in os.listdir(folder_path):
        if pattern.match(name):
            count += 1
    return count


def next_tagged_file_index(folder_path, prefix, name_tag):
    pattern = _tag_filename_regex(prefix, name_tag)
    max_idx = 0
    for name in os.listdir(folder_path):
        match = pattern.match(name)
        if not match:
            continue
        max_idx = max(max_idx, int(match.group(1)))
    return max_idx + 1


def generate_one_pattern(
    pattern_name,
    target_per_pattern,
    output_root,
    name_tag,
    style,
    rng,
    signatures_by_pattern,
    global_signatures,
    window_size,
    noise_level,
    diversity_level,
    max_attempt_factor,
):
    cfg = PATTERN_CONFIG[pattern_name]
    folder = os.path.join(output_root, cfg["folder"])
    os.makedirs(folder, exist_ok=True)

    existing_png_count = count_tagged_images(folder, cfg["prefix"], name_tag)
    remaining = max(0, target_per_pattern - existing_png_count)
    if remaining == 0:
        print(
            f"[{pattern_name}] already has {existing_png_count} images for tag '{name_tag}', skip generation."
        )
        return 0, 0

    validator = cfg["validator"]
    file_idx = next_tagged_file_index(folder, cfg["prefix"], name_tag)
    generated = 0
    attempts = 0
    max_attempts = max(remaining * max_attempt_factor, remaining + 200)

    while generated < remaining and attempts < max_attempts:
        attempts += 1
        df = build_synthetic_ohlc(
            pattern_name,
            rng=rng,
            length=window_size,
            noise_level=noise_level,
            diversity_level=diversity_level,
        )

        is_valid, _ = validator(df)
        if not is_valid:
            continue

        signature = calc_signature(df)
        if signature in global_signatures:
            continue

        while True:
            filename = f"{cfg['prefix']}_{name_tag}_{file_idx:05d}.png"
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
        default="artificial_v2",
        help="Root output folder for synthetic images.",
    )
    parser.add_argument(
        "--name-tag",
        type=str,
        default="ART",
        help="Filename tag used in generated image names, e.g. V3.",
    )
    parser.add_argument(
        "--target-per-pattern",
        type=int,
        default=DEFAULT_TARGET_PER_PATTERN,
        help="Target total image count per selected pattern.",
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
    parser.add_argument(
        "--noise-level",
        type=float,
        default=DEFAULT_NOISE_LEVEL,
        help="Noise intensity factor. Larger value gives more diverse and noisier candles.",
    )
    parser.add_argument(
        "--diversity-level",
        type=float,
        default=DEFAULT_DIVERSITY_LEVEL,
        help="Structure diversity factor. Larger value increases shape variability.",
    )
    parser.add_argument(
        "--reset-output",
        action="store_true",
        help="Delete existing synthetic folders and manifest before generation.",
    )
    parser.add_argument(
        "--patterns",
        type=str,
        default=None,
        help="Comma-separated pattern names to generate. Default: all patterns.",
    )
    return parser.parse_args()


def parse_selected_patterns(raw_patterns):
    if raw_patterns is None or not str(raw_patterns).strip():
        return list(PATTERN_CONFIG.keys())

    selected = []
    seen = set()
    for item in str(raw_patterns).split(","):
        key = item.strip()
        if not key:
            continue
        if key not in PATTERN_CONFIG:
            raise ValueError(
                f"Unknown pattern '{key}'. Available: {', '.join(PATTERN_CONFIG.keys())}"
            )
        if key not in seen:
            selected.append(key)
            seen.add(key)

    if not selected:
        raise ValueError("--patterns is empty after parsing.")
    return selected


def main():
    args = parse_args()
    selected_patterns = parse_selected_patterns(args.patterns)
    name_tag = args.name_tag.strip()

    if args.target_per_pattern < 1:
        raise ValueError("--target-per-pattern must be >= 1.")
    if not name_tag:
        raise ValueError("--name-tag cannot be empty.")
    if any(ch in name_tag for ch in r'\/:*?"<>|'):
        raise ValueError("--name-tag contains invalid filename characters.")
    if args.window_size < 24:
        raise ValueError("--window-size must be >= 24.")
    if args.max_attempt_factor < 5:
        raise ValueError("--max-attempt-factor must be >= 5.")
    if args.noise_level < 0.6 or args.noise_level > 3.0:
        raise ValueError("--noise-level must be in [0.6, 3.0].")
    if args.diversity_level < 1.0 or args.diversity_level > 4.0:
        raise ValueError("--diversity-level must be in [1.0, 4.0].")

    output_root = os.path.abspath(args.output_root)
    os.makedirs(output_root, exist_ok=True)
    if args.reset_output:
        reset_output_folder(output_root)

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
    print(f"Name tag: {name_tag}")
    print(f"Noise level: {args.noise_level}")
    print(f"Diversity level: {args.diversity_level}")
    print(f"Selected patterns: {selected_patterns}")
    print("-" * 60)

    total_generated = 0
    total_attempts = 0
    for pattern_name in selected_patterns:
        generated, attempts = generate_one_pattern(
            pattern_name=pattern_name,
            target_per_pattern=args.target_per_pattern,
            output_root=output_root,
            name_tag=name_tag,
            style=style,
            rng=rng,
            signatures_by_pattern=signatures_by_pattern,
            global_signatures=global_signatures,
            window_size=args.window_size,
            noise_level=args.noise_level,
            diversity_level=args.diversity_level,
            max_attempt_factor=args.max_attempt_factor,
        )
        total_generated += generated
        total_attempts += attempts

    save_manifest(manifest_path, signatures_by_pattern)
    print("-" * 60)
    print(
        f"Done. New images: {total_generated}, total attempts: {total_attempts}, "
        f"patterns: {len(selected_patterns)}"
    )


if __name__ == "__main__":
    main()
