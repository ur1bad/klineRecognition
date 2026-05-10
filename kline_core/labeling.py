import numpy as np
from itertools import combinations
from scipy.signal import argrelextrema


# 默认参数：极值点识别优先 order=3，轻微平滑窗口=3
DEFAULT_EXTREMA_ORDER = 3
DEFAULT_SMOOTH_WINDOW = 3


def _safe_pct_diff(a, b):
    base = (a + b) / 2
    if base == 0:
        return np.inf
    return abs(a - b) / base


def _select_best_candidate(candidates):
    if not candidates:
        return None
    return max(candidates, key=lambda item: item.get("score", item.get("neck_magnitude", 0.0)))


def _smooth_series(values, smooth_window=DEFAULT_SMOOTH_WINDOW):
    """对序列做轻微平滑，减少局部噪声。"""
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        return arr

    window = max(1, int(smooth_window))
    if window % 2 == 0:
        window += 1

    if window == 1 or arr.size < window:
        return arr.copy()

    pad = window // 2
    padded = np.pad(arr, (pad, pad), mode="edge")
    kernel = np.ones(window, dtype=float) / window
    return np.convolve(padded, kernel, mode="valid")


def _linear_slope(indices, values):
    if len(indices) < 2:
        return 0.0
    x = np.asarray(indices, dtype=float)
    y = np.asarray(values, dtype=float)
    return float(np.polyfit(x, y, 1)[0])


def _extract_extrema(highs, lows, extrema_order=DEFAULT_EXTREMA_ORDER, smooth_window=DEFAULT_SMOOTH_WINDOW):
    """基于平滑后的高低价提取局部高低点。"""
    n = len(highs)
    if n == 0:
        return [], [], np.array([]), np.array([])

    order = max(1, int(extrema_order))
    highs_smoothed = _smooth_series(highs, smooth_window)
    lows_smoothed = _smooth_series(lows, smooth_window)

    local_max_indices = argrelextrema(highs_smoothed, np.greater_equal, order=order)[0]
    local_min_indices = argrelextrema(lows_smoothed, np.less_equal, order=order)[0]

    left_bound = max(order, 2)
    right_bound = n - order - 1
    if right_bound < left_bound:
        return [], [], highs_smoothed, lows_smoothed

    valid_maxs = [i for i in local_max_indices if left_bound <= i <= right_bound]
    valid_mins = [i for i in local_min_indices if left_bound <= i <= right_bound]

    return valid_maxs, valid_mins, highs_smoothed, lows_smoothed


def check_double_bottom(
    df,
    threshold=0.065,
    min_interval=4,
    max_interval=24,
    min_rebound=0.020,
    breakout_ratio=0.0,
    extrema_order=DEFAULT_EXTREMA_ORDER,
    smooth_window=DEFAULT_SMOOTH_WINDOW,
):
    """双底识别。"""
    if len(df) < 20:
        return False, {}

    lows = df["Low"].values
    highs = df["High"].values
    n = len(df)

    _, valid_mins, _, _ = _extract_extrema(
        highs,
        lows,
        extrema_order=extrema_order,
        smooth_window=smooth_window,
    )
    if len(valid_mins) < 2:
        return False, {}

    global_min = float(np.min(lows))
    global_max = float(np.max(highs))
    total_range = global_max - global_min
    if total_range <= 0:
        return False, {}

    candidates = []

    for idx1, idx2 in combinations(valid_mins, 2):
        span = idx2 - idx1
        if span < min_interval or span > max_interval:
            continue

        price1 = lows[idx1]
        price2 = lows[idx2]
        avg_bottom = (price1 + price2) / 2

        diff_pct = _safe_pct_diff(price1, price2)
        if diff_pct > threshold:
            continue

        if min(price1, price2) > global_min * 1.04:
            continue

        if idx2 - idx1 < 2:
            continue
        between_highs = highs[idx1 + 1:idx2]
        if len(between_highs) == 0:
            continue

        neck_idx = idx1 + 1 + int(np.argmax(between_highs))
        neck_high = highs[neck_idx]

        rebound_ratio = (neck_high - avg_bottom) / max(avg_bottom, 1e-8)
        if rebound_ratio < min_rebound:
            continue

        if idx2 + 1 < n:
            after_high = float(np.max(highs[idx2 + 1:]))
            if after_high < neck_high * (1 + breakout_ratio):
                continue

            future_min = float(np.min(lows[idx2 + 1:]))
            if future_min < min(price1, price2) * 0.975:
                continue

        left_high = float(np.max(highs[:idx1 + 1]))
        if left_high <= avg_bottom * 1.005:
            continue

        if avg_bottom > global_min + 0.72 * total_range:
            continue

        score = rebound_ratio - 0.55 * diff_pct + 0.02 * (span / n)
        candidates.append(
            {
                "pattern": "double_bottom",
                "idx1": int(idx1),
                "idx2": int(idx2),
                "neck_idx": int(neck_idx),
                "neck_magnitude": float(rebound_ratio),
                "score": float(score),
            }
        )

    best_candidate = _select_best_candidate(candidates)
    if best_candidate is None:
        return False, {}
    return True, best_candidate


