from pathlib import Path
import sys
import os
import tempfile
import time
from collections import Counter

import akshare as ak
import matplotlib
import mplfinance as mpf
import pandas as pd
from PIL import Image

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kline_core.labeling import (
    DEFAULT_EXTREMA_ORDER,
    DEFAULT_SMOOTH_WINDOW,
    check_ascending_triangle,
    check_descending_triangle,
    check_double_bottom,
    check_double_top,
    check_head_and_shoulders_bottom,
    check_head_and_shoulders_top,
    check_no_clear_pattern,
)

# 强制使用无界面后端，避免本地环境显示报错
matplotlib.use("Agg")

# 运行配置
FIXED_WINDOW = 30
SLIDE_STEP = 3
IMAGE_SIZE = (448, 448)
REQUEST_INTERVAL = 5
DEFAULT_START_DATE = "20210101"

# 形态参数配置（可统一调整）
EXTREMA_ORDER = DEFAULT_EXTREMA_ORDER
SMOOTH_WINDOW = DEFAULT_SMOOTH_WINDOW

# 绘图临时尺寸
TMP_FIGSIZE = (8, 8)
TMP_DPI = 100

# 数据缓存目录
DATA_ROOT_DIR = os.path.join("stock_data")
RAW_DATA_DIR = os.path.join(DATA_ROOT_DIR, "raw")
NORMALIZED_DATA_DIR = os.path.join(DATA_ROOT_DIR, "normalized")

# 图片输出目录配置
PATTERN_METADATA = {
    "double_bottom": {"folder": "double_bottom", "prefix": "DoubleBottom"},
    "double_top": {"folder": "double_top", "prefix": "DoubleTop"},
    "head_and_shoulders_top": {
        "folder": "head_and_shoulders_top",
        "prefix": "HeadShouldersTop",
    },
    "head_and_shoulders_bottom": {
        "folder": "head_and_shoulders_bottom",
        "prefix": "HeadShouldersBottom",
    },
    "ascending_triangle": {
        "folder": "ascending_triangle",
        "prefix": "AscendingTriangle",
    },
    "descending_triangle": {
        "folder": "descending_triangle",
        "prefix": "DescendingTriangle",
    },
    "no_pattern": {"folder": "no_pattern", "prefix": "NoPattern"},
}

# 识别器列表（顺序即优先参与打分竞争的候选集合）
PATTERN_DETECTORS = [
    (
        "double_bottom",
        check_double_bottom,
        {"extrema_order": EXTREMA_ORDER, "smooth_window": SMOOTH_WINDOW},
    ),
    (
        "double_top",
        check_double_top,
        {"extrema_order": EXTREMA_ORDER, "smooth_window": SMOOTH_WINDOW},
    ),
    (
        "head_and_shoulders_top",
        check_head_and_shoulders_top,
        {"extrema_order": EXTREMA_ORDER, "smooth_window": SMOOTH_WINDOW},
    ),
    (
        "head_and_shoulders_bottom",
        check_head_and_shoulders_bottom,
        {"extrema_order": EXTREMA_ORDER, "smooth_window": SMOOTH_WINDOW},
    ),
    (
        "ascending_triangle",
        check_ascending_triangle,
        {"extrema_order": EXTREMA_ORDER, "smooth_window": SMOOTH_WINDOW},
    ),
    (
        "descending_triangle",
        check_descending_triangle,
        {"extrema_order": EXTREMA_ORDER, "smooth_window": SMOOTH_WINDOW},
    ),
]


def _ensure_storage_dirs():
    os.makedirs(RAW_DATA_DIR, exist_ok=True)
    os.makedirs(NORMALIZED_DATA_DIR, exist_ok=True)


def _get_storage_paths(symbol, adjust):
    raw_path = os.path.join(RAW_DATA_DIR, f"{symbol}_{adjust}_raw.csv")
    normalized_path = os.path.join(
        NORMALIZED_DATA_DIR,
        f"{symbol}_{adjust}_normalized.csv",
    )
    return raw_path, normalized_path


