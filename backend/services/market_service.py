from __future__ import annotations

import contextlib
import io
import math
import time
from datetime import datetime
from typing import Any, Optional

import akshare as ak
import pandas as pd


CACHE_TTL_SECONDS = 15 * 60
SOURCE_NAME = "AkShare 东方财富实时行情"
INDEX_CODES = ["000001", "399001", "399006", "000688"]


class MarketService:
    """Provide lightweight A-share market overview data for the frontend."""

    def __init__(self) -> None:
        self._cache_payload: Optional[dict[str, Any]] = None
        self._cache_created_at = 0.0

    def get_overview(self, *, force_refresh: bool = False) -> dict[str, Any]:
        if not force_refresh and self._cache_payload and self._is_cache_fresh():
            return self._cache_payload

        source = SOURCE_NAME
        source_notes: list[str] = []
        try:
            stock_df, stock_source = self._try_fetch_stock_spot_with_sources()
            stocks = self._build_stock_rows(stock_df)
            source_notes.append(stock_source)
        except Exception as exc:
            stocks = self._build_fallback_stock_rows()
            source_notes.append(f"个股示例数据（实时源不可用：{type(exc).__name__}）")

        try:
            index_df, index_source = self._try_fetch_index_spot_with_sources()
            indices = self._build_index_rows(index_df)
            if not indices:
                raise ValueError("指数行情缺少目标指数。")
            source_notes.append(index_source)
        except Exception as exc:
            indices = self._build_fallback_index_rows()
            source_notes.append(f"指数示例数据（实时源不可用：{type(exc).__name__}）")

        if source_notes:
            source = "；".join(source_notes)

        top_turnover, top_turnover_title, top_turnover_metric = self._build_turnover_rank(stocks)

        payload = {
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "source": source,
            "indices": indices,
            "breadth": self._build_breadth(stocks),
            "sentiment": self._build_sentiment(stocks, indices),
            "stocks": stocks,
            "top_gainers": self._top_rows(stocks, "change_percent", reverse=True),
            "top_losers": self._top_rows(stocks, "change_percent", reverse=False),
            "top_amount": self._top_rows(stocks, "amount", reverse=True),
            "top_turnover": top_turnover,
            "top_turnover_title": top_turnover_title,
            "top_turnover_metric": top_turnover_metric,
        }
        self._cache_payload = payload
        self._cache_created_at = time.time()
        return payload

    def _is_cache_fresh(self) -> bool:
        return (time.time() - self._cache_created_at) <= CACHE_TTL_SECONDS

    def _try_fetch_stock_spot_with_sources(self) -> tuple[pd.DataFrame, str]:
        fetch_attempts = [
            ("东方财富A股实时行情", ak.stock_zh_a_spot_em),
            ("新浪A股实时行情", ak.stock_zh_a_spot),
        ]

        last_error: Optional[Exception] = None
        for source_name, fetch_fn in fetch_attempts:
            try:
                dataframe = self._call_data_source(fetch_fn)
                if dataframe is not None and not dataframe.empty:
                    return dataframe, source_name
            except Exception as exc:
                last_error = exc

        if last_error is not None:
            raise last_error
        raise ValueError("所有个股实时行情数据源均返回空数据。")

    def _try_fetch_index_spot_with_sources(self) -> tuple[pd.DataFrame, str]:
        fetch_attempts = [
            ("东方财富指数实时行情", lambda: ak.stock_zh_index_spot_em(symbol="沪深重要指数")),
            ("新浪指数实时行情", ak.stock_zh_index_spot_sina),
        ]

        last_error: Optional[Exception] = None
        for source_name, fetch_fn in fetch_attempts:
            try:
                dataframe = self._call_data_source(fetch_fn)
                if dataframe is not None and not dataframe.empty:
                    return dataframe, source_name
            except Exception as exc:
                last_error = exc

        if last_error is not None:
            raise last_error
        raise ValueError("所有指数实时行情数据源均返回空数据。")

    def _call_data_source(self, fetch_fn: Any) -> pd.DataFrame:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return fetch_fn()

    def _build_index_rows(self, index_df: pd.DataFrame) -> list[dict[str, Any]]:
        if index_df is None or index_df.empty:
            return []
        if "代码" not in index_df.columns:
            return []

        rows: list[dict[str, Any]] = []
        for code in INDEX_CODES:
            normalized_codes = index_df["代码"].apply(self._normalize_stock_code)
            matched = index_df[normalized_codes == code]
            if matched.empty:
                continue
            item = matched.iloc[0]
            rows.append(
                {
                    "code": self._normalize_stock_code(item.get("代码", "")),
                    "name": str(item.get("名称", "")).strip(),
                    "latest_price": self._safe_float(item.get("最新价")),
                    "change_amount": self._safe_float(item.get("涨跌额")),
                    "change_percent": self._safe_float(item.get("涨跌幅")),
                    "amount": self._safe_float(item.get("成交额")),
                }
            )
        return rows

    def _build_stock_rows(self, dataframe: pd.DataFrame) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for _, item in dataframe.iterrows():
            code = self._normalize_stock_code(item.get("代码", ""))
            name = str(item.get("名称", "")).strip()
            if not code or not name:
                continue

            board = self._resolve_board(code)
            rows.append(
                {
                    "code": code,
                    "name": name,
                    "latest_price": self._safe_float(item.get("最新价")),
                    "change_percent": self._safe_float(item.get("涨跌幅")),
                    "change_amount": self._safe_float(item.get("涨跌额")),
                    "turnover_rate": self._safe_float(item.get("换手率")),
                    "amplitude": self._safe_float(item.get("振幅")),
                    "volume": self._safe_float(item.get("成交量")),
                    "amount": self._safe_float(item.get("成交额")),
                    "pe_dynamic": self._safe_float(item.get("市盈率-动态")),
                    "market": self._resolve_market(code),
                    "board": board,
                }
            )
        return rows

    def _normalize_stock_code(self, value: Any) -> str:
        text = str(value or "").strip()
        if text.startswith(("sh", "sz", "bj")):
            return text[2:]
        return text

    def _build_breadth(self, stocks: list[dict[str, Any]]) -> dict[str, Any]:
        valid_stocks = [item for item in stocks if item.get("change_percent") is not None]
        changes = [item.get("change_percent") for item in valid_stocks]
        up = sum(1 for value in changes if float(value) > 0)
        down = sum(1 for value in changes if float(value) < 0)
        flat = sum(1 for value in changes if float(value) == 0)
        limit_up = sum(1 for item in valid_stocks if self._is_limit_up(item))
        limit_down = sum(1 for item in valid_stocks if self._is_limit_down(item))
        non_limit_changes = [
            item.get("change_percent")
            for item in valid_stocks
            if not self._is_limit_up(item) and not self._is_limit_down(item)
        ]

        bucket_specs = [
            ("跌停", None, -9.8, "down"),
            ("<-8%", -9.8, -8.0, "down"),
            ("-8~-6%", -8.0, -6.0, "down"),
            ("-6~-4%", -6.0, -4.0, "down"),
            ("-4~-2%", -4.0, -2.0, "down"),
            ("-2~0%", -2.0, 0.0, "down"),
            ("0~2%", 0.0, 2.0, "up"),
            ("2~4%", 2.0, 4.0, "up"),
            ("4~6%", 4.0, 6.0, "up"),
            ("6~8%", 6.0, 8.0, "up"),
            (">8%", 8.0, 9.8, "up"),
            ("涨停", 9.8, None, "up"),
        ]
        buckets = [
            {
                "label": label,
                "count": limit_down
                if label == "跌停"
                else limit_up
                if label == "涨停"
                else self._count_bucket(non_limit_changes, lower, upper),
                "tone": tone,
            }
            for label, lower, upper, tone in bucket_specs
        ]

        return {
            "total": len(changes),
            "up": up,
            "down": down,
            "flat": flat,
            "limit_up": limit_up,
            "limit_down": limit_down,
            "buckets": buckets,
        }

    def _build_sentiment(self, stocks: list[dict[str, Any]], indices: Optional[list[dict[str, Any]]] = None) -> dict[str, Any]:
        valid_stocks = [item for item in stocks if item.get("change_percent") is not None]
        changes = [float(item["change_percent"]) for item in valid_stocks]
        total = len(changes)
        if total == 0:
            return {
                "score": 5.0,
                "level": "数据不足",
                "advice": "当前行情数据不足，建议稍后刷新。",
                "advance_ratio": 0.0,
                "strong_ratio": 0.0,
                "weak_ratio": 0.0,
                "mean_change": 0.0,
                "index_change": None,
                "components": {},
            }

        up = sum(1 for value in changes if value > 0)
        strong = sum(1 for value in changes if value >= 2.0)
        weak = sum(1 for value in changes if value <= -2.0)
        limit_up = sum(1 for item in valid_stocks if self._is_limit_up(item))
        limit_down = sum(1 for item in valid_stocks if self._is_limit_down(item))
        advance_ratio = up / total
        strong_ratio = strong / total
        weak_ratio = weak / total
        mean_change = sum(changes) / total
        index_change = self._calculate_index_change(indices or [])

        components = {
            "breadth": (advance_ratio - 0.5) * 3.6,
            "strength": (strong_ratio - weak_ratio) * 3.0,
            "limit": ((limit_up - limit_down) / total) * 14.0,
            "average_change": self._clamp(mean_change, -2.0, 2.0) * 0.45,
            "index_trend": self._clamp(index_change, -2.5, 2.5) * 0.30 if index_change is not None else 0.0,
        }
        score = 5.0 + sum(components.values())
        score = round(max(0.0, min(10.0, score)), 1)

        if score >= 7.5:
            level = "强势"
            advice = "市场赚钱效应较强，可关注高景气板块与形态共振机会。"
        elif score >= 6.0:
            level = "偏强"
            advice = "市场情绪偏强，可积极参与并优先关注强势板块，但仍需控制追高风险。"
        elif score >= 4.0:
            level = "中性"
            advice = "市场分化明显，建议结合个股形态和回测结果筛选机会。"
        elif score >= 2.5:
            level = "偏弱"
            advice = "市场承压，建议降低仓位并关注防守型机会。"
        else:
            level = "弱势"
            advice = "市场风险偏高，建议谨慎观望。"

        return {
            "score": score,
            "level": level,
            "advice": advice,
            "advance_ratio": round(advance_ratio, 4),
            "strong_ratio": round(strong_ratio, 4),
            "weak_ratio": round(weak_ratio, 4),
            "mean_change": round(mean_change, 4),
            "index_change": round(index_change, 4) if index_change is not None else None,
            "components": {key: round(value, 4) for key, value in components.items()},
        }

    def _top_rows(self, stocks: list[dict[str, Any]], field: str, *, reverse: bool, limit: int = 8) -> list[dict[str, Any]]:
        filtered = [item for item in stocks if item.get(field) is not None]
        return sorted(filtered, key=lambda item: float(item.get(field) or 0.0), reverse=reverse)[:limit]

    def _build_turnover_rank(self, stocks: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str, str]:
        turnover_rows = self._top_rows(stocks, "turnover_rate", reverse=True)
        if turnover_rows:
            return turnover_rows, "换手率榜", "turnover_rate"

        # 新浪实时源不提供换手率，使用成交量作为活跃榜兜底，避免页面空白。
        volume_rows = self._top_rows(stocks, "volume", reverse=True)
        if volume_rows:
            return volume_rows, "成交量榜", "volume"

        return self._top_rows(stocks, "amount", reverse=True), "成交额榜", "amount"

    def _limit_threshold(self, stock: dict[str, Any]) -> float:
        code = str(stock.get("code") or "")
        name = str(stock.get("name") or "").upper()
        board = str(stock.get("board") or "")
        if "ST" in name:
            return 5.0
        if board in {"创业板", "科创板"} or code.startswith(("300", "301", "688")):
            return 20.0
        if board == "北交所" or code.startswith(("4", "8", "920")):
            return 30.0
        return 10.0

    def _is_limit_up(self, stock: dict[str, Any]) -> bool:
        change = stock.get("change_percent")
        if change is None:
            return False
        return float(change) >= self._limit_threshold(stock) - 0.18

    def _is_limit_down(self, stock: dict[str, Any]) -> bool:
        change = stock.get("change_percent")
        if change is None:
            return False
        return float(change) <= -self._limit_threshold(stock) + 0.18

    def _count_bucket(self, values: list[float], lower: Optional[float], upper: Optional[float]) -> int:
        count = 0
        for value in values:
            number = float(value)
            if lower is not None and number < lower:
                continue
            if upper is not None and number >= upper:
                continue
            count += 1
        return count

    def _safe_float(self, value: Any) -> Optional[float]:
        try:
            if value is None or pd.isna(value):
                return None
            text = str(value).strip()
            if text in {"", "-", "--"}:
                return None
            number = float(text.replace(",", "").replace("%", ""))
        except Exception:
            return None
        if not math.isfinite(number):
            return None
        return round(number, 4)

    def _calculate_index_change(self, indices: list[dict[str, Any]]) -> Optional[float]:
        weighted_indices = {
            "000001": 0.35,
            "399001": 0.30,
            "399006": 0.20,
            "000688": 0.15,
        }
        weighted_total = 0.0
        weight_sum = 0.0
        for item in indices:
            change = item.get("change_percent")
            if change is None:
                continue
            code = str(item.get("code") or "")
            weight = weighted_indices.get(code, 0.10)
            weighted_total += float(change) * weight
            weight_sum += weight
        if weight_sum <= 0:
            return None
        return weighted_total / weight_sum

    def _clamp(self, value: float, lower: float, upper: float) -> float:
        return max(lower, min(upper, value))

    def _resolve_market(self, code: str) -> str:
        if code.startswith(("4", "8", "920")):
            return "北交所"
        if code.startswith(("6", "9")):
            return "沪市"
        if code.startswith(("0", "2", "3")):
            return "深市"
        return "A股"

    def _resolve_board(self, code: str) -> str:
        if code.startswith("688"):
            return "科创板"
        if code.startswith(("300", "301")):
            return "创业板"
        if code.startswith(("600", "601", "603", "605", "900")):
            return "沪市A股"
        if code.startswith(("000", "001", "002", "003")):
            return "深市A股"
        if code.startswith(("4", "8", "920")):
            return "北交所"
        return "其他"

    def _build_fallback_index_rows(self) -> list[dict[str, Any]]:
        return [
            {
                "code": "000001",
                "name": "上证指数",
                "latest_price": 3218.64,
                "change_amount": 12.42,
                "change_percent": 0.39,
                "amount": 482300000000.0,
            },
            {
                "code": "399001",
                "name": "深证成指",
                "latest_price": 9842.17,
                "change_amount": -31.85,
                "change_percent": -0.32,
                "amount": 611900000000.0,
            },
            {
                "code": "399006",
                "name": "创业板指",
                "latest_price": 1986.55,
                "change_amount": 8.16,
                "change_percent": 0.41,
                "amount": 237600000000.0,
            },
            {
                "code": "000688",
                "name": "科创50",
                "latest_price": 742.90,
                "change_amount": -2.21,
                "change_percent": -0.30,
                "amount": 86400000000.0,
            },
        ]

    def _build_fallback_stock_rows(self) -> list[dict[str, Any]]:
        samples = [
            ("600519", "贵州茅台", 1520.50, 1.26),
            ("300750", "宁德时代", 196.42, -0.84),
            ("601318", "中国平安", 46.18, 0.52),
            ("000333", "美的集团", 68.72, 1.05),
            ("600036", "招商银行", 36.91, -0.38),
            ("002594", "比亚迪", 218.35, 2.14),
            ("000858", "五粮液", 148.66, -1.18),
            ("601012", "隆基绿能", 18.43, 0.16),
            ("600030", "中信证券", 22.96, 0.88),
            ("000001", "平安银行", 11.28, -0.71),
            ("600900", "长江电力", 27.41, 0.24),
            ("300059", "东方财富", 14.76, 3.18),
            ("688981", "中芯国际", 50.92, -1.64),
            ("688111", "金山办公", 274.20, 2.76),
            ("601899", "紫金矿业", 17.86, 4.22),
            ("600276", "恒瑞医药", 43.35, -2.08),
            ("002415", "海康威视", 31.42, 0.34),
            ("000725", "京东方A", 4.18, -0.48),
            ("600887", "伊利股份", 27.06, 0.67),
            ("300760", "迈瑞医疗", 286.10, -1.92),
            ("601888", "中国中免", 74.55, 1.73),
            ("603259", "药明康德", 49.86, -3.46),
            ("002230", "科大讯飞", 44.62, 5.28),
            ("601668", "中国建筑", 5.92, 0.17),
            ("601398", "工商银行", 5.86, -0.17),
            ("600000", "浦发银行", 8.11, 0.00),
            ("301308", "江波龙", 82.34, 8.46),
            ("688041", "海光信息", 94.82, 6.75),
            ("832000", "安徽凤凰", 12.46, -6.18),
            ("920118", "太湖远大", 18.72, 9.92),
        ]

        rows: list[dict[str, Any]] = []
        for index, (code, name, base_price, change_percent) in enumerate(samples, start=1):
            latest_price = round(base_price * (1 + change_percent / 100), 2)
            change_amount = round(latest_price - base_price, 2)
            amount = float((80 + index * 13) * 100000000)
            volume = float((350 + index * 21) * 10000)
            rows.append(
                {
                    "code": code,
                    "name": name,
                    "latest_price": latest_price,
                    "change_percent": change_percent,
                    "change_amount": change_amount,
                    "turnover_rate": round(0.7 + (index % 9) * 0.64, 2),
                    "amplitude": round(1.1 + (index % 7) * 0.42, 2),
                    "volume": volume,
                    "amount": amount,
                    "pe_dynamic": round(8.5 + (index % 11) * 4.3, 2),
                    "market": self._resolve_market(code),
                    "board": self._resolve_board(code),
                }
            )
        return rows