def check_double_top(
    df,
    threshold=0.065,
    min_interval=4,
    max_interval=24,
    min_pullback=0.020,
    breakdown_ratio=0.0,
    future_peak_tolerance=0.015,
    extrema_order=DEFAULT_EXTREMA_ORDER,
    smooth_window=DEFAULT_SMOOTH_WINDOW,
):
    """双顶识别。"""
    if len(df) < 20:
        return False, {}

    highs = df["High"].values
    lows = df["Low"].values
    closes = df["Close"].values
    n = len(df)

    valid_maxs, _, _, _ = _extract_extrema(
        highs,
        lows,
        extrema_order=extrema_order,
        smooth_window=smooth_window,
    )
    if len(valid_maxs) < 2:
        return False, {}

    global_max = float(np.max(highs))
    global_min = float(np.min(lows))
    total_range = global_max - global_min
    if total_range <= 0:
        return False, {}

    candidates = []

    for idx1, idx2 in combinations(valid_maxs, 2):
        span = idx2 - idx1
        if span < min_interval or span > max_interval:
            continue

        price1 = highs[idx1]
        price2 = highs[idx2]
        avg_top = (price1 + price2) / 2

        diff_pct = _safe_pct_diff(price1, price2)
        if diff_pct > threshold:
            continue

        if max(price1, price2) < global_max * 0.98:
            continue
        if min(price1, price2) < global_max * 0.90:
            continue

        if idx2 - idx1 < 2:
            continue
        between_lows = lows[idx1 + 1:idx2]
        if len(between_lows) == 0:
            continue

        neck_idx = idx1 + 1 + int(np.argmin(between_lows))
        neck_low = lows[neck_idx]

        pullback_ratio = (avg_top - neck_low) / max(avg_top, 1e-8)
        if pullback_ratio < min_pullback:
            continue

        left_low = float(np.min(lows[:idx1 + 1]))
        if left_low >= avg_top:
            continue
        if (price1 - left_low) / max(left_low, 1e-8) < 0.015:
            continue

        if idx2 + 1 < n:
            future_lows = lows[idx2 + 1:]
            future_closes = closes[idx2 + 1:]
            future_highs = highs[idx2 + 1:]

            after_min = float(np.min(future_lows))
            if after_min > neck_low * (1 - breakdown_ratio):
                continue

            if float(np.min(future_closes)) >= closes[idx2] * 0.997:
                continue

            future_peak = float(np.max(future_highs))
            if future_peak >= max(price1, price2) * (1 - future_peak_tolerance):
                continue

        if price2 > price1 * 1.04:
            continue

        if avg_top < global_min + 0.45 * total_range:
            continue

        score = pullback_ratio - 0.55 * diff_pct + 0.02 * (span / n)
        candidates.append(
            {
                "pattern": "double_top",
                "idx1": int(idx1),
                "idx2": int(idx2),
                "neck_idx": int(neck_idx),
                "neck_magnitude": float(pullback_ratio),
                "score": float(score),
            }
        )

    best_candidate = _select_best_candidate(candidates)
    if best_candidate is None:
        return False, {}
    return True, best_candidate


