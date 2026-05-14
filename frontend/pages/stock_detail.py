from __future__ import annotations

from html import escape
from typing import Any, Optional

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from frontend.shared import (
    api_get,
    build_panel_header,
    render_page_banner,
    render_placeholder,
    render_stat_card,
)


UP_COLOR = "#e04b3f"
DOWN_COLOR = "#169a62"
PRICE_COLOR = "#1f5f96"
TEXT_COLOR = "#152c4a"
SECONDARY_TEXT_COLOR = "#314256"
KLINE_HISTORY_DAYS = 520
MA_COLORS = {
    "ma5": "#2b70b8",
    "ma10": "#f2a541",
    "ma30": "#8e5bb7",
}
PLOTLY_CONFIG = {
    "scrollZoom": True,
    "displayModeBar": True,
    "responsive": True,
    "modeBarButtonsToRemove": ["select2d", "lasso2d"],
}


def render_stock_detail_page() -> None:
    _inject_stock_detail_css()

    stock_code = _get_query_param("stock_code")
    if not stock_code:
        render_page_banner("股票详情", "缺少股票代码，无法加载个股详情。", ["行情中心"])
        render_placeholder("未选择股票", "请从行情中心的个股行情列表点击股票代码或名称进入详情页。")
        _render_back_to_market_button()
        return

    control_col, action_col = st.columns([0.28, 0.72])
    with control_col:
        _render_back_to_market_button()
    with action_col:
        refresh_clicked = st.button("刷新详情", type="primary", key=f"stock_detail_refresh_{stock_code}")

    with st.spinner("正在加载股票详情..."):
        payload, error = _load_stock_detail(stock_code, force_refresh=refresh_clicked)

    if error:
        render_page_banner("股票详情", f"股票 {stock_code} 详情暂不可用", ["行情中心", stock_code])
        render_placeholder("股票详情加载失败", error)
        return

    stock = payload.get("stock") or {}
    history = list(payload.get("history") or [])
    minute = list(payload.get("minute") or [])
    name = str(stock.get("name") or stock_code)
    render_page_banner(
        f"{name}（{stock_code}）",
        "查看单只股票的实时行情、关键指标与走势结构",
        [str(stock.get("board") or "-"), str(stock.get("market") or "-")],
    )

    st.markdown(
        f"""
        <div class="market-source-strip stock-detail-source">
            <span>实时数据：{escape(str(payload.get("source") or "-"))}</span>
            <span>分时数据：{escape(str(payload.get("minute_source") or "-"))}</span>
            <span>K线数据：{escape(str(payload.get("history_source") or "-"))}</span>
            <span>更新时间：{escape(_format_datetime(payload.get("updated_at")))}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    _render_metric_row(stock)
    _render_market_chart(stock, history, minute)
    _render_detail_sections(stock, history)


def _load_stock_detail(stock_code: str, *, force_refresh: bool) -> tuple[dict[str, Any], Optional[str]]:
    try:
        return (
            api_get(
                f"/market/stock/{stock_code}",
                params={
                    "force_refresh": bool(force_refresh),
                },
            ),
            None,
        )
    except Exception as exc:
        return {}, str(exc)


def _render_metric_row(stock: dict[str, Any]) -> None:
    change_percent = stock.get("change_percent")
    change_amount = stock.get("change_amount")
    metric_col1, metric_col2, metric_col3, metric_col4, metric_col5 = st.columns(5)
    with metric_col1:
        render_stat_card("最新价", _format_number(stock.get("latest_price")), "当前实时行情最新成交价", "emerald", compact=True)
    with metric_col2:
        render_stat_card("涨跌幅", _format_signed(change_percent, suffix="%"), f"涨跌额 {_format_signed(change_amount)}", "forest", compact=True)
    with metric_col3:
        render_stat_card("振幅", _format_optional_unit(stock.get("amplitude"), "%"), "当日最高价与最低价波动幅度", "mint", compact=True)
    with metric_col4:
        render_stat_card("换手率", _format_optional_unit(stock.get("turnover_rate"), "%"), "当日换手活跃度", "sage", compact=True)
    with metric_col5:
        render_stat_card("成交额", _format_amount(stock.get("amount")), "当日累计成交额", "sage", compact=True)


def _render_market_chart(stock: dict[str, Any], history: list[dict[str, Any]], minute: list[dict[str, Any]]) -> None:
    st.markdown(
        "<div class='content-card stock-detail-chart-card'>"
        + build_panel_header("行情图表", "分时与K线指标视图", "图表")
        + "</div>",
        unsafe_allow_html=True,
    )

    intraday_tab, daily_tab, weekly_tab, monthly_tab = st.tabs(["分时图", "日K线", "周K线", "月K线"])
    with intraday_tab:
        _render_intraday_chart(stock, minute)
    with daily_tab:
        _render_kline_chart(history, "D", "日K线", "stock_detail_daily_kline")
    with weekly_tab:
        _render_kline_chart(history, "W", "周K线", "stock_detail_weekly_kline")
    with monthly_tab:
        _render_kline_chart(history, "M", "月K线", "stock_detail_monthly_kline")


def _render_intraday_chart(stock: dict[str, Any], minute: list[dict[str, Any]]) -> None:
    dataframe = _minute_dataframe(minute)
    if dataframe.empty:
        render_placeholder("暂无分时数据", "当前未获取到可展示的分钟行情。")
        return

    dataframe = dataframe.copy()
    dataframe["time_label"] = dataframe["trade_time"].dt.strftime("%H:%M")
    x_values = dataframe["time_label"]
    tick_values = _intraday_tick_values(dataframe["time_label"].tolist())
    price_delta = dataframe["price"].diff().fillna(0)
    volume_colors = [UP_COLOR if value >= 0 else DOWN_COLOR for value in price_delta]

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.035,
        row_heights=[0.72, 0.28],
    )
    fig.add_trace(
        go.Scatter(
            x=x_values,
            y=dataframe["price"],
            mode="lines",
            name="分时",
            line=dict(color=PRICE_COLOR, width=2.4),
            hovertemplate="时间 %{x}<br>价格 %{y:.2f}<extra></extra>",
        ),
        row=1,
        col=1,
    )
    if "average_price" in dataframe and dataframe["average_price"].notna().sum() >= 2:
        fig.add_trace(
            go.Scatter(
                x=x_values,
                y=dataframe["average_price"],
                mode="lines",
                name="均价",
                line=dict(color="#f2a541", width=1.6),
                hovertemplate="时间 %{x}<br>均价 %{y:.2f}<extra></extra>",
            ),
            row=1,
            col=1,
        )
    fig.add_trace(
        go.Bar(
            x=x_values,
            y=dataframe["volume"],
            name="成交量",
            marker_color=volume_colors,
            opacity=0.82,
            hovertemplate="时间 %{x}<br>成交量 %{y:.0f}<extra></extra>",
        ),
        row=2,
        col=1,
    )

    latest_price = _format_number(stock.get("latest_price"))
    fig.update_layout(
        height=540,
        margin=dict(l=12, r=18, t=18, b=18),
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        font=dict(color=TEXT_COLOR),
        hovermode="x unified",
        dragmode="pan",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, font=dict(color=TEXT_COLOR, size=12)),
        hoverlabel=dict(bgcolor="#ffffff", bordercolor="#d8e4f2", font=dict(color=TEXT_COLOR, size=12)),
        bargap=0.12,
    )
    fig.add_annotation(
        xref="paper",
        yref="paper",
        x=0.01,
        y=0.96,
        text=f"最新价 {latest_price}",
        showarrow=False,
        align="left",
        bgcolor="rgba(255,255,255,0.86)",
        bordercolor="rgba(216,228,242,0.95)",
        borderwidth=1,
        borderpad=5,
        font=dict(color=TEXT_COLOR, size=12),
    )
    _style_plotly_axes(fig)
    fig.update_xaxes(
        type="category",
        categoryorder="array",
        categoryarray=dataframe["time_label"].tolist(),
        tickmode="array",
        tickvals=tick_values,
        ticktext=tick_values,
    )
    fig.update_yaxes(title_text="价格", fixedrange=False, row=1, col=1)
    fig.update_yaxes(title_text="成交量", fixedrange=False, row=2, col=1)
    st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)


def _render_kline_chart(history: list[dict[str, Any]], period: str, title: str, key: str) -> None:
    dataframe = _history_dataframe(history)
    if dataframe.empty:
        render_placeholder("暂无K线数据", "当前未获取到可展示的历史行情。")
        return

    dataframe = _resample_kline(dataframe, period)
    if dataframe.empty:
        render_placeholder("暂无K线数据", "当前周期下没有足够的历史行情。")
        return

    dataframe = _add_kline_indicators(dataframe)
    candle_colors = [UP_COLOR if close >= open_price else DOWN_COLOR for open_price, close in zip(dataframe["open"], dataframe["close"])]
    macd_colors = [UP_COLOR if value >= 0 else DOWN_COLOR for value in dataframe["macd"]]

    fig = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.025,
        row_heights=[0.58, 0.19, 0.23],
    )
    fig.add_trace(
        go.Candlestick(
            x=dataframe["trade_date"],
            open=dataframe["open"],
            high=dataframe["high"],
            low=dataframe["low"],
            close=dataframe["close"],
            name=title,
            increasing=dict(line=dict(color=UP_COLOR, width=1), fillcolor="rgba(224,75,63,0.45)"),
            decreasing=dict(line=dict(color=DOWN_COLOR, width=1), fillcolor="rgba(22,154,98,0.45)"),
        ),
        row=1,
        col=1,
    )
    for column, label in [("ma5", "MA5"), ("ma10", "MA10"), ("ma30", "MA30")]:
        if dataframe[column].notna().sum() < 2:
            continue
        fig.add_trace(
            go.Scatter(
                x=dataframe["trade_date"],
                y=dataframe[column],
                mode="lines",
                name=label,
                line=dict(color=MA_COLORS[column], width=1.4),
                hovertemplate=f"{label} %{{y:.2f}}<extra></extra>",
            ),
            row=1,
            col=1,
        )

    fig.add_trace(
        go.Bar(
            x=dataframe["trade_date"],
            y=dataframe["volume"],
            name="成交量",
            marker_color=candle_colors,
            opacity=0.82,
            hovertemplate="成交量 %{y:.0f}<extra></extra>",
        ),
        row=2,
        col=1,
    )
    fig.add_trace(
        go.Bar(
            x=dataframe["trade_date"],
            y=dataframe["macd"],
            name="MACD",
            marker_color=macd_colors,
            opacity=0.72,
            hovertemplate="MACD %{y:.3f}<extra></extra>",
        ),
        row=3,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=dataframe["trade_date"],
            y=dataframe["dif"],
            mode="lines",
            name="DIF",
            line=dict(color="#1f5f96", width=1.2),
            hovertemplate="DIF %{y:.3f}<extra></extra>",
        ),
        row=3,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=dataframe["trade_date"],
            y=dataframe["dea"],
            mode="lines",
            name="DEA",
            line=dict(color="#f2a541", width=1.2),
            hovertemplate="DEA %{y:.3f}<extra></extra>",
        ),
        row=3,
        col=1,
    )

    fig.update_layout(
        height=620,
        margin=dict(l=12, r=18, t=30, b=18),
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        font=dict(color=TEXT_COLOR),
        hovermode="x unified",
        dragmode="pan",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, font=dict(color=TEXT_COLOR, size=12)),
        title=dict(text=title, x=0, xanchor="left", font=dict(size=14, color=TEXT_COLOR)),
        hoverlabel=dict(bgcolor="#ffffff", bordercolor="#d8e4f2", font=dict(color=TEXT_COLOR, size=12)),
        xaxis_rangeslider_visible=False,
        bargap=0.18,
    )
    _style_plotly_axes(fig)
    fig.update_yaxes(title_text="价格", fixedrange=False, row=1, col=1)
    fig.update_yaxes(title_text="成交量", fixedrange=False, row=2, col=1)
    fig.update_yaxes(title_text="MACD", fixedrange=False, row=3, col=1)
    fig.update_xaxes(tickformat="%Y-%m" if period in {"W", "M"} else "%m-%d")
    st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)


def _style_plotly_axes(fig: go.Figure) -> None:
    fig.update_xaxes(
        showgrid=True,
        gridcolor="rgba(148, 163, 184, 0.26)",
        zeroline=False,
        fixedrange=False,
        tickfont=dict(color=SECONDARY_TEXT_COLOR, size=11),
        title_font=dict(color=TEXT_COLOR, size=12),
        linecolor="rgba(96, 119, 148, 0.45)",
        showline=True,
        showspikes=True,
        spikecolor="rgba(71, 85, 105, 0.45)",
        spikethickness=1,
        spikemode="across",
    )
    fig.update_yaxes(
        showgrid=True,
        gridcolor="rgba(148, 163, 184, 0.26)",
        zeroline=False,
        fixedrange=False,
        tickfont=dict(color=SECONDARY_TEXT_COLOR, size=11),
        title_font=dict(color=TEXT_COLOR, size=12),
        linecolor="rgba(96, 119, 148, 0.45)",
        showline=True,
        showspikes=True,
        spikecolor="rgba(71, 85, 105, 0.45)",
        spikethickness=1,
    )


def _intraday_tick_values(time_labels: list[str]) -> list[str]:
    if not time_labels:
        return []
    preferred = ["09:30", "10:30", "11:30", "13:00", "14:00", "15:00"]
    ticks = [label for label in preferred if label in time_labels]
    if len(ticks) >= 3:
        return ticks

    step = max(1, len(time_labels) // 6)
    indices = list(range(0, len(time_labels), step))
    if indices[-1] != len(time_labels) - 1:
        indices.append(len(time_labels) - 1)
    return [time_labels[index] for index in indices]


def _render_detail_sections(stock: dict[str, Any], history: list[dict[str, Any]]) -> None:
    info_col, table_col = st.columns([0.72, 1.28])
    with info_col:
        _render_stock_info_card(stock)
    with table_col:
        _render_history_table(history)


def _render_stock_info_card(stock: dict[str, Any]) -> None:
    rows = [
        ("股票代码", stock.get("code")),
        ("股票名称", stock.get("name")),
        ("所属市场", stock.get("market")),
        ("所属板块", stock.get("board")),
        ("最新价", _format_number(stock.get("latest_price"))),
        ("涨跌额", _format_signed(stock.get("change_amount"))),
        ("振幅", _format_optional_unit(stock.get("amplitude"), "%")),
        ("成交量", _format_volume(stock.get("volume"))),
    ]
    items_html = "".join(
        f"""
        <div class="info-item">
            <div class="label">{escape(label)}</div>
            <div class="value">{escape(str(value or "-"))}</div>
        </div>
        """
        for label, value in rows
    )
    st.markdown(
        f"""
        <div class="content-card stock-detail-info-card">
            {build_panel_header("股票信息", "实时行情源返回的基础行情字段", "基础信息")}
            <div class="info-grid">{items_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_history_table(history: list[dict[str, Any]]) -> None:
    dataframe = _history_dataframe(history)
    if dataframe.empty:
        return

    display_df = dataframe.tail(30).sort_values("trade_date", ascending=False).copy()
    headers = ["交易日", "开盘", "最高", "最低", "收盘", "涨跌幅", "换手率", "成交量", "成交额"]
    row_html: list[str] = []
    for _, row in display_df.iterrows():
        change_class = _signed_class(row.get("change_percent"))
        row_html.append(
            "<tr>"
            f"<td><span class='record-id'>{escape(row['trade_date'].strftime('%Y-%m-%d'))}</span></td>"
            f"<td><span class='stock-detail-number'>{escape(_format_number(row.get('open')))}</span></td>"
            f"<td><span class='stock-detail-number'>{escape(_format_number(row.get('high')))}</span></td>"
            f"<td><span class='stock-detail-number'>{escape(_format_number(row.get('low')))}</span></td>"
            f"<td><span class='stock-detail-number'>{escape(_format_number(row.get('close')))}</span></td>"
            f"<td><span class='stock-detail-number {change_class}'>{escape(_format_signed(row.get('change_percent'), suffix='%'))}</span></td>"
            f"<td><span class='stock-detail-number'>{escape(_format_optional_unit(row.get('turnover_rate'), '%'))}</span></td>"
            f"<td><span class='stock-detail-number'>{escape(_format_volume(row.get('volume')))}</span></td>"
            f"<td><span class='stock-detail-number'>{escape(_format_amount(row.get('amount')))}</span></td>"
            "</tr>"
        )

    st.markdown(
        "<div class='content-card stock-detail-table-card'>"
        + build_panel_header("近期交易明细", "展示最近 30 个交易日行情", "日线数据")
        + "<div class='record-table-wrap stock-history-table-wrap'>"
        + "<div class='record-table-scroll stock-history-table-scroll'>"
        + "<table class='record-table stock-history-table'>"
        + "<thead><tr>"
        + "".join(f"<th>{escape(header)}</th>" for header in headers)
        + "</tr></thead><tbody>"
        + "".join(row_html)
        + "</tbody></table></div></div></div>",
        unsafe_allow_html=True,
    )


def _history_dataframe(history: list[dict[str, Any]]) -> pd.DataFrame:
    dataframe = pd.DataFrame(history)
    if dataframe.empty:
        return dataframe
    dataframe["trade_date"] = pd.to_datetime(dataframe["trade_date"], errors="coerce")
    for column in ["open", "high", "low", "close", "volume", "amount", "change_percent", "turnover_rate"]:
        if column in dataframe:
            dataframe[column] = pd.to_numeric(dataframe[column], errors="coerce")
    dataframe = dataframe.dropna(subset=["trade_date", "open", "high", "low", "close"]).sort_values("trade_date")
    return dataframe


def _minute_dataframe(minute: list[dict[str, Any]]) -> pd.DataFrame:
    dataframe = pd.DataFrame(minute)
    if dataframe.empty:
        return dataframe
    dataframe["trade_time"] = pd.to_datetime(dataframe["trade_time"], errors="coerce")
    for column in ["price", "volume", "amount", "average_price"]:
        if column in dataframe:
            dataframe[column] = pd.to_numeric(dataframe[column], errors="coerce")
    dataframe = dataframe.dropna(subset=["trade_time", "price"]).sort_values("trade_time")
    if "volume" not in dataframe:
        dataframe["volume"] = 0.0
    dataframe["volume"] = dataframe["volume"].fillna(0.0)
    return dataframe


def _resample_kline(dataframe: pd.DataFrame, period: str) -> pd.DataFrame:
    data = dataframe.copy()
    if period == "D":
        return data.tail(KLINE_HISTORY_DAYS).reset_index(drop=True)

    rule = "W-FRI" if period == "W" else "ME"
    data = data.set_index("trade_date")
    aggregations = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
        "amount": "sum",
    }
    try:
        grouped = data.resample(rule).agg(aggregations)
    except ValueError:
        grouped = data.resample("M").agg(aggregations)
    grouped = grouped.dropna(subset=["open", "high", "low", "close"]).reset_index()
    return grouped.tail(160 if period == "W" else 80).reset_index(drop=True)


def _add_kline_indicators(dataframe: pd.DataFrame) -> pd.DataFrame:
    data = dataframe.copy()
    data["ma5"] = data["close"].rolling(5, min_periods=1).mean()
    data["ma10"] = data["close"].rolling(10, min_periods=1).mean()
    data["ma30"] = data["close"].rolling(30, min_periods=1).mean()
    ema12 = data["close"].ewm(span=12, adjust=False).mean()
    ema26 = data["close"].ewm(span=26, adjust=False).mean()
    data["dif"] = ema12 - ema26
    data["dea"] = data["dif"].ewm(span=9, adjust=False).mean()
    data["macd"] = (data["dif"] - data["dea"]) * 2
    return data


def _render_back_to_market_button() -> None:
    if st.button("返回行情中心", key="stock_detail_back_market", use_container_width=True):
        st.session_state["page"] = "market"
        st.query_params["page"] = "market"
        _drop_query_param("stock_code")
        st.rerun()


def _get_query_param(key: str, default: str = "") -> str:
    value = st.query_params.get(key, default)
    if isinstance(value, list):
        value = value[0] if value else default
    return str(value or default).strip()


def _drop_query_param(key: str) -> None:
    try:
        st.query_params.pop(key, None)
    except Exception:
        try:
            del st.query_params[key]
        except Exception:
            pass


def _signed_class(value: Any) -> str:
    try:
        if value is None or pd.isna(value):
            return "stock-detail-neutral"
        number = float(value)
    except Exception:
        return "stock-detail-neutral"
    if number > 0:
        return "stock-detail-up"
    if number < 0:
        return "stock-detail-down"
    return "stock-detail-neutral"


def _format_number(value: Any) -> str:
    try:
        if value is None or pd.isna(value):
            return "-"
        return f"{float(value):.2f}"
    except Exception:
        return "-"


def _format_signed(value: Any, *, suffix: str = "") -> str:
    try:
        if value is None or pd.isna(value):
            return "-"
        number = float(value)
    except Exception:
        return "-"
    sign = "+" if number > 0 else ""
    return f"{sign}{number:.2f}{suffix}"


def _format_optional_unit(value: Any, unit: str) -> str:
    text = _format_number(value)
    return "-" if text == "-" else f"{text}{unit}"


def _format_amount(value: Any) -> str:
    try:
        if value is None or pd.isna(value):
            return "-"
        number = float(value)
    except Exception:
        return "-"
    if abs(number) >= 100000000:
        return f"{number / 100000000:.2f}亿"
    if abs(number) >= 10000:
        return f"{number / 10000:.2f}万"
    return f"{number:.2f}"


def _format_volume(value: Any) -> str:
    try:
        if value is None or pd.isna(value):
            return "-"
        number = float(value)
    except Exception:
        return "-"
    if abs(number) >= 100000000:
        return f"{number / 100000000:.2f}亿"
    if abs(number) >= 10000:
        return f"{number / 10000:.2f}万"
    return f"{number:.2f}"


def _format_datetime(value: Any) -> str:
    timestamp = pd.to_datetime(value, errors="coerce")
    if pd.isna(timestamp):
        return str(value or "-")
    return timestamp.strftime("%Y-%m-%d %H:%M:%S")


def _inject_stock_detail_css() -> None:
    st.markdown(
        """
        <style>
        .stock-detail-source {
            min-height: 46px;
            display: flex;
            align-items: center;
            flex-wrap: wrap;
            gap: 1rem;
            color: #314256;
            font-size: 0.9rem;
            justify-content: flex-start;
            margin: -0.2rem 0 0.9rem 0;
        }
        .stock-detail-source span {
            color: #243447;
            font-weight: 650;
        }
        .stock-detail-info-card {
            min-height: 360px;
        }
        .stock-detail-chart-card,
        .stock-detail-table-card {
            margin-bottom: 0.35rem;
        }
        .stock-detail-chart-card .panel-heading p,
        .stock-detail-table-card .panel-heading p {
            color: #314256;
            font-weight: 600;
        }
        .stock-history-table-wrap {
            margin-top: 0.55rem;
            border-radius: 16px;
        }
        .stock-history-table-scroll {
            max-height: 500px;
        }
        .stock-history-table th,
        .stock-history-table td {
            white-space: nowrap;
        }
        .stock-detail-number {
            color: #152c4a;
            font-variant-numeric: tabular-nums;
            font-weight: 720;
        }
        .stock-detail-up {
            color: #d84c3f;
        }
        .stock-detail-down {
            color: #1f9d63;
        }
        .stock-detail-neutral {
            color: #52657c;
        }
        .stTabs [data-baseweb="tab-list"] {
            gap: 0.35rem;
            border-bottom: 1px solid rgba(148, 163, 184, 0.28);
        }
        .stTabs [data-baseweb="tab"] {
            height: 2.35rem;
            padding: 0 1rem;
            color: #314256;
            font-weight: 700;
        }
        .stTabs [aria-selected="true"] {
            color: #1f5f96;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
