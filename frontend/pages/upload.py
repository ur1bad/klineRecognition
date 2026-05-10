from __future__ import annotations

import streamlit as st

from frontend.shared import (
    api_post_multipart,
    build_panel_header,
    fetch_backtest_result,
    record_can_backtest,
    remember_record,
    render_backtest_visual,
    render_fixed_image_preview,
    render_page_banner,
    render_placeholder,
    render_prediction_result_card,
    uploaded_file_to_data_uri,
    validate_upload_date_inputs,
)


def render_upload_page() -> None:
    render_page_banner(
        "上传K线图识别",
        "上传本地 K 线图图片，系统会返回识别类别、置信度与可用于后续回测的记录信息",
        [],
    )

    form_col, info_col = st.columns([1.18, 0.92])
    with form_col:
        with st.container(key="upload-params-panel"):
            st.markdown(
                build_panel_header("上传参数面板", "上传图片与填写可选的行情辅助字段，便于后续回测"),
                unsafe_allow_html=True,
            )
            upload = st.file_uploader(
                "上传 K 线图图片",
                type=["png", "jpg", "jpeg", "bmp"],
                key="upload_page_file",
            )
            stock_code = st.text_input("股票代码（可选）", value="", placeholder="示例：600519", key="upload_stock_code")
            start_date = st.text_input("开始日期（可选）", value="", placeholder="示例：2024-01-01", key="upload_start_date")
            end_date = st.text_input("结束日期（可选）", value="", placeholder="示例：2024-06-30", key="upload_end_date")
            window_size = st.number_input(
                "窗口大小（可选）",
                min_value=20,
                max_value=240,
                value=None,
                step=1,
                placeholder="示例：30",
                key="upload_window_size",
            )
            submitted = st.button("开始识别", type="primary", use_container_width=True, key="upload_predict_submit")

    with info_col:
        st.markdown(
            f"""
            <div class="content-card">
                {build_panel_header("操作说明", "", "使用说明")}
                <div class="tip-list">
                    <div class="tip-item">
                        <strong>上传K线图</strong>
                        <span>上传本地已生成的K线图，作为系统的图像输入</span>
                    </div>
                    <div class="tip-item">
                        <strong>补充行情字段</strong>
                        <span>若填写股票代码、窗口大小与日期区间，识别完成后可进一步展示回测验证结果</span>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if upload is not None:
            render_fixed_image_preview(uploaded_file_to_data_uri(upload), "待识别图片预览")
        else:
            render_placeholder("图片预览区", "上传图片后，这里会显示待识别的 K 线图预览")

    if submitted:
        if upload is None:
            st.error("请先上传一张 K 线图。")
        else:
            (
                resolved_start_date,
                resolved_end_date,
                resolved_window_size,
                validation_errors,
                notices,
            ) = validate_upload_date_inputs(
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
                with st.spinner("正在调用后端完成图片识别..."):
                    try:
                        files = {"file": (upload.name, upload.getvalue(), upload.type or "image/png")}
                        data = {
                            "stock_code": stock_code.strip(),
                            "start_date": resolved_start_date,
                            "end_date": resolved_end_date,
                        }
                        if resolved_window_size is not None:
                            data["window_size"] = int(resolved_window_size)
                        result = api_post_multipart("/predict_image", files=files, data=data)
                        st.session_state["upload_result"] = result
                        st.session_state["upload_backtest_result"] = None
                        st.session_state["upload_backtest_error"] = None
                        remember_record(int(result["record"]["id"]))
                        if record_can_backtest(result["record"]):
                            backtest_result, backtest_error = fetch_backtest_result(int(result["record"]["id"]))
                            st.session_state["upload_backtest_result"] = backtest_result
                            st.session_state["upload_backtest_error"] = backtest_error
                    except Exception as exc:
                        st.error(f"识别失败：{exc}")

    result = st.session_state.get("upload_result")
    if not result:
        render_placeholder("识别结果区域", "提交识别任务后，这里会显示结果卡片、识别说明以及可选的回测验证摘要")
        return

    image_col, result_col = st.columns([1.0, 1.02])
    with image_col:
        if result["record"].get("image_url"):
            render_fixed_image_preview(result["record"]["image_url"], "识别图像")
        else:
            render_placeholder("识别图像", "当前记录暂未返回可访问的图像地址")
    with result_col:
        render_prediction_result_card(
            result,
            title="识别结果",
            subtitle="展示模型预测结果信息",
        )

    backtest_result = st.session_state.get("upload_backtest_result")
    backtest_error = st.session_state.get("upload_backtest_error")
    if backtest_result:
        render_backtest_visual(
            backtest_result,
            title="基于当前上传记录的直接回测",
            image_url=result["record"].get("image_url"),
        )
    elif backtest_error:
        st.info(f"当前记录暂未完成自动回测：{backtest_error}")