def _normalize_stock_df(df):
    """
    将不同来源的字段统一为标准 OHLCV 格式。
    """
    column_map = {
        "日期": "Date",
        "开盘": "Open",
        "最高": "High",
        "最低": "Low",
        "收盘": "Close",
        "成交量": "Volume",
        "amount": "Volume",
        "date": "Date",
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "volume": "Volume",
        "Date": "Date",
        "Open": "Open",
        "High": "High",
        "Low": "Low",
        "Close": "Close",
        "Volume": "Volume",
    }

    rename_map = {col: column_map[col] for col in df.columns if col in column_map}
    df = df.rename(columns=rename_map)

    required_cols = {"Date", "Open", "High", "Low", "Close"}
    missing = required_cols - set(df.columns)
    if missing:
        return None, missing

    if "Volume" not in df.columns:
        df["Volume"] = 0

    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    for col in ["Open", "High", "Low", "Close", "Volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["Date", "Open", "High", "Low", "Close"])
    if df.empty:
        return None, {"Date", "Open", "High", "Low", "Close"}

    df = df[["Date", "Open", "High", "Low", "Close", "Volume"]]
    df = df.sort_values("Date")
    df = df.set_index("Date")
    return df, None


def _save_local_stock_data(symbol, adjust, raw_df, normalized_df):
    raw_path, normalized_path = _get_storage_paths(symbol, adjust)
    try:
        raw_df.to_csv(raw_path, index=False, encoding="utf-8-sig")
        normalized_df.reset_index().to_csv(
            normalized_path,
            index=False,
            encoding="utf-8-sig",
        )
        print(f"    [缓存] 原始数据已保存: {raw_path}")
        print(f"    [缓存] 标准化数据已保存: {normalized_path}")
    except Exception as exc:
        print(f"    [警告] {symbol} 本地缓存保存失败: {exc}")


def _load_local_normalized_data(symbol, start_date, adjust):
    _, normalized_path = _get_storage_paths(symbol, adjust)
    if not os.path.exists(normalized_path):
        return None

    try:
        local_df = pd.read_csv(normalized_path)
        normalized_df, missing = _normalize_stock_df(local_df)
        if normalized_df is None:
            print(
                f"    [警告] {symbol} 本地缓存格式无效，缺失字段: {sorted(missing)}"
            )
            return None

        normalized_df = normalized_df[normalized_df.index >= pd.to_datetime(start_date)]
        if len(normalized_df) < FIXED_WINDOW:
            print(
                f"    [警告] {symbol} 本地缓存在 {start_date} 后仅 {len(normalized_df)} 条，"
                f"不足 {FIXED_WINDOW} 条"
            )
            return None

        print(f"    [缓存] 使用本地标准化数据: {normalized_path}")
        return normalized_df
    except Exception as exc:
        print(f"    [警告] {symbol} 读取本地缓存失败: {exc}")
        return None


def _to_prefixed_symbol(symbol):
    if symbol.startswith("6") or symbol.startswith("9"):
        return f"sh{symbol}"
    return f"sz{symbol}"


def _try_fetch_with_sources(symbol, start_date, adjust):
    """
    按优先级尝试多个数据源，返回首个可用结果。
    """
    fetch_attempts = [
        (
            "东方财富日线",
            lambda: ak.stock_zh_a_hist(
                symbol=symbol,
                start_date=start_date,
                adjust=adjust,
            ),
        ),
        (
            "腾讯日线",
            lambda: ak.stock_zh_a_hist_tx(
                symbol=_to_prefixed_symbol(symbol),
                start_date=start_date,
                end_date="20500101",
                adjust=adjust,
            ),
        ),
        (
            "新浪日线",
            lambda: ak.stock_zh_a_daily(
                symbol=_to_prefixed_symbol(symbol),
                start_date=start_date,
                end_date="20500101",
                adjust=adjust,
            ),
        ),
    ]

    last_error = None
    for source_name, fetch_fn in fetch_attempts:
        try:
            raw_df = fetch_fn()
            if raw_df is not None and not raw_df.empty:
                print(f"    [数据源] {symbol} 拉取成功: {source_name}")
                return raw_df, source_name
            print(f"    [警告] {symbol} 在 {source_name} 返回空数据")
        except Exception as exc:
            last_error = exc
            print(f"    [警告] {symbol} 在 {source_name} 失败: {exc}")

    return None, last_error


def fetch_stock_data(symbol, start_date, adjust="qfq", save_local=True, use_local_fallback=True):
    """
    下载并标准化单只股票数据，失败时可回退本地缓存。
    """
    print(f"--> [请求] 正在拉取 {symbol}，起始日期 {start_date}...")
    try:
        raw_df, _source_info = _try_fetch_with_sources(symbol, start_date, adjust)

        if raw_df is None or raw_df.empty:
            print(f"    [警告] {symbol} 所有数据源均不可用")
            if use_local_fallback:
                return _load_local_normalized_data(symbol, start_date, adjust)
            return None

        df, missing = _normalize_stock_df(raw_df)
        if df is None:
            print(f"    [警告] {symbol} 字段缺失: {sorted(missing)}")
            if use_local_fallback:
                return _load_local_normalized_data(symbol, start_date, adjust)
            return None

        if len(df) < FIXED_WINDOW:
            print(f"    [警告] {symbol} 仅有 {len(df)} 条数据，不足 {FIXED_WINDOW} 条")
            if use_local_fallback:
                return _load_local_normalized_data(symbol, start_date, adjust)
            return None

        if save_local:
            _save_local_stock_data(symbol, adjust, raw_df, df)

        return df

    except Exception as exc:
        print(f"    [错误] 拉取 {symbol} 失败: {exc}")
        if use_local_fallback:
            return _load_local_normalized_data(symbol, start_date, adjust)
        return None


def identify_patterns(df):
    """
    滑窗识别多种形态，并在同一窗口只保留得分最高的一个标签。
    """
    found_patterns = []

    for i in range(FIXED_WINDOW, len(df) + 1, SLIDE_STEP):
        subset = df.iloc[i - FIXED_WINDOW:i]
        target_date = subset.index[-1].strftime("%Y%m%d")

        matches = []
        matched_flags = []

        for pattern_name, detector, detector_kwargs in PATTERN_DETECTORS:
            is_match, info = detector(subset, **detector_kwargs)
            matched_flags.append(is_match)
            if is_match and info:
                info_copy = dict(info)
                info_copy["pattern"] = pattern_name
                matches.append(info_copy)

        if matches:
            best_match = max(
                matches,
                key=lambda item: item.get("score", item.get("neck_magnitude", 0.0)),
            )
            best_match.pop("score", None)
            found_patterns.append({"data": subset, "date": target_date, "info": best_match})
            continue

        is_no_pattern, no_pattern_info = check_no_clear_pattern(
            subset,
            matched_patterns=matched_flags,
        )
        if is_no_pattern:
            no_pattern_info = dict(no_pattern_info)
            no_pattern_info.pop("score", None)
            found_patterns.append(
                {
                    "data": subset,
                    "date": target_date,
                    "info": no_pattern_info,
                }
            )

    return found_patterns


def _find_existing_image_paths(output_root_dir, symbol, date_str):
    """
    在所有形态目录中查找同一 symbol+date 的图片文件。
    """
    suffix = f"_{symbol}_{date_str}.png"
    search_dirs = [os.path.join(output_root_dir, item["folder"]) for item in PATTERN_METADATA.values()]
    search_dirs.append(os.path.join(output_root_dir, "unknown"))

    paths = []
    for folder in search_dirs:
        if not os.path.isdir(folder):
            continue
        for filename in os.listdir(folder):
            if filename.endswith(suffix):
                paths.append(os.path.join(folder, filename))
    return paths


def _ensure_unique_image_location(output_root_dir, symbol, date_str, target_path):
    """
    保证同一 symbol+date 的图片只保留在目标路径。
    返回：
    - "exists_target"：目标已存在且已清理重复
    - "moved_to_target"：从其它目录迁移到目标目录
    - "cleaned_only"：仅清理了重复但仍需重绘
    - "not_found"：未找到已有文件
    """
    existing_paths = _find_existing_image_paths(output_root_dir, symbol, date_str)
    if not existing_paths:
        return "not_found"

    target_abs = os.path.abspath(target_path)
    unique_abs = []
    seen = set()
    for path in existing_paths:
        abs_path = os.path.abspath(path)
        if abs_path not in seen:
            unique_abs.append(abs_path)
            seen.add(abs_path)
    existing_paths = unique_abs

    if target_abs in existing_paths:
        cleanup_failed = False
        for path in existing_paths:
            if path != target_abs and os.path.exists(path):
                try:
                    os.remove(path)
                except Exception as exc:
                    cleanup_failed = True
                    print(f"   [警告] 清理重复图片失败: {path} ({exc})")
        if cleanup_failed:
            return "exists_target_with_residual"
        return "exists_target"

    source_path = existing_paths[0]
    os.makedirs(os.path.dirname(target_abs), exist_ok=True)
    try:
        os.replace(source_path, target_abs)
    except Exception as exc:
        print(f"   [警告] 迁移图片失败: {source_path} -> {target_abs} ({exc})")
        return "move_failed"

    cleanup_failed = False
    for path in existing_paths[1:]:
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception as exc:
                cleanup_failed = True
                print(f"   [警告] 清理重复图片失败: {path} ({exc})")
    if cleanup_failed:
        return "moved_with_residual"
    return "moved_to_target"


def save_and_resize_chart(df_subset, save_path, style):
    """
    先渲染较大图片，再缩放到目标尺寸，提升清晰度。
    """
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


def save_pattern_images(pattern_records, symbol, output_root_dir, skip_existing=True):
    """
    按类别保存形态图，支持增量跳过已存在图片。
    """
    if not pattern_records:
        return 0

    for metadata in PATTERN_METADATA.values():
        folder_path = os.path.join(output_root_dir, metadata["folder"])
        os.makedirs(folder_path, exist_ok=True)

    my_style = mpf.make_mpf_style(
        base_mpf_style="yahoo",
        gridstyle="",
        rc={"font.size": 0, "lines.linewidth": 1.0},
    )

    count = 0
    skipped = 0
    relocated = 0
    for record in pattern_records:
        df_subset = record["data"]
        date_str = record["date"]
        pattern_type = record["info"].get("pattern", "unknown")

        metadata = PATTERN_METADATA.get(
            pattern_type,
            {"folder": "unknown", "prefix": "Unknown"},
        )
        save_dir = os.path.join(output_root_dir, metadata["folder"])
        os.makedirs(save_dir, exist_ok=True)

        filename = f"{metadata['prefix']}_{symbol}_{date_str}.png"
        save_path = os.path.join(save_dir, filename)

        unique_state = _ensure_unique_image_location(
            output_root_dir=output_root_dir,
            symbol=symbol,
            date_str=date_str,
            target_path=save_path,
        )

        if unique_state in ("moved_to_target", "moved_with_residual"):
            relocated += 1
            if skip_existing:
                skipped += 1
                continue

        if unique_state in ("exists_target", "exists_target_with_residual"):
            if skip_existing:
                skipped += 1
                continue

        if skip_existing and os.path.exists(save_path):
            skipped += 1
            continue

        try:
            save_and_resize_chart(df_subset, save_path, my_style)
            print(
                f"   [保存] {filename} -> {save_dir} "
                f"(形态强度: {record['info'].get('neck_magnitude', 0):.3f})"
            )
            count += 1
        except Exception as exc:
            print(f"   [错误] 绘图失败 {filename}: {exc}")

    if relocated > 0:
        print(f"   [迁移] {symbol} 目录纠正图片: {relocated} 张")
    if skipped > 0:
        print(f"   [跳过] {symbol} 已存在图片: {skipped} 张")

    return count


def run_pipeline(stock_list, start_date):
    """
    主流程：拉取数据 -> 识别形态 -> 保存图片。
    """
    output_dir = os.path.join("images")
    os.makedirs(output_dir, exist_ok=True)
    _ensure_storage_dirs()

    total_images = 0
    total_counter = Counter()

    print(
        f"=== 开始执行任务（窗口={FIXED_WINDOW}，步长={SLIDE_STEP}，请求间隔={REQUEST_INTERVAL}秒）==="
    )
    print(f"输出目录: {os.path.abspath(output_dir)}")
    print(f"原始数据目录: {os.path.abspath(RAW_DATA_DIR)}")
    print(f"标准化数据目录: {os.path.abspath(NORMALIZED_DATA_DIR)}")
    print(f"极值参数: order={EXTREMA_ORDER}，平滑窗口={SMOOTH_WINDOW}")
    for pattern_name, metadata in PATTERN_METADATA.items():
        folder = os.path.abspath(os.path.join(output_dir, metadata["folder"]))
        print(f"  - {pattern_name}: {folder}")
    print(f"图片尺寸: {IMAGE_SIZE[0]}x{IMAGE_SIZE[1]}")
    print(f"临时渲染尺寸: {TMP_FIGSIZE[0] * TMP_DPI}x{TMP_FIGSIZE[1] * TMP_DPI}\n")

    for symbol in stock_list:
        df = fetch_stock_data(symbol, start_date)
        if df is not None:
            patterns = identify_patterns(df)
            symbol_counter = Counter(
                item["info"].get("pattern", "unknown") for item in patterns
            )
            total_counter.update(symbol_counter)

            print(f"    -> {symbol} 识别窗口数: {len(patterns)}")
            if symbol_counter:
                print(f"    -> {symbol} 类别分布: {dict(symbol_counter)}")

            if patterns:
                saved_count = save_pattern_images(patterns, symbol, output_dir)
                total_images += saved_count
            else:
                print("    -> 未找到符合条件的窗口")

        print(f"    [等待] 休眠 {REQUEST_INTERVAL} 秒")
        time.sleep(REQUEST_INTERVAL)
        print("-" * 40)

    print(f"\n=== 全部完成，本次新增图片 {total_images} 张 ===")
    print(f"总体类别分布: {dict(total_counter)}")


if __name__ == "__main__":
    test_stocks = [
        "601318",
        "600000",
        "600030",
        "600104",
        "000333",
        "002594",
        "300059",
        "600900",
    ]

    run_pipeline(test_stocks, start_date=DEFAULT_START_DATE)
