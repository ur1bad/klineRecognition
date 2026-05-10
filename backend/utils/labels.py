from __future__ import annotations

import re
from typing import Optional, Union


PATTERN_KEY_TO_LABEL = {
    "head_and_shoulders_top": "头肩顶",
    "head_and_shoulders_bottom": "头肩底",
    "double_top": "双顶",
    "double_bottom": "双底",
    "ascending_triangle": "上升三角形",
    "descending_triangle": "下降三角形",
    "no_pattern": "无明显形态",
}

PATTERN_LABEL_TO_KEY = {label: key for key, label in PATTERN_KEY_TO_LABEL.items()}
PATTERN_LABELS = list(PATTERN_LABEL_TO_KEY.keys())

BULLISH_KEYS = {"head_and_shoulders_bottom", "double_bottom", "ascending_triangle"}
BEARISH_KEYS = {"head_and_shoulders_top", "double_top", "descending_triangle"}

DEFAULT_REASONS = {
    "头肩顶": "图中高点依次形成左肩、头部和右肩，颈线附近出现转弱迹象。",
    "头肩底": "图中低点依次形成左肩、头部和右肩，颈线附近出现企稳上破迹象。",
    "双顶": "图中出现两个相近高点，中间回撤较明显，属于典型顶部结构。",
    "双底": "图中出现两个相近低点，中间存在明显反弹，属于典型底部结构。",
    "上升三角形": "图中高点趋于水平、低点逐步抬高，符合上升三角形整理特征。",
    "下降三角形": "图中低点趋于水平、高点逐步下移，符合下降三角形整理特征。",
    "无明显形态": "当前 K 线窗口内未识别出明确的目标形态特征。",
}

LABEL_ALIASES = {
    "头肩顶": ["头肩顶", "头肩顶部", "head_and_shoulders_top", "headshoulderstop"],
    "头肩底": ["头肩底", "头肩底部", "head_and_shoulders_bottom", "headshouldersbottom"],
    "双顶": ["双顶", "double_top", "doubletop"],
    "双底": ["双底", "double_bottom", "doublebottom"],
    "上升三角形": ["上升三角形", "ascending_triangle", "ascendingtriangle"],
    "下降三角形": ["下降三角形", "descending_triangle", "descendingtriangle"],
    "无明显形态": ["无明显形态", "无形态", "未识别", "no_pattern", "nopattern", "none"],
}

MODEL_PROMPT = (
    "<image>请判断这张K线图属于哪一种形态。"
    "可选类别：上升三角形、下降三角形、双底、双顶、头肩底、头肩顶、无明显形态。"
    "只输出类别名称。"
)


def key_to_label(key: Optional[str]) -> str:
    if not key:
        return "无明显形态"
    return PATTERN_KEY_TO_LABEL.get(key, "无明显形态")


def label_to_key(label: Optional[str]) -> str:
    if not label:
        return "no_pattern"
    normalized = normalize_label(label)
    return PATTERN_LABEL_TO_KEY.get(normalized, "no_pattern")


def normalize_label(value: Optional[str]) -> str:
    if not value:
        return "无明显形态"

    compact = re.sub(r"[\s`\"'，。；;:{}\[\]()]+", "", str(value)).lower()
    for label, aliases in LABEL_ALIASES.items():
        for alias in aliases:
            if alias.lower() in compact:
                return label
    return "无明显形态"


def clamp_confidence(value: Optional[Union[float, int]], label: Optional[str] = None) -> float:
    if value is None:
        return default_confidence(label or "无明显形态")
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default_confidence(label or "无明显形态")
    if numeric > 1:
        numeric = numeric / 100.0
    numeric = max(0.0, min(1.0, numeric))
    if numeric == 0.0:
        return default_confidence(label or "无明显形态")
    return round(numeric, 4)


def default_confidence(label: str) -> float:
    return 0.56 if label == "无明显形态" else 0.78


def reason_for_label(label: str, custom_reason: Optional[str] = None) -> str:
    if custom_reason and custom_reason.strip():
        return custom_reason.strip()
    return DEFAULT_REASONS.get(label, DEFAULT_REASONS["无明显形态"])


def signal_direction(label: str) -> str:
    key = label_to_key(label)
    if key in BULLISH_KEYS:
        return "bullish"
    if key in BEARISH_KEYS:
        return "bearish"
    return "neutral"
