from __future__ import annotations

import streamlit as st

from frontend.shared import (
    api_post_json,
    build_panel_header,
    fetch_backtest_result,
    remember_record,
    render_backtest_visual,
    render_fixed_image_preview,
    render_page_banner,
    render_placeholder,
    render_prediction_result_card,
    validate_generate_form_inputs,
)


def render_auto_page() -> None:
    render_page_banner(
        "自动生成并识别",
        "输入股票参数信息后，系统会自动抓取数据、生成K线图并完成识别",
        [],
    )

    form_col, intro_col = st.columns([1.18, 0.92])
    with form_col:
        with st.form("generate_predict_form", clear_on_submit=False):
            st.markdown(
                build_panel_header("生成参数面板", "输入股票代码、日期区间和窗口参数，用于自动生成K线图"),
                unsafe_allow_html=True,
            )
            stock_code = st.text_input("股票代码", value="", placeholder="示例：600519", key="generate_stock_code")
            start_date = st.text_input("开始日期（可选）", value="", placeholder="示例：2024-01-01", key="generate_start_date")
            end_date = st.text_input("结束日期（可选）", value="", placeholder="示例：2024-06-30", key="generate_end_date")
            window_size = st.number_input(
                "窗口大小（可选）",
                min_value=20,
                max_value=240,
                value=None,
                step=1,
                placeholder="示例：30",
                key="generate_window_size",
            )
            submitted = st.form_submit_button("生成并识别", type="primary", use_container_width=True)
    with intro_col:
        st.markdown(
            f"""
            <div class="content-card">
                {build_panel_header("操作说明", "", "使用说明")}
                <div class="tip-list">
                    <div class="tip-item">
                        <strong>输入股票参数</strong>
                        <span>输入股票信息，用于自动抓取数据、生成K线图</span>
                    </div>
                    <div class="tip-item">
                        <strong>点击生成并识别</strong>
                        <span>自动对生成的K线图进行形态识别，并可进一步展示回测验证结果</span>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    if submitted:
        st.session_state["generate_result"] = None
        st.session_state["generate_backtest_result"] = None
        st.session_state["generate_backtest_error"] = None

        payload, validation_errors, notices = validate_generate_form_inputs(
            stock_code,
            start_date,
            end_date,
            int(window_size) if window_size is not None else None,
        )
        if validation_errors:
            for error_message in validation_errors:
                st.error(error_message)
        else:
            for notice in notices:
                st.info(notice)
            with st.spinner("正在拉取行情并自动生成 K 线图..."):
                try:
                    result = api_post_json("/generate_and_predict", payload)
                    st.session_state["generate_result"] = result
                    st.session_state["generate_backtest_result"] = None
                    st.session_state["generate_backtest_error"] = None
                    remember_record(int(result["record"]["id"]))
                    backtest_result, backtest_error = fetch_backtest_result(int(result["record"]["id"]))
                    st.session_state["generate_backtest_result"] = backtest_result
                    st.session_state["generate_backtest_error"] = backtest_error
                except Exception as exc:
                    st.error(f"生成识别失败：{exc}")

    result = st.session_state.get("generate_result")
    if not result:
        render_placeholder("识别结果", "提交参数后，这里会展示自动生成的 K 线图、识别结果卡片和回测分析摘要")
        return

    generation = result["generation"]
    image_col, result_col = st.columns([1.08, 1.0])
    with image_col:
        if generation.get("image_url"):
            render_fixed_image_preview(generation["image_url"], "自动生成的 K 线图")
        else:
            render_placeholder("生成图像", "当前记录暂未返回可访问的图像地址")
    with result_col:
        render_prediction_result_card(
            result,
            title="识别结果",
            subtitle="展示模型预测结果信息",
        )

    backtest_result = st.session_state.get("generate_backtest_result")
    backtest_error = st.session_state.get("generate_backtest_error")
    if backtest_result:
        render_backtest_visual(
            backtest_result,
            title="基于当前股票信息的回测结果",
            image_url=generation.get("image_url"),
        )
    elif backtest_error:
        st.info(f"自动回测暂未完成：{backtest_error}")