def check_head_and_shoulders_top(
    df,
    shoulder_tolerance=0.08,
    head_margin=0.02,
    min_pullback=0.02,
    min_gap=3,
    max_gap=14,
    breakdown_ratio=0.0,
    extrema_order=DEFAULT_EXTREMA_ORDER,
    smooth_window=DEFAULT_SMOOTH_WINDOW,
):
    """头肩顶识别（组合搜索，不限连续三点）。"""
    if len(df) < 24:
        return False, {}

    highs = df["High"].values
    lows = df["Low"].values
    n = len(df)

    valid_maxs, _, _, _ = _extract_extrema(
        highs,
        lows,
        extrema_order=extrema_order,
        smooth_window=smooth_window,
    )
    if len(valid_maxs) < 3:
        return False, {}

    global_max = float(np.max(highs))
    global_min = float(np.min(lows))
    total_range = global_max - global_min
    if total_range <= 0:
        return False, {}

    candidates = []

    for left, head, right in combinations(valid_maxs, 3):
        if not (min_gap <= head - left <= max_gap and min_gap <= right - head <= max_gap):
            continue

        left_shoulder = highs[left]
        head_top = highs[head]
        right_shoulder = highs[right]

        shoulder_diff = _safe_pct_diff(left_shoulder, right_shoulder)
        if shoulder_diff > shoulder_tolerance:
            continue

        shoulder_avg = (left_shoulder + right_shoulder) / 2
        if head_top < shoulder_avg * (1 + head_margin):
            continue
        if head_top < max(left_shoulder, right_shoulder) * (1 + head_margin * 0.7):
            continue
        if head_top < global_max * 0.96:
            continue

        if head - left < 2 or right - head < 2:
            continue

        neck1_range = lows[left + 1:head]
        neck2_range = lows[head + 1:right]
        if len(neck1_range) == 0 or len(neck2_range) == 0:
            continue

        neck1_idx = left + 1 + int(np.argmin(neck1_range))
        neck2_idx = head + 1 + int(np.argmin(neck2_range))

        neck1 = lows[neck1_idx]
        neck2 = lows[neck2_idx]
        neck_level = (neck1 + neck2) / 2

        pullback_ratio = (head_top - neck_level) / max(head_top, 1e-8)
        if pullback_ratio < min_pullback:
            continue

        if right + 1 < n:
            after_min = float(np.min(lows[right + 1:]))
            if after_min > neck_level * (1 - breakdown_ratio):
                continue

        if shoulder_avg < global_min + 0.48 * total_range:
            continue

        symmetry_penalty = abs((head - left) - (right - head)) / max(n, 1)
        prominence = (head_top - shoulder_avg) / max(head_top, 1e-8)
        score = pullback_ratio + 0.7 * prominence - 0.35 * shoulder_diff - 0.2 * symmetry_penalty

        candidates.append(
            {
                "pattern": "head_and_shoulders_top",
                "left_idx": int(left),
                "head_idx": int(head),
                "right_idx": int(right),
                "neck_idx": int((neck1_idx + neck2_idx) / 2),
                "neck_magnitude": float(pullback_ratio),
                "score": float(score),
            }
        )

    best_candidate = _select_best_candidate(candidates)
    if best_candidate is None:
        return False, {}
    return True, best_candidate


