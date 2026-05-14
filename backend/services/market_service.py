from __future__ import annotations

import contextlib
import io
import math
import time
from datetime import datetime, timedelta
from typing import Any, Optional

import akshare as ak
import pandas as pd


CACHE_TTL_SECONDS = 15 * 60
DETAIL_HISTORY_DAYS = 520
SOURCE_NAME = "AkShare 东方财富实时行情"
INDEX_CODES = ["000001", "399001", "399006", "000688"]


class MarketService:
    """Provide lightweight A-share market overview data for the frontend."""

    def __init__(self) -> None:
        self._cache_payload: Optional[dict[str, Any]] = None
        self._cache_created_at = 0.0
        self._history_cache: dict[tuple[str, str, int], dict[str, Any]] = {}

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

    def get_stock_detail(
        self,
        stock_code: str,
        *,
        force_refresh: bool = False,
        history_days: int = DETAIL_HISTORY_DAYS,
        adjust: str = "qfq",
    ) -> dict[str, Any]:
        code = self._normalize_stock_code(stock_code)
        history_days = DETAIL_HISTORY_DAYS
        overview = self.get_overview(force_refresh=force_refresh)
        stock = next((item for item in overview.get("stocks", []) if item.get("code") == code), None)
        if stock is None:
            stock = self._build_minimal_stock_row(code)

        try:
            history, history_source = self._get_history_rows_with_cache(
                code,
                history_days=history_days,
                adjust=adjust,
                force_refresh=force_refresh,
            )
        except Exception as exc:
            history = self._build_fallback_history_rows(stock, history_days=history_days)
            history_source = f"示例走势（历史行情源不可用：{type(exc).__name__}）"
            self._store_history_cache(code, adjust, history_days, history, history_source)

        stock = self._enrich_stock_detail_metrics(stock, history)
        history = self._align_latest_history_with_spot(stock, history)

        try:
            minute, minute_source = self._fetch_minute_rows(code)
        except Exception as exc:
            minute = self._build_fallback_minute_rows(stock)
            minute_source = f"示例分时（分钟行情源不可用：{type(exc).__name__}）"

        return {
            "updated_at": overview.get("updated_at") or datetime.now().isoformat(timespec="seconds"),
            "source": overview.get("source") or SOURCE_NAME,
            "history_source": history_source,
            "minute_source": minute_source,
            "stock": stock,
            "history": history,
            "minute": minute,
        }

    def _is_cache_fresh(self) -> bool:
        return (time.time() - self._cache_created_at) <= CACHE_TTL_SECONDS

    def _enrich_stock_detail_metrics(self, stock: dict[str, Any], history: list[dict[str, Any]]) -> dict[str, Any]:
        enriched = dict(stock)
        spot_volume = enriched.get("volume")
        spot_amount = enriched.get("amount")
        spot_price = enriched.get("latest_price")
        latest_history = self._latest_history_row(history)
        if latest_history:
            fallback_pairs = [
                ("latest_price", "close"),
                ("change_percent", "change_percent"),
                ("volume", "volume"),
                ("amount", "amount"),
            ]
            for stock_field, history_field in fallback_pairs:
                if self._is_missing(enriched.get(stock_field)) and not self._is_missing(latest_history.get(history_field)):
                    enriched[stock_field] = latest_history.get(history_field)

        if self._is_missing(enriched.get("turnover_rate")):
            turnover_rate = self._resolve_detail_turnover_rate(
                history,
                current_volume=spot_volume,
                current_amount=spot_amount,
                current_price=spot_price,
            )
            if turnover_rate is not None:
                enriched["turnover_rate"] = turnover_rate
        return enriched

    def _latest_history_row(self, history: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
        if not history:
            return None
        return max(history, key=lambda row: str(row.get("trade_date") or ""))

    def _resolve_detail_turnover_rate(
        self,
        history: list[dict[str, Any]],
        *,
        current_volume: Any,
        current_amount: Any,
        current_price: Any,
    ) -> Optional[float]:
        latest = self._latest_history_row(history)
        if latest and str(latest.get("trade_date") or "") == datetime.now().date().isoformat():
            latest_turnover = self._safe_float(latest.get("turnover_rate"))
            if latest_turnover is not None:
                return latest_turnover
        return self._estimate_current_turnover_rate(
            history,
            current_volume=current_volume,
            current_amount=current_amount,
            current_price=current_price,
        )

    def _estimate_current_turnover_rate(
        self,
        history: list[dict[str, Any]],
        *,
        current_volume: Any,
        current_amount: Any,
        current_price: Any,
    ) -> Optional[float]:
        current_volume_shares = self._volume_as_shares(current_volume, current_amount, current_price)
        if current_volume_shares is None or current_volume_shares <= 0:
            return None

        history_rows = sorted(history, key=lambda row: str(row.get("trade_date") or ""), reverse=True)
        for row in history_rows:
            history_turnover = self._safe_float(row.get("turnover_rate"))
            history_volume_shares = self._volume_as_shares(row.get("volume"), row.get("amount"), row.get("close"))
            if history_turnover is None or history_turnover <= 0 or history_volume_shares is None or history_volume_shares <= 0:
                continue
            float_shares = history_volume_shares / (history_turnover / 100.0)
            if float_shares > 0:
                return round((current_volume_shares / float_shares) * 100.0, 4)
        return None

    def _volume_as_shares(self, volume: Any, amount: Any, price: Any) -> Optional[float]:
        volume_number = self._safe_float(volume)
        amount_number = self._safe_float(amount)
        price_number = self._safe_float(price)
        if amount_number is not None and price_number is not None and price_number > 0:
            implied_shares = amount_number / price_number
            if implied_shares > 0:
                if volume_number is None or volume_number <= 0:
                    return implied_shares
                if 0.5 <= volume_number / implied_shares <= 2.0:
                    return volume_number
                if 0.5 <= (volume_number * 100.0) / implied_shares <= 2.0:
                    return volume_number * 100.0
                return implied_shares
        return volume_number

    def _align_latest_history_with_spot(self, stock: dict[str, Any], history: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not history or self._is_missing(stock.get("change_percent")):
            return history

        latest = self._latest_history_row(history)
        if not latest or str(latest.get("trade_date") or "") != datetime.now().date().isoformat():
            return history

        aligned = self._copy_rows(history)
        for row in aligned:
            if row.get("trade_date") == latest.get("trade_date"):
                row["change_percent"] = stock.get("change_percent")
                break
        return aligned

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

    def _get_history_rows_with_cache(
        self,
        code: str,
        *,
        history_days: int,
        adjust: str,
        force_refresh: bool,
    ) -> tuple[list[dict[str, Any]], str]:
        cache_key = self._history_cache_key(code, adjust, history_days)
        cached = self._history_cache.get(cache_key)
        if not force_refresh and cached and self._is_cache_entry_fresh(cached):
            return self._copy_rows(cached.get("history") or []), str(cached.get("source") or "")

        history, history_source = self._fetch_history_rows(code, history_days=history_days, adjust=adjust)
        self._store_history_cache(code, adjust, history_days, history, history_source)
        return history, history_source

    def _store_history_cache(
        self,
        code: str,
        adjust: str,
        history_days: int,
        history: list[dict[str, Any]],
        source: str,
    ) -> None:
        cache_key = self._history_cache_key(code, adjust, history_days)
        self._history_cache[cache_key] = {
            "created_at": time.time(),
            "source": source,
            "history": self._copy_rows(history),
        }

    def _history_cache_key(self, code: str, adjust: str, history_days: int) -> tuple[str, str, int]:
        return (self._normalize_stock_code(code), str(adjust or ""), int(history_days))

    def _is_cache_entry_fresh(self, cache_entry: dict[str, Any]) -> bool:
        try:
            created_at = float(cache_entry.get("created_at") or 0.0)
        except Exception:
            return False
        return (time.time() - created_at) <= CACHE_TTL_SECONDS

    def _copy_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [dict(row) for row in rows]

    def _fetch_history_rows(self, code: str, *, history_days: int, adjust: str) -> tuple[list[dict[str, Any]], str]:
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=max(90, int(history_days) * 2))).strftime("%Y%m%d")
        prefixed_code = self._minute_fetch_symbol(code)
        attempts = [
            (
                "东方财富日线行情",
                lambda: ak.stock_zh_a_hist(
                    symbol=code,
                    start_date=start_date,
                    end_date=end_date,
                    adjust=adjust,
                ),
            ),
            (
                "新浪日线行情",
                lambda: ak.stock_zh_a_daily(
                    symbol=prefixed_code,
                    start_date=start_date,
                    end_date=end_date,
                    adjust=adjust,
                ),
            ),
            (
                "腾讯日线行情",
                lambda: ak.stock_zh_a_hist_tx(
                    symbol=prefixed_code,
                    start_date=start_date,
                    end_date=end_date,
                    adjust=adjust,
                ),
            ),
        ]

        last_error: Optional[Exception] = None
        for source_name, fetch_fn in attempts:
            try:
                dataframe = self._call_data_source(fetch_fn)
                rows = self._build_history_rows(dataframe, limit=history_days)
                if rows:
                    return rows, source_name
                last_error = ValueError(f"{source_name} 返回空行情。")
            except Exception as exc:
                last_error = exc

        if last_error is not None:
            raise last_error
        raise ValueError("历史行情为空。")

    def _build_history_rows(self, dataframe: pd.DataFrame, *, limit: int) -> list[dict[str, Any]]:
        if dataframe is None or dataframe.empty:
            return []

        rows: list[dict[str, Any]] = []
        data = dataframe.tail(max(1, int(limit))).copy()
        for _, item in data.iterrows():
            trade_date = pd.to_datetime(self._first_existing_value(item, ["日期", "date", "Date", "day", "trade_date"]), errors="coerce")
            if pd.isna(trade_date):
                continue
            close = self._safe_float(self._first_existing_value(item, ["收盘", "close", "Close"]))
            volume = self._safe_float(self._first_existing_value(item, ["成交量", "volume", "Volume", "vol"]))
            amount = self._safe_float(self._first_existing_value(item, ["成交额", "amount", "Amount"]))
            if volume is None:
                volume = amount
                amount = round(volume * close, 2) if volume is not None and close is not None else None
            rows.append(
                {
                    "trade_date": trade_date.strftime("%Y-%m-%d"),
                    "open": self._safe_float(self._first_existing_value(item, ["开盘", "open", "Open"])),
                    "high": self._safe_float(self._first_existing_value(item, ["最高", "high", "High"])),
                    "low": self._safe_float(self._first_existing_value(item, ["最低", "low", "Low"])),
                    "close": close,
                    "volume": volume,
                    "amount": amount,
                    "change_percent": self._safe_float(self._first_existing_value(item, ["涨跌幅", "change_percent", "pct_chg"])),
                    "turnover_rate": self._extract_history_turnover_rate(item),
                }
            )
        return self._fill_history_derived_fields(rows)

    def _fill_history_derived_fields(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows = sorted(rows, key=lambda row: str(row.get("trade_date") or ""))
        previous_close: Optional[float] = None
        for row in rows:
            close = row.get("close")
            if row.get("change_percent") is None and previous_close and close is not None:
                row["change_percent"] = round(((float(close) - previous_close) / previous_close) * 100, 4)
            if row.get("amount") is None and row.get("volume") is not None and close is not None:
                row["amount"] = round(float(row["volume"]) * float(close), 2)
            if close is not None:
                previous_close = float(close)
        return rows

    def _extract_history_turnover_rate(self, row: pd.Series) -> Optional[float]:
        rate = self._safe_float(self._first_existing_value(row, ["换手率", "turnover_rate"]))
        if rate is not None:
            return rate
        turnover = self._safe_float(self._first_existing_value(row, ["turnover"]))
        if turnover is None:
            return None
        return round(turnover * 100, 4) if abs(turnover) <= 1 else turnover

    def _fetch_minute_rows(self, code: str) -> tuple[list[dict[str, Any]], str]:
        end_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d 15:30:00")
        start_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d 09:30:00")
        prefixed_code = self._minute_fetch_symbol(code)
        attempts = [
            (
                "东方财富分钟行情",
                lambda: ak.stock_zh_a_hist_min_em(
                    symbol=code,
                    start_date=start_date,
                    end_date=end_date,
                    period="1",
                    adjust="",
                ),
            ),
            (
                "新浪分钟行情",
                lambda: ak.stock_zh_a_minute(symbol=prefixed_code, period="1", adjust=""),
            ),
        ]

        last_error: Optional[Exception] = None
        for source_name, fetch_fn in attempts:
            try:
                dataframe = self._call_data_source(fetch_fn)
                rows = self._build_minute_rows(dataframe, limit=260)
                if rows:
                    return rows, source_name
            except Exception as exc:
                last_error = exc

        if last_error is not None:
            raise last_error
        raise ValueError("分钟行情为空。")

    def _build_minute_rows(self, dataframe: pd.DataFrame, *, limit: int) -> list[dict[str, Any]]:
        if dataframe is None or dataframe.empty:
            return []

        data = dataframe.copy()
        time_column = self._first_existing_column(data, ["时间", "日期时间", "day", "datetime", "日期"])
        if not time_column:
            return []

        data["_trade_time"] = pd.to_datetime(data[time_column], errors="coerce")
        data = data.dropna(subset=["_trade_time"]).sort_values("_trade_time")
        if data.empty:
            return []

        latest_day = data["_trade_time"].dt.date.max()
        data = data[data["_trade_time"].dt.date == latest_day].tail(max(1, int(limit)))

        rows: list[dict[str, Any]] = []
        for _, item in data.iterrows():
            price = self._safe_float(self._first_existing_value(item, ["收盘", "close", "最新价", "price"]))
            if price is None:
                continue
            trade_time = item["_trade_time"]
            rows.append(
                {
                    "trade_time": trade_time.strftime("%Y-%m-%d %H:%M:%S"),
                    "price": price,
                    "volume": self._safe_float(self._first_existing_value(item, ["成交量", "volume", "vol"])),
                    "amount": self._safe_float(self._first_existing_value(item, ["成交额", "amount"])),
                    "average_price": self._safe_float(self._first_existing_value(item, ["均价", "average_price", "avg_price"])),
                }
            )
        return rows

    def _first_existing_column(self, dataframe: pd.DataFrame, candidates: list[str]) -> Optional[str]:
        for column in candidates:
            if column in dataframe.columns:
                return column
        return None

    def _first_existing_value(self, row: pd.Series, candidates: list[str]) -> Any:
        for column in candidates:
            if column not in row:
                continue
            value = row.get(column)
            if value is not None and not pd.isna(value):
                return value
        return None

    def _minute_fetch_symbol(self, code: str) -> str:
        if code.startswith(("6", "9")):
            return f"sh{code}"
        return f"sz{code}"

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
            amplitude = self._safe_float(item.get("振幅"))
            if amplitude is None:
                amplitude = self._calculate_spot_amplitude(item)
            rows.append(
                {
                    "code": code,
                    "name": name,
                    "latest_price": self._safe_float(item.get("最新价")),
                    "change_percent": self._safe_float(item.get("涨跌幅")),
                    "change_amount": self._safe_float(item.get("涨跌额")),
                    "turnover_rate": self._safe_float(item.get("换手率")),
                    "amplitude": amplitude,
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
        if text.lower().startswith(("sh", "sz", "bj")):
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

    def _calculate_spot_amplitude(self, row: pd.Series) -> Optional[float]:
        high = self._safe_float(self._first_existing_value(row, ["最高", "high", "High"]))
        low = self._safe_float(self._first_existing_value(row, ["最低", "low", "Low"]))
        previous_close = self._safe_float(self._first_existing_value(row, ["昨收", "昨收价", "pre_close", "previous_close"]))
        if high is None or low is None or previous_close is None or previous_close <= 0:
            return None
        return round(((high - low) / previous_close) * 100, 4)

    def _is_missing(self, value: Any) -> bool:
        try:
            if value is None or pd.isna(value):
                return True
        except Exception:
            return value is None
        return str(value).strip() in {"", "-", "--"}

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

    def _build_minimal_stock_row(self, code: str) -> dict[str, Any]:
        return {
            "code": code,
            "name": code,
            "latest_price": None,
            "change_percent": None,
            "change_amount": None,
            "turnover_rate": None,
            "amplitude": None,
            "volume": None,
            "amount": None,
            "pe_dynamic": None,
            "market": self._resolve_market(code),
            "board": self._resolve_board(code),
        }

    def _build_fallback_history_rows(self, stock: dict[str, Any], *, history_days: int) -> list[dict[str, Any]]:
        base_price = float(stock.get("latest_price") or 10.0)
        change_percent = float(stock.get("change_percent") or 0.0)
        day = datetime.now().date()
        trade_days = []
        while len(trade_days) < max(20, int(history_days)):
            if day.weekday() < 5:
                trade_days.append(day)
            day -= timedelta(days=1)
        trade_days.reverse()

        rows: list[dict[str, Any]] = []
        total = max(len(trade_days), 1)
        seed = sum(ord(char) for char in str(stock.get("code") or ""))
        for index, trade_day in enumerate(trade_days):
            wave = math.sin((index + seed % 17) / 4.0) * 0.018 + math.cos((index + seed % 11) / 7.0) * 0.010
            drift = ((index + 1) / total - 1.0) * (change_percent / 100.0) * 0.35
            close = max(0.01, base_price * (1.0 + wave + drift))
            open_price = close * (1.0 - math.sin((index + 3) / 5.0) * 0.006)
            high = max(open_price, close) * 1.012
            low = min(open_price, close) * 0.988
            volume = float(400000 + (index + 1) * 9000 + (seed % 97) * 1000)
            rows.append(
                {
                    "trade_date": trade_day.strftime("%Y-%m-%d"),
                    "open": round(open_price, 2),
                    "high": round(high, 2),
                    "low": round(low, 2),
                    "close": round(close, 2),
                    "volume": round(volume, 2),
                    "amount": round(volume * close, 2),
                    "change_percent": None,
                    "turnover_rate": None,
                }
            )
        return rows

    def _build_fallback_minute_rows(self, stock: dict[str, Any]) -> list[dict[str, Any]]:
        base_price = float(stock.get("latest_price") or 10.0)
        change_percent = float(stock.get("change_percent") or 0.0)
        trade_day = datetime.now().date()
        while trade_day.weekday() >= 5:
            trade_day -= timedelta(days=1)

        minute_points: list[datetime] = []
        for start_hour, start_minute, end_hour, end_minute in [(9, 30, 11, 30), (13, 0, 15, 0)]:
            current = datetime.combine(trade_day, datetime.min.time()).replace(hour=start_hour, minute=start_minute)
            end = datetime.combine(trade_day, datetime.min.time()).replace(hour=end_hour, minute=end_minute)
            while current <= end:
                minute_points.append(current)
                current += timedelta(minutes=1)

        rows: list[dict[str, Any]] = []
        seed = sum(ord(char) for char in str(stock.get("code") or ""))
        total = max(len(minute_points), 1)
        for index, trade_time in enumerate(minute_points):
            progress = index / total
            wave = math.sin((index + seed % 13) / 13.0) * 0.008 + math.cos((index + seed % 7) / 19.0) * 0.006
            drift = (progress - 0.5) * (change_percent / 100.0) * 0.35
            price = max(0.01, base_price * (1.0 + wave + drift))
            volume = 1500 + (seed % 97) * 12 + abs(math.sin(index / 9.0)) * 6200
            rows.append(
                {
                    "trade_time": trade_time.strftime("%Y-%m-%d %H:%M:%S"),
                    "price": round(price, 2),
                    "volume": round(volume, 2),
                    "amount": round(volume * price, 2),
                    "average_price": round(base_price * (1.0 + drift * 0.35), 2),
                }
            )
        return rows

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
