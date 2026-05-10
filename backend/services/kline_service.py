from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from uuid import uuid4

import mplfinance as mpf
import pandas as pd

from backend.config import get_config
from backend.utils.date_utils import ensure_date_order, normalize_date_string, timestamp_slug, to_compact_date
from kline_core.data_loader import fetch_stock_data, save_and_resize_chart


def build_chart_style() -> mpf.Style:
    """严格复用现有项目中的 K 线图视觉风格。"""
    return mpf.make_mpf_style(
        base_mpf_style="yahoo",
        gridstyle="",
        rc={"font.size": 0, "lines.linewidth": 1.0},
    )


@dataclass
class GeneratedChart:
    stock_code: str
    image_path: Path
    window_df: pd.DataFrame
    full_df: pd.DataFrame
    window_size: int
    start_date: str
    end_date: str
    window_start: str
    window_end: str


class KlineChartService:
    def __init__(self) -> None:
        self.config = get_config()
        self.style = build_chart_style()

    def fetch_dataframe(self, stock_code: str, start_date: str, end_date: str, adjust: str = "qfq") -> pd.DataFrame:
        start_date, end_date = ensure_date_order(start_date, end_date)
        dataframe = fetch_stock_data(
            symbol=stock_code,
            start_date=to_compact_date(start_date),
            adjust=adjust,
            save_local=False,
            use_local_fallback=True,
        )
        if dataframe is None or dataframe.empty:
            raise ValueError(f"未能获取股票 {stock_code} 的行情数据。")

        start_ts = pd.Timestamp(start_date)
        end_ts = pd.Timestamp(end_date)
        dataframe = dataframe[(dataframe.index >= start_ts) & (dataframe.index <= end_ts)].copy()
        if dataframe.empty:
            raise ValueError(f"股票 {stock_code} 在 {start_date} 到 {end_date} 之间没有可用数据。")
        return dataframe

    def select_window(self, dataframe: pd.DataFrame, window_size: int, anchor_date: Optional[str] = None) -> pd.DataFrame:
        if len(dataframe) < window_size:
            raise ValueError(f"当前区间仅有 {len(dataframe)} 条数据，小于窗口大小 {window_size}。")

        if anchor_date is None:
            return dataframe.iloc[-window_size:].copy()

        anchor_ts = pd.Timestamp(normalize_date_string(anchor_date))
        eligible = dataframe[dataframe.index <= anchor_ts]
        if len(eligible) < window_size:
            raise ValueError(f"锚点日期 {anchor_date} 前的数据不足 {window_size} 条。")
        return eligible.iloc[-window_size:].copy()

    def render_chart(self, window_df: pd.DataFrame, output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        save_and_resize_chart(window_df, str(output_path), self.style)
        return output_path.resolve()

    def generate_chart(
        self,
        stock_code: str,
        start_date: str,
        end_date: str,
        window_size: int = 30,
        adjust: str = "qfq",
        anchor_date: Optional[str] = None,
    ) -> GeneratedChart:
        full_df = self.fetch_dataframe(stock_code=stock_code, start_date=start_date, end_date=end_date, adjust=adjust)
        window_df = self.select_window(full_df, window_size=window_size, anchor_date=anchor_date)

        filename = (
            f"{stock_code}_{window_df.index[-1].strftime('%Y%m%d')}"
            f"_w{window_size}_{timestamp_slug()}_{uuid4().hex[:6]}.png"
        )
        image_path = self.config.generated_dir / filename
        self.render_chart(window_df, image_path)

        return GeneratedChart(
            stock_code=stock_code,
            image_path=image_path.resolve(),
            window_df=window_df,
            full_df=full_df,
            window_size=window_size,
            start_date=normalize_date_string(start_date) or start_date,
            end_date=normalize_date_string(end_date) or end_date,
            window_start=window_df.index[0].date().isoformat(),
            window_end=window_df.index[-1].date().isoformat(),
        )