def check_head_and_shoulders_bottom(
    df,
    shoulder_tolerance=0.08,
    head_margin=0.02,
    min_rebound=0.02,
    min_gap=3,
    max_gap=14,
    breakout_ratio=0.0,
    extrema_order=DEFAULT_EXTREMA_ORDER,
    smooth_window=DEFAULT_SMOOTH_WINDOW,
):
    """头肩底识别（组合搜索，不限连续三点）。"""
    if len(df) < 24:
        return False, {}

    lows = df["Low"].values
    highs = df["High"].values
    n = len(df)

    _, valid_mins, _, _ = _extract_extrema(
        highs,
        lows,
        extrema_order=extrema_order,
        smooth_window=smooth_window,
    )
    if len(valid_mins) < 3:
        return False, {}

    global_min = float(np.min(lows))
    global_max = float(np.max(highs))
    total_range = global_max - global_min
    if total_range <= 0:
        return False, {}

    candidates = []

    for left, head, right in combinations(valid_mins, 3):
        if not (min_gap <= head - left <= max_gap and min_gap <= right - head <= max_gap):
            continue

        left_shoulder = lows[left]
        head_bottom = lows[head]
        right_shoulder = lows[right]

        shoulder_diff = _safe_pct_diff(left_shoulder, right_shoulder)
        if shoulder_diff > shoulder_tolerance:
            continue

        shoulder_avg = (left_shoulder + right_shoulder) / 2
        if head_bottom > shoulder_avg * (1 - head_margin):
            continue
        if head_bottom > min(left_shoulder, right_shoulder) * (1 - head_margin * 0.7):
            continue
        if head_bottom > global_min * 1.04:
            continue

        if head - left < 2 or right - head < 2:
            continue

        neck1_range = highs[left + 1:head]
        neck2_range = highs[head + 1:right]
        if len(neck1_range) == 0 or len(neck2_range) == 0:
            continue

        neck1_idx = left + 1 + int(np.argmax(neck1_range))
        neck2_idx = head + 1 + int(np.argmax(neck2_range))

        neck1 = highs[neck1_idx]
        neck2 = highs[neck2_idx]
        neck_level = (neck1 + neck2) / 2

        rebound_ratio = (neck_level - head_bottom) / max(neck_level, 1e-8)
        if rebound_ratio < min_rebound:
            continue

        if right + 1 < n:
            after_max = float(np.max(highs[right + 1:]))
            if after_max < neck_level * (1 + breakout_ratio):
                continue

        if shoulder_avg > global_min + 0.62 * total_range:
            continue

        symmetry_penalty = abs((head - left) - (right - head)) / max(n, 1)
        prominence = (shoulder_avg - head_bottom) / max(shoulder_avg, 1e-8)
        score = rebound_ratio + 0.7 * prominence - 0.35 * shoulder_diff - 0.2 * symmetry_penalty

        candidates.append(
            {
                "pattern": "head_and_shoulders_bottom",
                "left_idx": int(left),
                "head_idx": int(head),
                "right_idx": int(right),
                "neck_idx": int((neck1_idx + neck2_idx) / 2),
                "neck_magnitude": float(rebound_ratio),
                "score": float(score),
            }
        )

    best_candidate = _select_best_candidate(candidates)
    if best_candidate is None:
        return False, {}
    return True, best_candidate


def check_ascending_triangle(
    df,
    resistance_tolerance=0.03,
    min_interval=8,
    max_interval=26,
    min_rise_ratio=0.015,
    breakout_ratio=0.0,
    min_touch_count=2,
    extrema_order=DEFAULT_EXTREMA_ORDER,
    smooth_window=DEFAULT_SMOOTH_WINDOW,
):
    """上升三角形识别：高点近似水平、低点抬高。"""
    if len(df) < 22:
        return False, {}

    highs = df["High"].values
    lows = df["Low"].values
    n = len(df)

    valid_maxs, valid_mins, _, _ = _extract_extrema(
        highs,
        lows,
        extrema_order=extrema_order,
        smooth_window=smooth_window,
    )
    if len(valid_maxs) < 2 or len(valid_mins) < 2:
        return False, {}

    candidates = []

    for idx1, idx2 in combinations(valid_maxs, 2):
        span = idx2 - idx1
        if span < min_interval or span > max_interval:
            continue

        resistance = (highs[idx1] + highs[idx2]) / 2
        if _safe_pct_diff(highs[idx1], highs[idx2]) > resistance_tolerance:
            continue

        touches = [k for k in valid_maxs if idx1 <= k <= idx2 and _safe_pct_diff(highs[k], resistance) <= resistance_tolerance]
        if len(touches) < min_touch_count:
            continue

        lows_between = [k for k in valid_mins if idx1 <= k <= idx2]
        if len(lows_between) < 2:
            continue

        low_values = [lows[k] for k in lows_between]
        rise_ratio = (low_values[-1] - low_values[0]) / max(abs(low_values[0]), 1e-8)
        if rise_ratio < min_rise_ratio:
            continue

        if _linear_slope(lows_between, low_values) <= 0:
            continue

        if low_values[-1] >= resistance * 0.998:
            continue

        if idx2 + 1 < n:
            future_high = float(np.max(highs[idx2 + 1:]))
            if future_high < resistance * (1 + breakout_ratio):
                continue

        compression = (resistance - low_values[-1]) / max(resistance, 1e-8)
        score = rise_ratio + 0.5 * compression + 0.01 * len(touches)

        candidates.append(
            {
                "pattern": "ascending_triangle",
                "idx1": int(idx1),
                "idx2": int(idx2),
                "neck_idx": int(idx2),
                "neck_magnitude": float(rise_ratio),
                "score": float(score),
            }
        )

    best_candidate = _select_best_candidate(candidates)
    if best_candidate is None:
        return False, {}
    return True, best_candidate


