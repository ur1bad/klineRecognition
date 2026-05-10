from __future__ import annotations

from typing import Any, Optional

import streamlit as st

from frontend.shared import (
    PATTERN_OPTIONS,
    is_today,
    load_records_payload,
    record_can_backtest,
    render_home_records_table,
    render_recent_activity_card,
    render_stat_card,
    render_system_status_card,
)


def render_home_page(health: Optional[dict[str, Any]], health_error: Optional[str]) -> None:
    records_payload, records_error = load_records_payload(limit=500)
    items = records_payload.get("items", [])
    total_records = int(records_payload.get("total", 0))
    today_records = sum(1 for item in items if is_today(item.get("created_at")))
    supported_count = len(PATTERN_OPTIONS) - 1
    ready_backtests = sum(1 for item in items if record_can_backtest(item))

    st.markdown(
        f"""
        <div class="welcome-card">
            <div>
                <div class="welcome-pill">系统首页</div>
                <h2>欢迎使用 K线图形态识别系统</h2>
                <p>
                    本系统面向 K 线图形态识别与结果分析，支持图像上传识别、自动生成识别、历史记录查询和回测验证等功能
                </p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    stat_col1, stat_col2, stat_col3, stat_col4 = st.columns(4)
    with stat_col1:
        render_stat_card("历史识别总数", str(total_records), "系统已保存的识别记录总量", "emerald")
    with stat_col2:
        render_stat_card("今日识别次数", str(today_records), "当日系统识别任务活跃度", "forest")
    with stat_col3:
        render_stat_card("已支持形态类别数", str(supported_count), "头肩顶、头肩底、双顶、双底、上升三角形、下降三角形、无明显形态", "sage")
    with stat_col4:
        render_stat_card("回测任务数", str(ready_backtests), "具备直接回测条件的历史记录数量", "mint")

    left, right = st.columns([1.25, 1.0])
    with left:
        render_recent_activity_card(items)
    with right:
        render_system_status_card(health, health_error or records_error, total_records, ready_backtests)

    render_home_records_table(items)
