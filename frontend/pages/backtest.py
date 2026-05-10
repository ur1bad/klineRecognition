from __future__ import annotations

from typing import Optional

import streamlit as st

from frontend.shared import (
    DEFAULT_BACKTEST_HORIZON,
    build_panel_header,
    fetch_backtest_result,
    format_datetime_text,
    load_records_payload,
    normalize_pattern_label,
    record_can_backtest,
    remember_record,
    render_backtest_visual,
    render_page_banner,
    render_placeholder,
)


def render_backtest_page() -> None:
    render_page_banner(
        "回测分析",
        "基于识别窗口结束日之后的历史交易表现，对识别结果进行回测验证",
        [],
    )

    records_payload, error = load_records_payload(limit=500)
    if error:
        st.error(f"获取记录失败：{error}")
        return

    ready_records = [item for item in records_payload["items"] if record_can_backtest(item)]
    if not ready_records:
        render_placeholder("暂无可回测记录", "请先执行一次自动生成识别，或在上传识别时补充股票代码与日期范围")
        return

    option_map = {
        f"#{item['id']} | {item['stock_code']} | {normalize_pattern_label(item['predicted_label'])} | {format_datetime_text(item.get('created_at'))}": item
        for item in ready_records
    }
    record_placeholder = "请选择识别记录"
    record_options = [record_placeholder] + list(option_map.keys())
    horizon_options = [1, 2, 3, 5, 8, 10]
    autorun_request = bool(st.session_state.get("backtest_autorun_request"))
    target_record_id = st.session_state.get("selected_backtest_record_id")

    default_record_label = record_placeholder
    if autorun_request and target_record_id is not None:
        for label, item in option_map.items():
            if int(item["id"]) == int(target_record_id):
                default_record_label = label
                break

    if st.session_state.get("backtest_record_select") not in record_options or autorun_request:
        st.session_state["backtest_record_select"] = default_record_label
    if st.session_state.get("backtest_horizon_select") not in horizon_options or autorun_request:
        st.session_state["backtest_horizon_select"] = DEFAULT_BACKTEST_HORIZON

    with st.container(key="backtest-control-panel"):
        st.markdown(
            build_panel_header("回测参数设置", "", "参数设置"),
            unsafe_allow_html=True,
        )
        with st.form("backtest_control_form", clear_on_submit=False):
            control_col1, control_col2, control_col3 = st.columns([1.65, 0.7, 0.7])
            with control_col1:
                selected_label = st.selectbox(
                    "选择识别记录",
                    options=record_options,
                    key="backtest_record_select",
                )
            with control_col2:
                horizon_days = st.selectbox(
                    "未来持有天数",
                    options=horizon_options,
                    key="backtest_horizon_select",
                )
            with control_col3:
                st.markdown("<div style='height:1.8rem;'></div>", unsafe_allow_html=True)
                run_clicked = st.form_submit_button("执行回测分析", type="primary", use_container_width=True)

    selected_record = option_map.get(selected_label)
    selected_result_key: Optional[tuple[int, int]] = None
    if selected_record:
        remember_record(int(selected_record["id"]))
        selected_result_key = (int(selected_record["id"]), int(horizon_days))

    should_run = bool(selected_record and (run_clicked or autorun_request))
    st.session_state["backtest_autorun_request"] = False
    if should_run and selected_record and selected_result_key:
        with st.spinner("正在执行回测分析，请稍候..."):
            backtest_result, backtest_error = fetch_backtest_result(int(selected_record["id"]), int(horizon_days))
            if backtest_error:
                st.error(f"回测失败：{backtest_error}")
            else:
                st.session_state["backtest_result"] = backtest_result
                st.session_state["backtest_result_key"] = selected_result_key

    backtest_result = st.session_state.get("backtest_result")
    executed_result_key = st.session_state.get("backtest_result_key")
    if not backtest_result or not executed_result_key:
        render_placeholder("回测结果区域", "选择识别记录并点击“执行回测分析”后，这里会展示收益曲线、关键指标与结论摘要")
        return

    executed_record = next(
        (item for item in ready_records if int(item["id"]) == int(executed_result_key[0])),
        None,
    )

    render_backtest_visual(
        backtest_result,
        title="回测分析",
        image_url=executed_record.get("image_url") if executed_record else None,
    )
