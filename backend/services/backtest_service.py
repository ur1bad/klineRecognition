from __future__ import annotations

import re
from datetime import timedelta
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from backend.services.kline_service import KlineChartService
from backend.services.record_service import RecordService
from backend.utils.date_utils import normalize_date_string, parse_date
from backend.utils.labels import signal_direction


class BacktestService:
    """基于单条识别结果直接验证未来走势。"""

    def __init__(
        self,
        chart_service: Optional[KlineChartService] = None,
        record_service: Optional[RecordService] = None,
    ) -> None:
        self.chart_service = chart_service or KlineChartService()
        self.record_service = record_service or RecordService()

    def run_for_record(
        self,
        record_id: int,
        *,
        user_id: int,
        horizon_days: int = 3,
        adjust: str = "qfq",
    ) -> dict[str, Any]:
        record = self.record_service.get_record(record_id, user_id=user_id)
        if record is None:
            raise ValueError(f"记录 {record_id} 不存在。")
        if not self.record_service.is_backtest_ready(record):
            raise ValueError("当前记录缺少股票代码、窗口大小或结束日期，无法直接回测。")

        stock_code = str(record["stock_code"])
        window_size = int(record["window_size"])
        start_date = str(record["start_date"])
        anchor_date = self._resolve_anchor_date(record)
        extended_end = (parse_date(anchor_date) + timedelta(days=max(horizon_days * 5, 20))).isoformat()

        dataframe = self.chart_service.fetch_dataframe(
            stock_code=stock_code,
            start_date=start_date,
            end_date=extended_end,
            adjust=adjust,
        )

        anchor_position = self._locate_anchor_position(dataframe, anchor_date=anchor_date)
        if anchor_position < window_size - 1:
            raise ValueError("当前记录对应的窗口数据不足，无法回测。")
        if anchor_position + horizon_days >= len(dataframe):
            raise ValueError("当前记录后续交易日不足，无法完成未来走势验证。")

        window_df = dataframe.iloc[anchor_position - window_size + 1 : anchor_position + 1].copy()
        future_df = dataframe.iloc[anchor_position + 1 : anchor_position + horizon_days + 1].copy()

        current_close = float(window_df["Close"].iloc[-1])
        future_close = float(future_df["Close"].iloc[-1])
        future_return = (future_close - current_close) / current_close if current_close else 0.0
        direction = signal_direction(str(record["predicted_label"]))

        is_success: Optional[bool] = None
        if direction == "bullish":
            is_success = future_return > 0
        elif direction == "bearish":
            is_success = future_return < 0

        future_prices = []
        for trade_date, close_value in future_df["Close"].items():
            day_return = (float(close_value) - current_close) / current_close if current_close else 0.0
            future_prices.append(
                {
                    "trade_date": trade_date.date().isoformat(),
                    "close": round(float(close_value), 4),
                    "return_rate": round(day_return, 6),
                }
            )

        window_prices = [
            {
                "trade_date": trade_date.date().isoformat(),
                "close": round(float(close_value), 4),
            }
            for trade_date, close_value in window_df["Close"].items()
        ]

        record_with_url = self.record_service.attach_image_url(
            record,
            self.chart_service.config.streamlit_backend_url,
        )

        return {
            "summary": {
                "record_id": int(record["id"]),
                "stock_code": stock_code,
                "predicted_label": str(record["predicted_label"]),
                "signal_direction": direction,
                "window_start": window_df.index[0].date().isoformat(),
                "window_end": window_df.index[-1].date().isoformat(),
                "horizon_days": horizon_days,
                "current_close": round(current_close, 4),
                "future_close": round(future_close, 4),
                "future_return": round(future_return, 6),
                "future_direction": "上涨" if future_return > 0 else "下跌" if future_return < 0 else "横盘",
                "is_success": is_success,
                "inference_model": str(record.get("inference_model") or ""),
                "note": "以识别窗口结束日后的未来交易日表现，直接验证本次识别信号是否有效。",
            },
            "window_prices": window_prices,
            "future_prices": future_prices,
            "record_context": record_with_url,
            "extra": {
                "anchor_date": anchor_date,
                "source_type": record.get("source_type"),
                "adjust": adjust,
            },
        }

    def _resolve_anchor_date(self, record: dict[str, Any]) -> str:
        image_path = Path(str(record["image_path"]))
        match = re.search(r"_(\d{8})_w\d+_", image_path.name)
        if match:
            return normalize_date_string(match.group(1)) or str(record["end_date"])
        if record.get("end_date"):
            return str(record["end_date"])
        raise ValueError("无法从记录中解析识别窗口结束日期。")

    def _locate_anchor_position(self, dataframe: pd.DataFrame, anchor_date: str) -> int:
        anchor_ts = pd.Timestamp(normalize_date_string(anchor_date))
        eligible = dataframe[dataframe.index <= anchor_ts]
        if eligible.empty:
            raise ValueError(f"未找到锚点日期 {anchor_date} 之前的有效行情数据。")
        return int(dataframe.index.get_loc(eligible.index[-1]))
