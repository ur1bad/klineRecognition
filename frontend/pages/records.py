from __future__ import annotations

import streamlit as st

from frontend.shared import (
    DEFAULT_BACKTEST_HORIZON,
    api_delete,
    PATTERN_OPTIONS,
    api_get,
    build_panel_header,
    format_datetime_text,
    load_records_payload,
    normalize_pattern_label,
    parse_optional_nonnegative_int_input,
    record_can_backtest,
    remember_record,
    render_fixed_image_preview,
    render_history_records_table,
    render_page_banner,
    render_placeholder,
    render_record_detail_card,
    render_stat_card,
    set_page,
)


def _clear_deleted_record_state(record_id: int) -> None:
    for key in [
        "history_detail_select",
        f"history_delete_confirm_{record_id}",
    ]:
        st.session_state.pop(key, None)

    if st.session_state.get("selected_backtest_record_id") == record_id:
        st.session_state.pop("selected_backtest_record_id", None)
        st.session_state.pop("backtest_record_select", None)

    backtest_key = st.session_state.get("backtest_result_key")
    if isinstance(backtest_key, tuple) and backtest_key and int(backtest_key[0]) == record_id:
        st.session_state.pop("backtest_result", None)
        st.session_state.pop("backtest_result_key", None)

    for result_key, backtest_result_key, backtest_error_key in [
        ("upload_result", "upload_backtest_result", "upload_backtest_error"),
        ("generate_result", "generate_backtest_result", "generate_backtest_error"),
    ]:
        result = st.session_state.get(result_key)
        if isinstance(result, dict) and int(result.get("record", {}).get("id", 0)) == record_id:
            st.session_state.pop(result_key, None)
            st.session_state.pop(backtest_result_key, None)
            st.session_state.pop(backtest_error_key, None)


def _render_delete_record_panel(detail: dict[str, object]) -> None:
    record_id = int(detail["id"])
    confirm_key = f"history_delete_confirm_{record_id}"

    with st.container(key="history-delete-panel"):
        st.markdown(
            build_panel_header("删除记录", "删除后将从历史列表中移除，并清理系统保存的关联图像", "谨慎操作"),
            unsafe_allow_html=True,
        )
        confirmed = st.checkbox(
            f"确认删除记录 #{record_id}",
            key=confirm_key,
        )
        delete_clicked = st.button(
            "删除该记录",
            key=f"history_delete_record_button_{record_id}",
            disabled=not confirmed,
            use_container_width=True,
        )

    if not delete_clicked:
        return

    with st.spinner("正在删除识别记录..."):
        try:
            api_delete(f"/record/{record_id}")
        except Exception as exc:
            st.error(f"删除失败：{exc}")
            return

    _clear_deleted_record_state(record_id)
    st.session_state["history_delete_notice"] = f"记录 #{record_id} 已删除"
    st.rerun()


def render_history_page() -> None:
    render_page_banner(
        "历史识别记录",
        "支持按股票代码与识别类别筛选结果，并可查看单条记录详情",
        [],
    )
    delete_notice = st.session_state.pop("history_delete_notice", None)
    if delete_notice:
        st.toast(delete_notice, icon=":material/check_circle:", duration=2)

    with st.container(key="history-filter-panel"):
        st.markdown(
            build_panel_header("查询筛选区域", "", "记录检索"),
            unsafe_allow_html=True,
        )

        history_pattern_options = [("全部", "")] + [(label, label) for label in PATTERN_OPTIONS if label]
        filter_col1, filter_col2, filter_col3 = st.columns(3)
        with filter_col1:
            stock_code = st.text_input("按股票代码筛选", value="", placeholder="示例：600519")
        with filter_col2:
            predicted_label_option = st.selectbox(
                "按识别类型筛选",
                options=history_pattern_options,
                index=0,
                format_func=lambda option: option[0],
            )
        with filter_col3:
            limit_text = st.text_input(
                "返回条数",
                value="",
                placeholder="全部",
                key="history_limit_text",
            )
    predicted_label = predicted_label_option[1]
    limit, limit_error = parse_optional_nonnegative_int_input(limit_text, "返回条数")

    if limit_error:
        st.error(limit_error)
        return

    if limit is not None:
        result, error = load_records_payload(limit=int(limit), stock_code=stock_code, predicted_label=predicted_label)
    else:
        preview_result, error = load_records_payload(limit=1, stock_code=stock_code, predicted_label=predicted_label)
        if error:
            st.error(f"获取记录失败：{error}")
            return
        query_limit = max(int(preview_result.get("total", 0)), 1)
        result, error = load_records_payload(limit=query_limit, stock_code=stock_code, predicted_label=predicted_label)
    if error:
        st.error(f"获取记录失败：{error}")
        return

    items = result["items"]
    avg_confidence = 0.0
    if items:
        avg_confidence = sum(float(item.get("confidence", 0.0)) for item in items) / len(items)

    metric_col1, metric_col2, metric_col3 = st.columns(3)
    with metric_col1:
        render_stat_card("记录总数", str(result["total"]), "当前筛选条件下的记录总量", "emerald", compact=True)
    with metric_col2:
        render_stat_card("当前列表条数", str(len(items)), "本次列表实际返回的记录数量", "forest", compact=True)
    with metric_col3:
        render_stat_card(
            "平均置信度",
            f"{avg_confidence:.2%}" if items else "0.00%",
            "当前结果集合的平均置信度",
            "sage",
            compact=True,
        )

    render_history_records_table(items)
    if not items:
        return

    option_map = {
        f"#{item['id']} | {item.get('stock_code') or '无代码'} | {normalize_pattern_label(item.get('predicted_label'))} | {format_datetime_text(item.get('created_at'))}": item
        for item in items
    }
    with st.container(key="history-detail-panel"):
        st.markdown(
            build_panel_header("记录详情查看", "选择一条记录查看详情信息", "详情查看"),
            unsafe_allow_html=True,
        )
        detail_placeholder = "请选择一条记录"
        detail_options = [detail_placeholder] + list(option_map.keys())
        if st.session_state.get("history_detail_select") not in detail_options:
            st.session_state["history_detail_select"] = detail_placeholder
        selected_label = st.selectbox(
            "选择一条记录查看详情",
            options=detail_options,
            key="history_detail_select",
        )
    if selected_label == detail_placeholder:
        render_placeholder("记录详情预览", "选择一条历史识别记录后，这里会显示对应图像与详情信息")
        return
    selected_record = option_map[selected_label]

    try:
        detail = api_get(f"/record/{int(selected_record['id'])}")
    except Exception as exc:
        st.error(f"获取记录详情失败：{exc}")
        return

    remember_record(int(detail["id"]))

    left, right = st.columns([1.05, 1.0])
    with left:
        if detail.get("image_url"):
            render_fixed_image_preview(detail["image_url"], f"记录 #{detail['id']} 图像")
        else:
            render_placeholder("图像预览", "当前记录没有可展示的图像地址")
    with right:
        render_record_detail_card(detail)
        if record_can_backtest(detail):
            if st.button("进入回测分析页面", key="go_backtest_from_history", type="primary", use_container_width=True):
                remember_record(int(detail["id"]))
                st.session_state["backtest_autorun_request"] = True
                st.session_state["backtest_horizon_select"] = DEFAULT_BACKTEST_HORIZON
                set_page("backtest")
        else:
            st.info("该记录缺少股票代码、窗口大小或日期区间，暂不支持直接回测")
        _render_delete_record_panel(detail)