def check_descending_triangle(
    df,
    support_tolerance=0.03,
    min_interval=8,
    max_interval=26,
    min_fall_ratio=0.015,
    breakdown_ratio=0.0,
    min_touch_count=2,
    extrema_order=DEFAULT_EXTREMA_ORDER,
    smooth_window=DEFAULT_SMOOTH_WINDOW,
):
    """下降三角形识别：低点近似水平、高点下降。"""
    if len(df) < 22:
        return False, {}

    highs = df["High"].values
    lows = df["Low"].values
    n = len(df)

    valid_maxs, valid_mins, _, _ = _extract_extrema(
        highs,
        lows,
        extrema_order=extrema_order,
        smooth_window=smooth_window,
    )
    if len(valid_maxs) < 2 or len(valid_mins) < 2:
        return False, {}

    candidates = []

    for idx1, idx2 in combinations(valid_mins, 2):
        span = idx2 - idx1
        if span < min_interval or span > max_interval:
            continue

        support = (lows[idx1] + lows[idx2]) / 2
        if _safe_pct_diff(lows[idx1], lows[idx2]) > support_tolerance:
            continue

        touches = [k for k in valid_mins if idx1 <= k <= idx2 and _safe_pct_diff(lows[k], support) <= support_tolerance]
        if len(touches) < min_touch_count:
            continue

        highs_between = [k for k in valid_maxs if idx1 <= k <= idx2]
        if len(highs_between) < 2:
            continue

        high_values = [highs[k] for k in highs_between]
        fall_ratio = (high_values[0] - high_values[-1]) / max(abs(high_values[0]), 1e-8)
        if fall_ratio < min_fall_ratio:
            continue

        if _linear_slope(highs_between, high_values) >= 0:
            continue

        if high_values[-1] <= support * 1.002:
            continue

        if idx2 + 1 < n:
            future_low = float(np.min(lows[idx2 + 1:]))
            if future_low > support * (1 - breakdown_ratio):
                continue

        compression = (high_values[-1] - support) / max(support, 1e-8)
        score = fall_ratio + 0.5 * compression + 0.01 * len(touches)

        candidates.append(
            {
                "pattern": "descending_triangle",
                "idx1": int(idx1),
                "idx2": int(idx2),
                "neck_idx": int(idx2),
                "neck_magnitude": float(fall_ratio),
                "score": float(score),
            }
        )

    best_candidate = _select_best_candidate(candidates)
    if best_candidate is None:
        return False, {}
    return True, best_candidate


def _any_matched(matched_patterns):
    if not matched_patterns:
        return False

    if isinstance(matched_patterns, dict):
        iterable = matched_patterns.values()
    else:
        iterable = matched_patterns

    for item in iterable:
        if isinstance(item, (tuple, list)) and len(item) > 0:
            if bool(item[0]):
                return True
        elif isinstance(item, bool):
            if item:
                return True
        elif item:
            return True
    return False


def check_no_clear_pattern(df, matched_patterns=None, min_range_ratio=0.015):
    """未命中其它形态时标注为无明显形态。"""
    if len(df) < 20:
        return False, {}

    if _any_matched(matched_patterns):
        return False, {}

    highs = df["High"].values
    lows = df["Low"].values
    closes = df["Close"].values

    avg_close = float(np.mean(closes))
    if avg_close <= 0:
        return False, {}

    range_ratio = (float(np.max(highs)) - float(np.min(lows))) / avg_close
    if range_ratio < min_range_ratio:
        return False, {}

    return True, {
        "pattern": "no_pattern",
        "neck_magnitude": 0.0,
        "score": 0.0,
        "range_ratio": float(range_ratio),
    }
