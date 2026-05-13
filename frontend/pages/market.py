from __future__ import annotations

from html import escape
from typing import Any, Optional

import pandas as pd
import streamlit as st

from frontend.shared import (
    api_get,
    build_panel_header,
    render_page_banner,
    render_placeholder,
    render_stat_card,
)


BOARD_OPTIONS = ["全部", "沪市A股", "深市A股", "创业板", "科创板", "北交所"]
MARKET_TABLE_PAGE_SIZE = 10
SORT_OPTIONS = {
    "涨跌幅降序": ("涨跌幅(%)", False),
    "涨跌幅升序": ("涨跌幅(%)", True),
    "成交额降序": ("成交额(亿)", False),
    "换手率降序": ("换手率(%)", False),
    "最新价降序": ("最新价", False),
}


def render_market_page() -> None:
    _inject_market_css()
    render_page_banner(
        "行情中心",
        "聚合A股指数、市场涨跌分布、情绪评分和个股行情，为K线识别提供行情入口",
        ["实时行情", "市场热度", "个股排行"],
    )

    refresh_col, meta_col = st.columns([0.18, 0.82])
    with refresh_col:
        refresh_clicked = st.button("刷新行情", type="primary", use_container_width=True)

    with st.spinner("正在获取行情数据..."):
        payload, error = _load_market_payload(force_refresh=refresh_clicked)

    if error:
        render_placeholder("行情数据暂不可用", error)
        return

    with meta_col:
        st.markdown(
            f"""
            <div class="market-source-strip">
                <span>数据来源：{escape(str(payload.get("source") or "-"))}</span>
                <span>更新时间：{escape(_format_datetime(payload.get("updated_at")))}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    _render_index_section(payload.get("indices", []))
    _render_market_distribution(payload)
    _render_rank_section(payload)
    _render_stock_table(payload.get("stocks", []))


def _load_market_payload(*, force_refresh: bool = False) -> tuple[dict[str, Any], Optional[str]]:
    try:
        return api_get("/market/overview", params={"force_refresh": force_refresh}), None
    except Exception as exc:
        return {}, str(exc)


def _inject_market_css() -> None:
    st.markdown(
        """
        <style>
        .market-source-strip {
            min-height: 46px;
            display: flex;
            align-items: center;
            justify-content: flex-end;
            gap: 1rem;
            color: #6a7c92;
            font-size: 0.9rem;
        }
        .market-index-card {
            padding: 1rem 1.05rem;
            border: 1px solid #d8e3f1;
            border-radius: 18px;
            background: rgba(255,255,255,0.92);
            box-shadow: 0 12px 30px rgba(17, 49, 92, 0.08);
        }
        .market-index-name {
            color: #152c4a;
            font-size: 0.92rem;
            font-weight: 800;
            margin-bottom: 0.45rem;
        }
        .market-index-price {
            color: #152c4a;
            font-size: 1.42rem;
            line-height: 1.15;
            font-weight: 850;
        }
        .market-index-change,
        .market-rank-metric {
            margin-top: 0.35rem;
            font-size: 0.86rem;
            font-weight: 750;
        }
        .market-pos {
            color: #d84c3f;
        }
        .market-neg {
            color: #1f9d63;
        }
        .market-neutral {
            color: #6a7c92;
        }
        .market-score-card {
            min-height: 386px;
            padding: 1.05rem 1.1rem 1rem 1.1rem;
            border: 1px solid #d8e3f1;
            border-radius: 18px;
            background: rgba(255,255,255,0.94);
            box-shadow: 0 12px 30px rgba(17, 49, 92, 0.08);
        }
        .market-score-offset {
            height: 5.45rem;
        }
        .market-score-ring {
            width: 168px;
            height: 168px;
            border-radius: 50%;
            margin: 1rem auto 1.1rem auto;
            display: grid;
            place-items: center;
        }
        .market-score-inner {
            width: 124px;
            height: 124px;
            border-radius: 50%;
            background: #ffffff;
            display: grid;
            place-items: center;
            text-align: center;
            box-shadow: inset 0 0 0 1px #edf2f9;
        }
        .market-score-number {
            color: #152c4a;
            font-size: 2.2rem;
            font-weight: 900;
            line-height: 1;
        }
        .market-score-unit {
            color: #6a7c92;
            font-size: 0.82rem;
            margin-top: 0.2rem;
        }
        .market-advice {
            margin-top: 0.8rem;
            padding: 0.9rem;
            color: #39516e;
            background: #f4f7fc;
            border: 1px solid #e2ebf7;
            border-radius: 16px;
            line-height: 1.7;
        }
        .market-breadth-card {
            min-height: 386px;
            padding: 1.05rem 1.1rem 1rem 1.1rem;
            border: 1px solid #d8e3f1;
            border-radius: 18px;
            background: rgba(255,255,255,0.94);
            box-shadow: 0 12px 30px rgba(17, 49, 92, 0.08);
        }
        .market-breadth-grid {
            display: grid;
            grid-template-columns: repeat(12, minmax(0, 1fr));
            gap: 0.55rem;
            align-items: end;
            min-height: 292px;
            margin-top: 0.55rem;
        }
        .market-breadth-col {
            min-width: 0;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: flex-end;
            gap: 0.35rem;
        }
        .market-breadth-count {
            color: #152c4a;
            font-size: 0.78rem;
            font-weight: 850;
            min-height: 1.1rem;
        }
        .market-breadth-track {
            width: 100%;
            height: 210px;
            border-radius: 12px;
            background: #edf4fb;
            border: 1px solid #dfe9f6;
            display: flex;
            align-items: flex-end;
            overflow: hidden;
        }
        .market-breadth-bar {
            width: 100%;
            min-height: 5px;
            border-radius: 12px 12px 0 0;
            box-shadow: inset 0 1px 0 rgba(255,255,255,0.28);
        }
        .market-breadth-bar.up {
            background: linear-gradient(180deg, #e16456 0%, #d4483c 100%);
        }
        .market-breadth-bar.down {
            background: linear-gradient(180deg, #2aa36d 0%, #1f8c5e 100%);
        }
        .market-breadth-label {
            color: #61748a;
            font-size: 0.72rem;
            line-height: 1.15;
            text-align: center;
            white-space: nowrap;
        }
        .market-rank-card {
            padding: 1rem;
            border: 1px solid #d8e3f1;
            border-radius: 18px;
            background: rgba(255,255,255,0.92);
            box-shadow: 0 12px 30px rgba(17, 49, 92, 0.08);
        }
        .market-rank-title {
            color: #152c4a;
            font-size: 0.98rem;
            font-weight: 850;
            margin-bottom: 0.75rem;
        }
        .market-rank-row {
            display: grid;
            grid-template-columns: 1.6rem 1fr auto;
            align-items: center;
            gap: 0.55rem;
            padding: 0.54rem 0;
            border-top: 1px solid #edf2f9;
        }
        .market-rank-row:first-of-type {
            border-top: 0;
        }
        .market-rank-order {
            color: #6a7c92;
            font-size: 0.78rem;
            font-weight: 800;
        }
        .market-rank-name {
            min-width: 0;
        }
        .market-rank-name strong {
            display: block;
            color: #152c4a;
            font-size: 0.86rem;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .market-rank-name span {
            display: block;
            color: #6a7c92;
            font-size: 0.74rem;
            margin-top: 0.12rem;
        }
        .market-table-caption {
            margin: 0.3rem 0 0.5rem 0;
            color: #6a7c92;
            font-size: 0.86rem;
        }
        .market-table-name {
            color: #152c4a;
            font-weight: 750;
        }
        .market-table-number {
            font-variant-numeric: tabular-nums;
            white-space: nowrap;
        }
        .market-table-scroll-x {
            overflow-x: auto;
        }
        .market-pager-text {
            color: #152c4a;
            font-size: 0.9rem;
            font-weight: 700;
            white-space: nowrap;
        }
        .st-key-market-pager-panel {
            margin-top: 0.55rem;
            display: flex;
            justify-content: center;
        }
        .st-key-market-pager-panel > div {
            width: 100%;
            display: flex;
            justify-content: center;
        }
        .st-key-market-pager-panel [data-testid="stPills"] {
            margin-left: auto;
            margin-right: auto;
            display: flex;
            justify-content: center;
            width: fit-content;
        }
        .st-key-market-pager-panel button {
            min-height: 30px !important;
            height: 30px !important;
            padding: 0 0.52rem !important;
            border-radius: 7px !important;
            font-size: 0.86rem !important;
            font-weight: 700 !important;
            background: transparent !important;
            box-shadow: none !important;
            border-color: transparent !important;
        }
        .st-key-market-pager-panel button[aria-pressed="true"] {
            color: #d84c3f !important;
            background: rgba(255,255,255,0.42) !important;
            border-color: rgba(216, 227, 241, 0.72) !important;
        }
        .market-pager-form {
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 0.18rem;
            flex-wrap: wrap;
        }
        .market-pager-form a,
        .market-pager-form span.page-link {
            min-width: 30px;
            height: 30px;
            padding: 0 0.52rem;
            border: 1px solid transparent;
            border-radius: 7px;
            background: transparent;
            color: #39516e;
            font-size: 0.86rem;
            font-weight: 700;
            text-decoration: none;
            display: inline-flex;
            align-items: center;
            justify-content: center;
        }
        .market-pager-form a:hover {
            color: #d84c3f;
            background: #edf4fb;
            border-color: #d8e3f1;
        }
        .market-pager-form .current {
            color: #d84c3f;
            background: #f2f5f9;
            border-color: #e0e7f0;
            cursor: default;
        }
        .market-pager-form .nav {
            min-width: 54px;
        }
        .market-pager-form .market-pager-text {
            margin-left: 0.28rem;
            padding: 0 0.25rem;
            line-height: 30px;
        }
        .st-key-market-filter-panel label,
        .st-key-market-filter-panel label p,
        .st-key-market-filter-panel [data-testid="stWidgetLabel"],
        .st-key-market-filter-panel [data-testid="stWidgetLabel"] p {
            color: #294f80 !important;
            font-weight: 700 !important;
        }
        .st-key-market-filter-panel div[data-baseweb="select"] > div {
            min-height: 40px !important;
            border: 2px solid #284972 !important;
            border-radius: 14px !important;
            background: #ffffff !important;
            color: #152c4a !important;
            box-shadow: none !important;
        }
        .st-key-market-filter-panel div[data-baseweb="select"] > div {
            padding-left: 0.42rem !important;
            padding-right: 0.68rem !important;
            align-items: center !important;
        }
        .st-key-market-filter-panel .stTextInput div[data-baseweb="input"] > div {
            min-height: 40px !important;
            border: 1px solid #d5e2f1 !important;
            border-radius: 14px !important;
            background: #f8fbff !important;
            color: #152c4a !important;
            box-shadow: none !important;
            padding-right: 0.85rem !important;
            box-sizing: border-box !important;
        }
        .st-key-market-filter-panel div[data-baseweb="select"] span,
        .st-key-market-filter-panel div[data-baseweb="select"] div,
        .st-key-market-filter-panel .stTextInput input {
            color: #152c4a !important;
            font-size: 0.92rem !important;
            line-height: 1.35 !important;
        }
        .st-key-market-filter-panel .stTextInput input {
            padding-right: 1rem !important;
            background: transparent !important;
            box-sizing: border-box !important;
        }
        .st-key-market-filter-panel .stTextInput input::placeholder {
            color: #7f91a7 !important;
            opacity: 1 !important;
        }
        .st-key-market-filter-panel div[data-baseweb="select"] > div:focus-within {
            border-color: #2d67b7 !important;
            box-shadow: 0 0 0 3px rgba(45, 103, 183, 0.16) !important;
        }
        .st-key-market-filter-panel .stTextInput div[data-baseweb="input"] > div:focus-within {
            border-color: #8eb2e0 !important;
            box-shadow: 0 0 0 3px rgba(45, 103, 183, 0.10) !important;
        }
        @media (max-width: 900px) {
            .market-source-strip {
                justify-content: flex-start;
                flex-direction: column;
                align-items: flex-start;
                gap: 0.25rem;
            }
            .market-breadth-grid {
                grid-template-columns: repeat(6, minmax(0, 1fr));
            }
            .market-score-offset {
                height: 0;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_index_section(indices: list[dict[str, Any]]) -> None:
    st.markdown(
        build_panel_header("大盘指数概览", "展示主要A股指数最新点位和涨跌情况", "指数行情"),
        unsafe_allow_html=True,
    )
    if not indices:
        render_placeholder("暂无指数数据", "当前未获取到指数行情，可稍后刷新。")
        return

    columns = st.columns(min(4, len(indices)))
    for column, item in zip(columns, indices):
        with column:
            change_percent = item.get("change_percent")
            change_amount = item.get("change_amount")
            class_name = _signed_class(change_percent)
            st.markdown(
                f"""
                <div class="market-index-card">
                    <div class="market-index-name">{escape(str(item.get("name") or "-"))}({escape(str(item.get("code") or ""))})</div>
                    <div class="market-index-price">{escape(_format_number(item.get("latest_price")))}</div>
                    <div class="market-index-change {class_name}">
                        {escape(_format_signed(change_percent, suffix="%"))}
                        <span>{escape(_format_signed(change_amount))}</span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def _render_market_distribution(payload: dict[str, Any]) -> None:
    breadth = payload.get("breadth", {})
    sentiment = payload.get("sentiment", {})
    metric_col1, metric_col2, metric_col3, metric_col4, metric_col5 = st.columns(5)
    with metric_col1:
        render_stat_card("上涨家数", str(breadth.get("up", 0)), "当前涨幅大于0的股票数量", "emerald", compact=True)
    with metric_col2:
        render_stat_card("下跌家数", str(breadth.get("down", 0)), "当前涨幅小于0的股票数量", "forest", compact=True)
    with metric_col3:
        render_stat_card("平盘家数", str(breadth.get("flat", 0)), "当前涨跌幅为0的股票数量", "sage", compact=True)
    with metric_col4:
        render_stat_card("涨停家数", str(breadth.get("limit_up", 0)), "涨幅接近或达到涨停的股票数量", "mint", compact=True)
    with metric_col5:
        render_stat_card("跌停家数", str(breadth.get("limit_down", 0)), "跌幅接近或达到跌停的股票数量", "sage", compact=True)

    chart_col, score_col = st.columns([1.55, 0.75])
    with chart_col:
        st.markdown(
            build_panel_header("市场涨跌分布", "按涨跌幅区间统计A股市场整体分布", "涨跌分布"),
            unsafe_allow_html=True,
        )
        bucket_df = pd.DataFrame(breadth.get("buckets", []))
        if bucket_df.empty:
            render_placeholder("暂无分布数据", "当前未获取到有效的涨跌幅数据。")
        else:
            st.markdown(_build_breadth_distribution_html(bucket_df), unsafe_allow_html=True)

    with score_col:
        score = float(sentiment.get("score", 5.0))
        level = str(sentiment.get("level") or "-")
        advice = str(sentiment.get("advice") or "-")
        score_color = "#2a68b5" if score >= 6 else "#d9852b" if score >= 4 else "#b24b4b"
        score_percent = max(0.0, min(100.0, score * 10.0))
        st.markdown("<div class='market-score-offset'></div>", unsafe_allow_html=True)
        st.markdown(
            "<div class='market-score-card'>"
            + build_panel_header("大盘情绪评分", "基于指数趋势、上涨家数、强弱分布和涨跌停综合计算", level)
            + f"<div class='market-score-ring' style='background: conic-gradient({score_color} 0 {score_percent:.1f}%, #edf2f9 {score_percent:.1f}% 100%);'>"
            + "<div class='market-score-inner'><div>"
            + f"<div class='market-score-number'>{score:.1f}</div>"
            + "<div class='market-score-unit'>分 / 10分</div>"
            + "</div></div></div>"
            + f"<div class='market-advice'>{escape(advice)}</div>"
            + "</div>",
            unsafe_allow_html=True,
        )


def _render_rank_section(payload: dict[str, Any]) -> None:
    st.markdown(
        build_panel_header("热门榜单", "快速查看涨幅、跌幅、成交额和换手率靠前的个股", "个股排行"),
        unsafe_allow_html=True,
    )
    rank_col1, rank_col2, rank_col3, rank_col4 = st.columns(4)
    with rank_col1:
        _render_rank_card("涨幅榜", payload.get("top_gainers", []), "change_percent", "%")
    with rank_col2:
        _render_rank_card("跌幅榜", payload.get("top_losers", []), "change_percent", "%")
    with rank_col3:
        _render_rank_card("成交额榜", payload.get("top_amount", []), "amount", "")
    with rank_col4:
        metric = str(payload.get("top_turnover_metric") or "turnover_rate")
        title = str(payload.get("top_turnover_title") or "换手率榜")
        suffix = "%" if metric == "turnover_rate" else ""
        _render_rank_card(title, payload.get("top_turnover", []), metric, suffix)


def _render_rank_card(title: str, rows: list[dict[str, Any]], field: str, suffix: str) -> None:
    row_html: list[str] = []
    for index, item in enumerate(rows[:8], start=1):
        value = item.get(field)
        if field == "amount":
            metric = _format_amount(value)
            class_name = "market-neutral"
        elif field == "volume":
            metric = _format_volume(value)
            class_name = "market-neutral"
        else:
            metric = _format_signed(value, suffix=suffix)
            class_name = _signed_class(value)
        row_html.append(
            "<div class='market-rank-row'>"
            f"<div class='market-rank-order'>{index}</div>"
            "<div class='market-rank-name'>"
            f"<strong>{escape(str(item.get('name') or '-'))}</strong>"
            f"<span>{escape(str(item.get('code') or '-'))} · {escape(str(item.get('board') or '-'))}</span>"
            "</div>"
            f"<div class='market-rank-metric {class_name}'>{escape(metric)}</div>"
            "</div>"
        )

    if not row_html:
        row_html.append("<div class='market-rank-row'><div></div><div class='market-rank-name'><strong>暂无数据</strong></div><div></div></div>")

    st.markdown(
        "<div class='market-rank-card'>"
        f"<div class='market-rank-title'>{escape(title)}</div>"
        + "".join(row_html)
        + "</div>",
        unsafe_allow_html=True,
    )


def _render_stock_table(stocks: list[dict[str, Any]]) -> None:
    st.markdown(
        build_panel_header("个股行情", "支持按板块、代码或名称筛选，并按关键指标排序", "行情列表"),
        unsafe_allow_html=True,
    )
    dataframe = _build_stock_dataframe(stocks)
    if dataframe.empty:
        render_placeholder("暂无个股行情", "当前未获取到个股行情数据。")
        return

    with st.container(key="market-filter-panel"):
        filter_col1, filter_col2, filter_col3 = st.columns([0.85, 1.1, 0.9])
        with filter_col1:
            board = st.selectbox("板块筛选", BOARD_OPTIONS, key="market_board_filter")
        with filter_col2:
            keyword = st.text_input("代码或名称搜索", value="", placeholder="示例：600519 或 贵州茅台", key="market_keyword")
        with filter_col3:
            sort_name = st.selectbox("排序方式", list(SORT_OPTIONS.keys()), key="market_sort_select")

    filter_signature = (board, keyword.strip(), sort_name)
    filter_changed = st.session_state.get("market_filter_signature") != filter_signature
    if filter_changed:
        st.session_state["market_filter_signature"] = filter_signature
        st.session_state["market_current_page"] = 1

    filtered = dataframe.copy()
    if board != "全部":
        filtered = filtered[filtered["板块"] == board]
    keyword_text = keyword.strip()
    if keyword_text:
        mask = (
            filtered["代码"].astype(str).str.contains(keyword_text, case=False, na=False)
            | filtered["名称"].astype(str).str.contains(keyword_text, case=False, na=False)
        )
        filtered = filtered[mask]

    sort_column, ascending = SORT_OPTIONS[sort_name]
    filtered = filtered.sort_values(sort_column, ascending=ascending, na_position="last")

    total_rows = len(filtered)
    total_pages = max((total_rows + MARKET_TABLE_PAGE_SIZE - 1) // MARKET_TABLE_PAGE_SIZE, 1)
    current_page = int(st.session_state.get("market_current_page", 1))
    if current_page > total_pages:
        current_page = total_pages
    if current_page < 1:
        current_page = 1
    st.session_state["market_current_page"] = current_page

    start_index = (current_page - 1) * MARKET_TABLE_PAGE_SIZE
    end_index = start_index + MARKET_TABLE_PAGE_SIZE
    display_df = filtered.iloc[start_index:end_index]

    st.markdown(
        f"<div class='market-table-caption'>当前匹配 {total_rows} 条，每页固定显示 {MARKET_TABLE_PAGE_SIZE} 条，当前为第 {current_page} / {total_pages} 页。</div>",
        unsafe_allow_html=True,
    )
    st.markdown(_build_market_table_html(display_df, start_index=start_index), unsafe_allow_html=True)
    _render_market_pagination(current_page, total_pages)


def _render_market_pagination(current_page: int, total_pages: int) -> None:
    if total_pages <= 1:
        return

    if total_pages <= 5:
        page_numbers = list(range(1, total_pages + 1))
    else:
        start_page = max(1, min(current_page - 2, total_pages - 4))
        page_numbers = list(range(start_page, start_page + 5))

    options: list[str] = []
    if current_page > 1:
        options.extend(["首页", "上一页"])
    options.extend(str(page_number) for page_number in page_numbers)
    if current_page < total_pages:
        options.extend(["下一页", "尾页"])
    options.append(f"{current_page}/{total_pages}")

    pager_key = f"market_pager_select_{current_page}_{total_pages}"
    with st.container(key="market-pager-panel"):
        st.pills(
            "个股行情分页",
            options=options,
            default=str(current_page),
            key=pager_key,
            label_visibility="collapsed",
            width="content",
            on_change=_update_market_page_from_pager,
            args=(current_page, total_pages, pager_key),
        )


def _update_market_page_from_pager(current_page: int, total_pages: int, pager_key: str) -> None:
    selected = st.session_state.get(pager_key)
    target_page: Optional[int] = None
    if selected == "首页":
        target_page = 1
    elif selected == "上一页":
        target_page = current_page - 1
    elif selected == "下一页":
        target_page = current_page + 1
    elif selected == "尾页":
        target_page = total_pages
    elif selected and str(selected).isdigit():
        target_page = int(str(selected))

    if target_page is not None:
        target_page = max(1, min(total_pages, target_page))
        if target_page != current_page:
            st.session_state["market_current_page"] = target_page


def _build_breadth_distribution_html(bucket_df: pd.DataFrame) -> str:
    max_count = max(int(bucket_df["count"].max()), 1)
    columns: list[str] = []
    for _, row in bucket_df.iterrows():
        count = int(row.get("count") or 0)
        height = max(3.0, count / max_count * 100.0) if count else 0.0
        tone = "up" if str(row.get("tone")) == "up" else "down"
        columns.append(
            "<div class='market-breadth-col'>"
            f"<div class='market-breadth-count'>{count}</div>"
            "<div class='market-breadth-track'>"
            f"<div class='market-breadth-bar {tone}' style='height:{height:.1f}%;'></div>"
            "</div>"
            f"<div class='market-breadth-label'>{escape(str(row.get('label') or '-'))}</div>"
            "</div>"
        )
    return "<div class='market-breadth-card'><div class='market-breadth-grid'>" + "".join(columns) + "</div></div>"


def _build_market_table_html(dataframe: pd.DataFrame, *, start_index: int = 0) -> str:
    headers = ["序号", "代码", "名称", "板块", "最新价", "涨跌幅", "涨跌额", "换手率", "振幅", "成交额", "成交量", "市盈率"]
    rows: list[str] = []
    for row_number, (_, row) in enumerate(dataframe.iterrows(), start=start_index + 1):
        change_value = row.get("涨跌幅(%)")
        change_class = _signed_class(change_value)
        rows.append(
            "<tr>"
            f"<td><span class='market-table-number'>{row_number}</span></td>"
            f"<td><span class='record-id'>{escape(str(row.get('代码') or '-'))}</span></td>"
            f"<td><span class='market-table-name'>{escape(str(row.get('名称') or '-'))}</span></td>"
            f"<td><span class='record-badge'>{escape(str(row.get('板块') or '-'))}</span></td>"
            f"<td><span class='market-table-number'>{escape(_format_number(row.get('最新价')))}</span></td>"
            f"<td><span class='market-table-number {change_class}'>{escape(_format_signed(change_value, suffix='%'))}</span></td>"
            f"<td><span class='market-table-number {change_class}'>{escape(_format_signed(row.get('涨跌额')))}</span></td>"
            f"<td><span class='market-table-number'>{escape(_format_optional_unit(row.get('换手率(%)'), '%'))}</span></td>"
            f"<td><span class='market-table-number'>{escape(_format_optional_unit(row.get('振幅(%)'), '%'))}</span></td>"
            f"<td><span class='market-table-number'>{escape(_format_optional_unit(row.get('成交额(亿)'), '亿'))}</span></td>"
            f"<td><span class='market-table-number'>{escape(_format_optional_unit(row.get('成交量(万手)'), '万手'))}</span></td>"
            f"<td><span class='market-table-number'>{escape(_format_number(row.get('市盈率')))}</span></td>"
            "</tr>"
        )

    header_html = "".join(f"<th>{escape(header)}</th>" for header in headers)
    body_html = "".join(rows) or "<tr><td colspan='12'>暂无匹配数据</td></tr>"
    return (
        "<div class='content-card'>"
        "<div class='record-table-wrap'>"
        "<div class='market-table-scroll-x'>"
        "<table class='record-table'>"
        f"<thead><tr>{header_html}</tr></thead>"
        f"<tbody>{body_html}</tbody>"
        "</table></div></div></div>"
    )


def _build_stock_dataframe(stocks: list[dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for item in stocks:
        rows.append(
            {
                "代码": str(item.get("code") or ""),
                "名称": str(item.get("name") or ""),
                "板块": str(item.get("board") or ""),
                "最新价": _to_float(item.get("latest_price")),
                "涨跌幅(%)": _to_float(item.get("change_percent")),
                "涨跌额": _to_float(item.get("change_amount")),
                "换手率(%)": _to_float(item.get("turnover_rate")),
                "振幅(%)": _to_float(item.get("amplitude")),
                "成交额(亿)": _divide(item.get("amount"), 100000000),
                "成交量(万手)": _divide(item.get("volume"), 10000),
                "市盈率": _to_float(item.get("pe_dynamic")),
            }
        )
    return pd.DataFrame(rows)


def _signed_class(value: Any) -> str:
    number = _to_float(value)
    if number is None or number == 0:
        return "market-neutral"
    return "market-pos" if number > 0 else "market-neg"


def _format_signed(value: Any, *, suffix: str = "") -> str:
    number = _to_float(value)
    if number is None:
        return "-"
    sign = "+" if number > 0 else ""
    return f"{sign}{number:.2f}{suffix}"


def _format_number(value: Any) -> str:
    number = _to_float(value)
    if number is None:
        return "-"
    return f"{number:.2f}"


def _format_amount(value: Any) -> str:
    number = _to_float(value)
    if number is None:
        return "-"
    if abs(number) >= 100000000:
        return f"{number / 100000000:.2f}亿"
    if abs(number) >= 10000:
        return f"{number / 10000:.2f}万"
    return f"{number:.2f}"


def _format_volume(value: Any) -> str:
    number = _to_float(value)
    if number is None:
        return "-"
    if abs(number) >= 100000000:
        return f"{number / 100000000:.2f}亿手"
    if abs(number) >= 10000:
        return f"{number / 10000:.2f}万手"
    return f"{number:.2f}手"


def _format_optional_unit(value: Any, unit: str) -> str:
    number = _to_float(value)
    if number is None:
        return "-"
    return f"{number:.2f}{unit}"


def _format_datetime(value: Any) -> str:
    timestamp = pd.to_datetime(value, errors="coerce")
    if pd.isna(timestamp):
        return str(value or "-")
    return timestamp.strftime("%Y-%m-%d %H:%M:%S")


def _divide(value: Any, divisor: float) -> Optional[float]:
    number = _to_float(value)
    if number is None:
        return None
    return round(number / divisor, 4)


def _to_float(value: Any) -> Optional[float]:
    try:
        if value is None or pd.isna(value):
            return None
        return float(value)
    except Exception:
        return None
