from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

import pandas as pd

from backend.services.kline_service import KlineChartService
from backend.utils.date_utils import DateInputError, parse_date


class ContextResolveService:
    """Resolve frontend form context through backend-owned market data logic."""

    def __init__(self, chart_service: Optional[KlineChartService] = None) -> None:
        self.chart_service = chart_service or KlineChartService()

    def resolve_upload_context(
        self,
        *,
        stock_code: str,
        start_date: str,
        end_date: str,
        window_size: Optional[int],
        adjust: str = "qfq",
    ) -> dict[str, object]:
        resolved_start_date = start_date.strip()
        resolved_end_date = end_date.strip()
        resolved_stock_code = stock_code.strip()
        resolved_window_size = int(window_size) if window_size is not None else None
        validation_errors: list[str] = []
        notices: list[str] = []

        parsed_start_date = self._parse_calendar_date_input(
            resolved_start_date,
            "开始日期",
            validation_errors,
        )
        parsed_end_date = self._parse_calendar_date_input(
            resolved_end_date,
            "结束日期",
            validation_errors,
        )
        has_start_date = bool(parsed_start_date)
        has_end_date = bool(parsed_end_date)
        has_any_date = has_start_date or has_end_date
        has_window_size = resolved_window_size is not None

        if has_any_date and not resolved_stock_code:
            validation_errors.append("填写开始日期或结束日期时，必须同时填写股票代码。")

        if parsed_start_date and parsed_end_date and parsed_start_date > parsed_end_date:
            validation_errors.append("开始日期不能晚于结束日期。")

        if not validation_errors and has_any_date:
            if has_start_date and has_end_date:
                try:
                    trading_df = self.fetch_generate_dataframe(
                        resolved_stock_code,
                        resolved_start_date,
                        resolved_end_date,
                        adjust=adjust,
                    )
                    trading_day_count = len(trading_df)
                    if has_window_size:
                        if trading_day_count != int(resolved_window_size):
                            validation_errors.append(
                                f"开始日期到结束日期区间内实际共有 {trading_day_count} 个交易日，"
                                f"与窗口大小 {int(resolved_window_size)} 不一致，请调整后再提交。"
                            )
                    else:
                        resolved_window_size = trading_day_count
                        notices.append(
                            f"已根据开始日期和结束日期自动计算窗口大小：{trading_day_count} 个交易日。"
                        )
                except Exception as exc:
                    validation_errors.append(f"无法按交易日解析当前日期区间：{exc}")
            elif has_start_date or has_end_date:
                if not has_window_size:
                    validation_errors.append("仅填写一个日期时，必须同时填写窗口大小。")
                else:
                    try:
                        if has_start_date:
                            resolved_end_date = self.infer_generate_end_date(
                                resolved_stock_code,
                                resolved_start_date,
                                int(resolved_window_size),
                                adjust=adjust,
                            )
                            notices.append(
                                "未填写结束日期，已根据开始日期和窗口大小按交易日自动生成结束日期："
                                f"{resolved_end_date}"
                            )
                        else:
                            resolved_start_date = self.infer_generate_start_date(
                                resolved_stock_code,
                                resolved_end_date,
                                int(resolved_window_size),
                                adjust=adjust,
                            )
                            notices.append(
                                "未填写开始日期，已根据结束日期和窗口大小按交易日自动生成开始日期："
                                f"{resolved_start_date}"
                            )
                    except Exception as exc:
                        validation_errors.append(f"无法根据交易日自动补全日期：{exc}")

        return {
            "stock_code": resolved_stock_code,
            "start_date": resolved_start_date,
            "end_date": resolved_end_date,
            "window_size": resolved_window_size,
            "validation_errors": validation_errors,
            "notices": notices,
        }

    def resolve_generate_context(
        self,
        *,
        stock_code: str,
        start_date: str,
        end_date: str,
        window_size: Optional[int],
        adjust: str = "qfq",
    ) -> dict[str, object]:
        resolved_stock_code = stock_code.strip()
        resolved_start_date = start_date.strip()
        resolved_end_date = end_date.strip()
        validation_errors: list[str] = []
        notices: list[str] = []

        if not resolved_stock_code:
            validation_errors.append("请填写股票代码。")

        parsed_start_date = self._parse_calendar_date_input(
            resolved_start_date,
            "开始日期",
            validation_errors,
        )
        parsed_end_date = self._parse_calendar_date_input(
            resolved_end_date,
            "结束日期",
            validation_errors,
        )

        has_start_date = bool(resolved_start_date)
        has_end_date = bool(resolved_end_date)
        has_window_size = window_size is not None

        if not has_start_date and not has_end_date and not has_window_size:
            validation_errors.append("请至少填写开始日期、结束日期、窗口大小中的两个字段。")
            return self._generate_response(None, validation_errors, notices)
        if has_start_date and not has_end_date and not has_window_size:
            validation_errors.append("当前输入缺少必要字段：请补充结束日期或窗口大小。")
            return self._generate_response(None, validation_errors, notices)
        if has_end_date and not has_start_date and not has_window_size:
            validation_errors.append("当前输入缺少必要字段：请补充开始日期或窗口大小。")
            return self._generate_response(None, validation_errors, notices)
        if has_window_size and not has_start_date and not has_end_date:
            validation_errors.append("当前输入缺少必要字段：请补充开始日期或结束日期。")
            return self._generate_response(None, validation_errors, notices)

        if validation_errors:
            return self._generate_response(None, validation_errors, notices)

        if parsed_start_date and parsed_end_date and parsed_start_date > parsed_end_date:
            validation_errors.append("开始日期不能晚于结束日期。")
            return self._generate_response(None, validation_errors, notices)

        resolved_window_size: Optional[int]
        try:
            if parsed_start_date and parsed_end_date and has_window_size:
                dataframe = self.fetch_generate_dataframe(
                    resolved_stock_code,
                    resolved_start_date,
                    resolved_end_date,
                    adjust=adjust,
                )
                actual_trading_days = len(dataframe)
                if actual_trading_days != int(window_size):
                    validation_errors.append(
                        f"当前区间内实际交易日个数为 {actual_trading_days}，"
                        f"与窗口大小 {int(window_size)} 不一致。"
                    )
                    return self._generate_response(None, validation_errors, notices)
                resolved_window_size = int(window_size)
            elif parsed_start_date and has_window_size:
                resolved_window_size = int(window_size)
                resolved_end_date = self.infer_generate_end_date(
                    resolved_stock_code,
                    resolved_start_date,
                    resolved_window_size,
                    adjust=adjust,
                )
                notices.append(f"未填写结束日期，已自动生成结束日期：{resolved_end_date}")
            elif parsed_end_date and has_window_size:
                resolved_window_size = int(window_size)
                resolved_start_date = self.infer_generate_start_date(
                    resolved_stock_code,
                    resolved_end_date,
                    resolved_window_size,
                    adjust=adjust,
                )
                notices.append(f"未填写开始日期，已自动生成开始日期：{resolved_start_date}")
            elif parsed_start_date and parsed_end_date:
                dataframe = self.fetch_generate_dataframe(
                    resolved_stock_code,
                    resolved_start_date,
                    resolved_end_date,
                    adjust=adjust,
                )
                resolved_window_size = len(dataframe)
                notices.append(f"未填写窗口大小，已根据当前区间自动生成窗口大小：{resolved_window_size}")
            else:
                validation_errors.append(
                    "请输入符合要求的字段组合：开始日期+结束日期+窗口大小、开始日期+窗口大小、"
                    "结束日期+窗口大小，或开始日期+结束日期。"
                )
                return self._generate_response(None, validation_errors, notices)
        except Exception as exc:
            validation_errors.append(str(exc))
            return self._generate_response(None, validation_errors, notices)

        if int(resolved_window_size) < 20 or int(resolved_window_size) > 240:
            validation_errors.append(
                f"当前计算得到的窗口大小为 {int(resolved_window_size)}，"
                "超出系统支持范围（20 到 240）。"
            )
            return self._generate_response(None, validation_errors, notices)

        payload = {
            "stock_code": resolved_stock_code,
            "start_date": resolved_start_date,
            "end_date": resolved_end_date,
            "window_size": int(resolved_window_size),
            "adjust": adjust,
        }
        return self._generate_response(payload, validation_errors, notices)

    def fetch_generate_dataframe(
        self,
        stock_code: str,
        start_date_text: str,
        end_date_text: str,
        *,
        adjust: str = "qfq",
    ) -> pd.DataFrame:
        return self.chart_service.fetch_dataframe(
            stock_code=stock_code,
            start_date=start_date_text,
            end_date=end_date_text,
            adjust=adjust,
        )

    def infer_generate_end_date(
        self,
        stock_code: str,
        start_date_text: str,
        window_size: int,
        *,
        adjust: str = "qfq",
    ) -> str:
        start_date_value = datetime.strptime(start_date_text, "%Y-%m-%d").date()
        buffer_days = max(window_size * 3, 45)
        end_candidate = start_date_value + timedelta(days=buffer_days)
        last_count = 0

        for _ in range(6):
            dataframe = self.fetch_generate_dataframe(
                stock_code,
                start_date_text,
                end_candidate.isoformat(),
                adjust=adjust,
            )
            last_count = len(dataframe)
            if last_count >= window_size:
                return dataframe.index[window_size - 1].date().isoformat()
            end_candidate += timedelta(days=buffer_days)

        raise ValueError(
            f"从开始日期起当前仅获取到 {last_count} 个交易日，小于窗口大小 {window_size}。"
        )

    def infer_generate_start_date(
        self,
        stock_code: str,
        end_date_text: str,
        window_size: int,
        *,
        adjust: str = "qfq",
    ) -> str:
        end_date_value = datetime.strptime(end_date_text, "%Y-%m-%d").date()
        buffer_days = max(window_size * 3, 45)
        start_candidate = end_date_value - timedelta(days=buffer_days)
        last_count = 0

        for _ in range(6):
            dataframe = self.fetch_generate_dataframe(
                stock_code,
                start_candidate.isoformat(),
                end_date_text,
                adjust=adjust,
            )
            last_count = len(dataframe)
            if last_count >= window_size:
                return dataframe.index[-window_size].date().isoformat()
            start_candidate -= timedelta(days=buffer_days)

        raise ValueError(
            f"截至结束日期当前仅获取到 {last_count} 个交易日，小于窗口大小 {window_size}。"
        )

    def _parse_calendar_date_input(
        self,
        raw_value: str,
        field_label: str,
        validation_errors: list[str],
    ) -> Optional[date]:
        if not raw_value:
            return None
        try:
            return parse_date(raw_value, formats=("%Y-%m-%d",))
        except DateInputError as exc:
            if exc.reason == "nonexistent":
                validation_errors.append(f"{field_label}不存在：{exc.value_text}")
            else:
                validation_errors.append(f"{field_label}格式不正确，请按 YYYY-MM-DD 输入。")
            return None

    def _generate_response(
        self,
        payload: Optional[dict[str, object]],
        validation_errors: list[str],
        notices: list[str],
    ) -> dict[str, object]:
        return {
            "payload": payload,
            "validation_errors": validation_errors,
            "notices": notices,
        }
