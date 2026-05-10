from __future__ import annotations

import base64
import os
from datetime import date, datetime
from html import escape
from typing import Any, Optional

import altair as alt
import pandas as pd
import requests
import streamlit as st


BACKEND_URL = os.getenv("STREAMLIT_BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
DEFAULT_PAGE = "home"
DEFAULT_BACKTEST_HORIZON = 3
PATTERN_OPTIONS = ["", "头肩顶", "头肩底", "双顶", "双底", "上升三角形", "下降三角形", "无明显形态"]
PAGE_META = {
    "home": {
        "label": "首页",
        "icon": "⌂",
        "title": "首页",
        "breadcrumb": "首页",
        "subtitle": "系统总览、运行状态与最近识别动态",
    },
    "upload": {
        "label": "上传K线图识别",
        "icon": "⇪",
        "title": "上传K线图识别",
        "breadcrumb": "上传K线图识别",
        "subtitle": "上传本地 K 线图，快速完成图像识别与结果展示",
    },
    "generate": {
        "label": "自动生成并识别",
        "icon": "◎",
        "title": "自动生成并识别",
        "breadcrumb": "自动生成并识别",
        "subtitle": "输入股票参数后自动生成K线图并完成识别",
    },
    "records": {
        "label": "历史识别记录",
        "icon": "☷",
        "title": "历史识别记录",
        "breadcrumb": "历史识别记录",
        "subtitle": "查询历史识别记录及详情信息",
    },
    "backtest": {
        "label": "回测分析",
        "icon": "◈",
        "title": "回测分析",
        "breadcrumb": "回测分析",
        "subtitle": "基于识别结果和股票历史信息验证识别信号有效性",
    },
}
SOURCE_TYPE_MAP = {
    "upload": "图片上传",
    "generated": "自动生成",
}


st.set_page_config(
    page_title="K线图形态识别系统",
    page_icon="K",
    layout="wide",
    initial_sidebar_state="expanded",
)


def inject_css() -> None:
    """注入统一的后台管理系统风格样式。"""
    st.markdown(
        """
        <style>
        :root {
            --bg-main: #f2f6fb;
            --surface: #ffffff;
            --text-main: #152c4a;
            --text-subtle: #6a7c92;
            --border: #d8e3f1;
            --accent-1: #163a66;
            --shadow: 0 18px 45px rgba(17, 49, 92, 0.10);
        }
        html, body, [class*="css"] {
            font-family: "Microsoft YaHei UI", "PingFang SC", "Segoe UI", sans-serif;
        }
        .stApp {
            background:
                radial-gradient(circle at top right, rgba(72, 129, 211, 0.14), transparent 20%),
                radial-gradient(circle at left top, rgba(24, 67, 126, 0.12), transparent 24%),
                linear-gradient(180deg, #f4f7fc 0%, #edf3fb 100%);
            color: var(--text-main);
        }
        [data-testid="stHeader"] {
            background: transparent;
        }
        [data-testid="stToolbar"] {
            display: flex !important;
            visibility: visible !important;
            background: transparent !important;
        }
        [data-testid="collapsedControl"] {
            display: flex !important;
            visibility: visible !important;
            position: fixed !important;
            top: 0.9rem;
            left: 0.8rem;
            z-index: 10003 !important;
            background: rgba(255, 255, 255, 0.96);
            border-radius: 12px;
            box-shadow: 0 8px 20px rgba(17, 49, 92, 0.14);
        }
        .stAppDeployButton,
        [data-testid="stAppDeployButton"],
        .stDeployButton {
            display: none !important;
            visibility: hidden !important;
        }
        #MainMenu, footer {
            visibility: hidden;
        }
        .block-container {
            max-width: 1560px;
            padding-top: 1.2rem;
            padding-bottom: 2.2rem;
            padding-left: 2rem;
            padding-right: 2rem;
        }
        section[data-testid="stSidebar"] {
            background: linear-gradient(180deg, #17365e 0%, #122b4b 55%, #0d213a 100%);
            border-right: 1px solid rgba(255, 255, 255, 0.06);
        }
        section[data-testid="stSidebar"] > div {
            background: transparent;
        }
        [data-testid="stSidebarNav"] {
            display: none;
        }
        [data-testid="stSidebar"] .block-container {
            padding: 1.2rem 0.95rem 1rem 0.95rem;
        }
        .sidebar-brand {
            display: flex;
            gap: 0.9rem;
            align-items: center;
            margin-bottom: 1.1rem;
            padding: 1.05rem 1rem;
            border-radius: 22px;
            background: linear-gradient(135deg, rgba(255,255,255,0.10), rgba(255,255,255,0.04));
            border: 1px solid rgba(255,255,255,0.08);
            box-shadow: inset 0 1px 0 rgba(255,255,255,0.06);
        }
        .sidebar-brand-badge {
            width: 48px;
            height: 48px;
            border-radius: 16px;
            background: linear-gradient(135deg, #2d63b0, #74a6e3);
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-weight: 800;
            font-size: 1.05rem;
            box-shadow: 0 12px 24px rgba(8, 24, 52, 0.28);
        }
        .sidebar-brand-badge svg {
            width: 31px;
            height: 31px;
            display: block;
            overflow: visible;
        }
        .sidebar-brand h1 {
            margin: 0;
            color: #f4f8ff;
            font-size: 1rem;
            line-height: 1.2;
            font-weight: 700;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: clip;
        }
        .sidebar-brand p {
            margin: 0.22rem 0 0 0;
            color: rgba(223, 233, 248, 0.78);
            font-size: 0.7rem;
            letter-spacing: 0.04em;
            line-height: 1.35;
            white-space: nowrap;
        }
        .sidebar-brand > div:last-child {
            min-width: 0;
        }
        .sidebar-label {
            color: rgba(214, 226, 245, 0.76);
            font-size: 0.76rem;
            letter-spacing: 0.12em;
            text-transform: uppercase;
            margin: 0.35rem 0 0.65rem 0.25rem;
        }
        [data-testid="stSidebar"] .stButton {
            margin-bottom: 0.56rem;
        }
        [data-testid="stSidebar"] .stButton > button {
            width: 100%;
            min-height: 52px;
            border-radius: 16px;
            border: 1px solid rgba(255,255,255,0.08);
            background: rgba(255,255,255,0.06);
            color: #edf4ff;
            font-size: 0.95rem;
            font-weight: 600;
            justify-content: flex-start;
            padding: 0 1rem;
            transition: all 0.2s ease;
            box-shadow: none;
        }
        .sidebar-footer {
            margin-top: 0.95rem;
            padding: 1rem;
            border-radius: 18px;
            background: linear-gradient(180deg, rgba(255,255,255,0.08), rgba(255,255,255,0.05));
            border: 1px solid rgba(255,255,255,0.08);
            color: #eef4ff;
        }
        """
        """
        [data-testid="stSidebar"] .stButton > button:hover {
            border-color: rgba(118, 166, 233, 0.58);
            background: rgba(255,255,255,0.11);
            color: white;
            transform: translateY(-1px);
        }
        [data-testid="stSidebar"] .stButton > button[kind="primary"] {
            border-color: transparent;
            background: linear-gradient(135deg, #245da8 0%, #3d7fca 100%);
            color: white;
            box-shadow: 0 14px 28px rgba(10, 30, 64, 0.26);
        }
        [data-testid="stSidebar"] .stButton > button p,
        [data-testid="stSidebar"] .stButton > button span {
            color: inherit;
            font-weight: 600;
        }
        .sidebar-footer .footer-label {
            color: rgba(223, 233, 248, 0.72);
            font-size: 0.72rem;
            margin-bottom: 0.28rem;
        }
        .sidebar-footer .footer-value {
            font-size: 0.86rem;
            line-height: 1.55;
            word-break: break-all;
        }
        .sidebar-footer .footer-status {
            margin-top: 0.8rem;
            display: inline-flex;
            align-items: center;
            padding: 0.34rem 0.72rem;
            border-radius: 999px;
            background: rgba(255,255,255,0.11);
            font-size: 0.76rem;
            color: #f4f8ff;
        }
        .topbar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 1rem;
            padding: 1rem 1.25rem;
            border-radius: 24px;
            background: rgba(255,255,255,0.88);
            border: 1px solid rgba(20, 61, 110, 0.10);
            backdrop-filter: blur(12px);
            box-shadow: var(--shadow);
            margin-top: 0.2rem;
            margin-bottom: 1rem;
        }
        .topbar-left {
            display: flex;
            align-items: center;
            gap: 0.9rem;
        }
        .topbar-icon {
            width: 48px;
            height: 48px;
            border-radius: 16px;
            display: flex;
            align-items: center;
            justify-content: center;
            background: linear-gradient(135deg, #edf4ff, #dce9fb);
            color: var(--accent-1);
            font-size: 1.15rem;
            font-weight: 800;
        }
        .topbar-crumb {
            color: var(--text-subtle);
            font-size: 0.82rem;
            margin-bottom: 0.18rem;
        }
        .topbar-title {
            color: var(--text-main);
            font-size: 1.25rem;
            font-weight: 700;
            margin: 0;
        }
        .topbar-subtitle {
            color: var(--text-subtle);
            font-size: 0.84rem;
            margin-top: 0.15rem;
        }
        .topbar-right {
            display: flex;
            flex-wrap: wrap;
            justify-content: flex-end;
            gap: 0.65rem;
        }
        .toolbar-chip {
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            padding: 0.5rem 0.8rem;
            border-radius: 999px;
            background: #f4f8ff;
            border: 1px solid var(--border);
            color: var(--text-main);
            font-size: 0.8rem;
        }
        .toolbar-chip.status-online {
            background: rgba(72, 129, 211, 0.14);
            color: #1f4f8c;
            border-color: rgba(72, 129, 211, 0.24);
        }
        .toolbar-chip.status-offline {
            background: rgba(193, 76, 76, 0.10);
            color: #8b3434;
            border-color: rgba(193, 76, 76, 0.18);
        }
        """
        """
        .welcome-card {
            display: block;
            padding: 1.35rem 1.45rem;
            border-radius: 28px;
            background:
                radial-gradient(circle at top right, rgba(125, 173, 237, 0.22), transparent 22%),
                linear-gradient(135deg, #163862 0%, #1d4f86 55%, #2b639f 100%);
            color: white;
            box-shadow: 0 20px 46px rgba(14, 38, 74, 0.24);
            margin-bottom: 1rem;
        }
        .welcome-pill {
            display: inline-flex;
            align-items: center;
            padding: 0.35rem 0.72rem;
            border-radius: 999px;
            background: rgba(255,255,255,0.12);
            color: #f5f9ff;
            font-size: 0.78rem;
            margin-bottom: 0.8rem;
        }
        .welcome-card h2 {
            margin: 0;
            font-size: 1.85rem;
            line-height: 1.3;
        }
        .welcome-card p {
            margin: 0.75rem 0 0 0;
            line-height: 1.7;
            color: rgba(241, 246, 255, 0.88);
            max-width: none;
            font-size: 0.93rem;
            white-space: nowrap;
        }
        .stat-card {
            padding: 1.05rem 1.05rem 1rem;
            border-radius: 24px;
            background: var(--surface);
            border: 1px solid var(--border);
            box-shadow: var(--shadow);
            margin-bottom: 0.2rem;
            min-height: 172px;
            display: flex;
            flex-direction: column;
        }
        .stat-card.compact {
            padding: 0.82rem 0.95rem 0.8rem;
            min-height: 128px;
        }
        .stat-card.compact .stat-label {
            font-size: 0.8rem;
            margin-bottom: 0.45rem;
        }
        .stat-card.compact .stat-value {
            font-size: 1.55rem;
            min-height: 1.7rem;
        }
        .stat-card.compact .stat-desc {
            font-size: 0.72rem;
            line-height: 1.45;
        }
        .stat-card .stat-label {
            font-size: 0.84rem;
            color: var(--text-subtle);
            margin-bottom: 0.65rem;
        }
        .stat-card .stat-value {
            font-size: 1.9rem;
            font-weight: 800;
            color: var(--text-main);
            line-height: 1.1;
            min-height: 2.2rem;
        }
        .stat-card .stat-desc {
            margin-top: auto;
            color: var(--text-subtle);
            font-size: 0.76rem;
            line-height: 1.55;
        }
        .stat-card.emerald { background: linear-gradient(180deg, #ffffff 0%, #f7faff 100%); }
        .stat-card.forest { background: linear-gradient(180deg, #ffffff 0%, #f4f8ff 100%); }
        .stat-card.sage { background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%); }
        .stat-card.mint { background: linear-gradient(180deg, #ffffff 0%, #f2f7ff 100%); }
        .content-card {
            padding: 1.15rem 1.2rem;
            border-radius: 24px;
            background: var(--surface);
            border: 1px solid var(--border);
            box-shadow: var(--shadow);
            margin-bottom: 1rem;
        }
        .panel-heading {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.8rem;
            margin-bottom: 0.95rem;
        }
        .panel-heading h3 {
            margin: 0;
            color: var(--text-main);
            font-size: 1.04rem;
        }
        .panel-heading p {
            margin: 0.18rem 0 0 0;
            color: var(--text-subtle);
            font-size: 0.82rem;
        }
        .panel-badge {
            display: inline-flex;
            align-items: center;
            padding: 0.4rem 0.75rem;
            border-radius: 999px;
            background: #eef4ff;
            border: 1px solid var(--border);
            color: #1f4f8c;
            font-size: 0.77rem;
        }
        .info-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 0.8rem;
        }
        .info-item {
            padding: 0.9rem 0.95rem;
            border-radius: 18px;
            background: #f7faff;
            border: 1px solid var(--border);
        }
        .info-item .label {
            color: var(--text-subtle);
            font-size: 0.78rem;
            margin-bottom: 0.38rem;
        }
        .info-item .value {
            color: var(--text-main);
            font-weight: 700;
            line-height: 1.55;
            font-size: 0.95rem;
        }
        """
        """
        .activity-list {
            display: flex;
            flex-direction: column;
            gap: 0.9rem;
        }
        .activity-item {
            position: relative;
            padding: 0.9rem 1rem 0.95rem 1.35rem;
            margin-left: 0.25rem;
            border-left: 1px dashed #c3d4ea;
            background: linear-gradient(180deg, #f8fbff 0%, #ffffff 100%);
            border-radius: 18px;
        }
        .activity-item::before {
            content: "";
            position: absolute;
            left: -0.38rem;
            top: 0.55rem;
            width: 0.7rem;
            height: 0.7rem;
            border-radius: 50%;
            background: linear-gradient(135deg, #2f6ec3, #5d93dc);
            box-shadow: 0 0 0 5px rgba(72, 129, 211, 0.14);
        }
        .activity-title {
            color: var(--text-main);
            font-size: 0.94rem;
            font-weight: 700;
            margin-bottom: 0.24rem;
        }
        .activity-meta {
            color: var(--text-subtle);
            font-size: 0.8rem;
            line-height: 1.65;
        }
        .activity-tags {
            display: flex;
            flex-wrap: wrap;
            gap: 0.45rem;
            margin-top: 0.5rem;
        }
        .activity-tags span {
            display: inline-flex;
            align-items: center;
            padding: 0.28rem 0.65rem;
            border-radius: 999px;
            background: #eef5ff;
            color: #215695;
            border: 1px solid #d8e5f4;
            font-size: 0.74rem;
        }
        .record-table-wrap {
            border: 1px solid var(--border);
            border-radius: 18px;
            overflow: hidden;
            background: linear-gradient(180deg, #fdfdff 0%, #f6faff 100%);
            margin-top: 0.4rem;
        }
        .record-table-scroll {
            max-height: 320px;
            overflow-y: auto;
        }
        .record-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 0.84rem;
        }
        .record-table thead th {
            text-align: left;
            padding: 0.88rem 0.95rem;
            background: #edf4fb;
            color: #294f80;
            font-weight: 700;
            border-bottom: 1px solid #d8e4f2;
            position: sticky;
            top: 0;
            z-index: 1;
        }
        .record-table tbody tr:nth-child(even) {
            background: rgba(246, 249, 255, 0.90);
        }
        .record-table tbody tr:hover {
            background: rgba(234, 242, 252, 0.92);
        }
        .record-table tbody td {
            padding: 0.88rem 0.95rem;
            color: var(--text-main);
            border-bottom: 1px solid #e6edf6;
        }
        .record-table tbody tr:last-child td {
            border-bottom: none;
        }
        .record-badge {
            display: inline-flex;
            align-items: center;
            padding: 0.24rem 0.58rem;
            border-radius: 999px;
            background: #eef4ff;
            color: #235892;
            border: 1px solid #d7e3f2;
            font-size: 0.74rem;
            font-weight: 600;
        }
        .record-id {
            color: #21538d;
            font-weight: 700;
        }
        .pattern-badge {
            display: inline-flex;
            align-items: center;
            padding: 0.24rem 0.6rem;
            border-radius: 999px;
            background: #f3f7fe;
            color: #233f63;
            border: 1px solid #d8e4f1;
            font-size: 0.74rem;
            font-weight: 700;
        }
        .window-badge {
            display: inline-flex;
            align-items: center;
            padding: 0.24rem 0.56rem;
            border-radius: 999px;
            background: #ecf3ff;
            color: #24578f;
            border: 1px solid #d6e2f2;
            font-size: 0.73rem;
            font-weight: 700;
        }
        .history-confidence {
            font-weight: 700;
            color: #152c4a;
        }
        .history-time-text {
            color: #61748a;
            white-space: nowrap;
        }
        .backtest-kpi-row {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 0.8rem;
            margin-bottom: 1rem;
        }
        .backtest-kpi-card {
            padding: 1rem 1.05rem;
            border-radius: 22px;
            background: linear-gradient(180deg, #ffffff 0%, #f4f8ff 100%);
            border: 1px solid var(--border);
            box-shadow: var(--shadow);
        }
        .backtest-kpi-card .label {
            color: #667a90;
            font-size: 0.82rem;
            margin-bottom: 0.42rem;
        }
        .backtest-kpi-card .value {
            color: var(--text-main);
            font-size: 1.12rem;
            font-weight: 800;
            line-height: 1.35;
        }
        .backtest-table-wrap {
            border: 1px solid var(--border);
            border-radius: 18px;
            overflow: hidden;
            background: linear-gradient(180deg, #fcfdff 0%, #f6faff 100%);
            margin-top: 0.55rem;
        }
        .backtest-table-scroll {
            max-height: 360px;
            overflow-y: auto;
        }
        .backtest-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 0.84rem;
        }
        .backtest-table thead th {
            text-align: left;
            padding: 0.88rem 0.95rem;
            background: #edf4fb;
            color: #264d7f;
            font-weight: 700;
            border-bottom: 1px solid #d8e4f2;
            position: sticky;
            top: 0;
            z-index: 1;
        }
        .backtest-table tbody tr:nth-child(even) {
            background: rgba(246, 249, 255, 0.90);
        }
        .backtest-table tbody td {
            padding: 0.82rem 0.95rem;
            color: var(--text-main);
            border-bottom: 1px solid #e6edf6;
            vertical-align: middle;
        }
        .backtest-table tbody tr:last-child td {
            border-bottom: none;
        }
        .phase-badge {
            display: inline-flex;
            align-items: center;
            padding: 0.25rem 0.58rem;
            border-radius: 999px;
            font-size: 0.74rem;
            font-weight: 700;
            border: 1px solid transparent;
        }
        .phase-badge.window {
            background: #edf3ff;
            color: #21548d;
            border-color: #d9e4f5;
        }
        .phase-badge.future {
            background: #fff4e8;
            color: #a25a12;
            border-color: #f2dbbf;
        }
        .backtest-table .price-text {
            font-weight: 700;
            color: #152c4a;
        }
        .backtest-table .return-text {
            color: #667a90;
            font-weight: 600;
        }
        .tip-list {
            display: flex;
            flex-direction: column;
            gap: 0.85rem;
        }
        .tip-item {
            padding: 0.92rem 0.95rem;
            border-radius: 18px;
            background: linear-gradient(180deg, #f7faff, #ffffff);
            border: 1px solid var(--border);
        }
        .tip-item strong {
            display: block;
            color: var(--text-main);
            margin-bottom: 0.22rem;
        }
        .tip-item span {
            color: var(--text-subtle);
            line-height: 1.7;
            font-size: 0.82rem;
        }
        .page-banner {
            padding: 1.15rem 1.2rem;
            border-radius: 24px;
            background: linear-gradient(180deg, rgba(255,255,255,0.92), rgba(255,255,255,0.98));
            border: 1px solid var(--border);
            box-shadow: var(--shadow);
            margin-bottom: 1rem;
        }
        .page-banner h2 {
            margin: 0;
            color: var(--text-main);
            font-size: 1.35rem;
        }
        .page-banner p {
            margin: 0.45rem 0 0 0;
            color: var(--text-subtle);
            line-height: 1.75;
        }
        .tag-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.55rem;
            margin-top: 0.85rem;
        }
        .tag-row span {
            display: inline-flex;
            align-items: center;
            padding: 0.36rem 0.72rem;
            border-radius: 999px;
            background: #f2f7ff;
            border: 1px solid var(--border);
            color: #22548c;
            font-size: 0.78rem;
        }
        .placeholder-card {
            padding: 1rem 1.05rem;
            border-radius: 22px;
            background: linear-gradient(180deg, #f8fbff 0%, #ffffff 100%);
            border: 1px dashed #c8d8ee;
            color: var(--text-subtle);
            line-height: 1.8;
            margin-bottom: 1rem;
        }
        .stToastContainer [data-testid="stToast"] {
            border-radius: 18px !important;
            border: 1px solid #b8cbe6 !important;
            background: linear-gradient(180deg, #f6f9ff 0%, #ffffff 100%) !important;
            box-shadow: 0 12px 28px rgba(17, 49, 92, 0.14) !important;
            color: #1f7a4d !important;
        }
        .stToastContainer [data-testid="stToast"] span,
        .stToastContainer [data-testid="stToast"] p,
        .stToastContainer [data-testid="stToast"] [data-testid="stMarkdownContainer"] {
            color: #1f7a4d !important;
            font-weight: 700 !important;
        }
        """
        """
        .result-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 0.8rem;
            margin-top: 0.9rem;
        }
        .mini-metric {
            padding: 0.9rem 0.95rem;
            border-radius: 18px;
            background: #f5f9ff;
            border: 1px solid var(--border);
        }
        .mini-metric .label {
            color: var(--text-subtle);
            font-size: 0.78rem;
            margin-bottom: 0.3rem;
        }
        .mini-metric .value {
            color: var(--text-main);
            font-size: 1.1rem;
            font-weight: 800;
            line-height: 1.45;
        }
        .reason-box {
            margin-top: 0.9rem;
            padding: 0.95rem 1rem;
            border-radius: 18px;
            background: linear-gradient(180deg, #f7faff, #ffffff);
            border: 1px dashed #c5d7ed;
            color: var(--text-main);
            line-height: 1.8;
        }
        .tag-cloud {
            display: flex;
            flex-wrap: wrap;
            gap: 0.55rem;
            margin-top: 0.9rem;
        }
        .tag-cloud span {
            display: inline-flex;
            align-items: center;
            padding: 0.35rem 0.72rem;
            border-radius: 999px;
            background: #eef4ff;
            color: #21558d;
            border: 1px solid #d6e2f1;
            font-size: 0.76rem;
        }
        div[data-testid="metric-container"] {
            padding: 1rem 1.05rem;
            border-radius: 20px;
            background: var(--surface);
            border: 1px solid var(--border);
            box-shadow: var(--shadow);
        }
        div[data-testid="metric-container"] label[data-testid="stMetricLabel"] p {
            color: var(--text-subtle);
            font-size: 0.82rem;
            font-weight: 600;
        }
        div[data-testid="metric-container"] div[data-testid="stMetricValue"] {
            color: var(--text-main);
            font-weight: 800;
        }
        div[data-testid="metric-container"] div[data-testid="stMetricDelta"] {
            color: #2d67b7;
        }
        div[data-testid="stForm"] {
            border: 1px solid var(--border);
            border-radius: 24px;
            background: var(--surface);
            box-shadow: var(--shadow);
            padding: 1rem 1.1rem 1.15rem;
            margin-bottom: 1rem;
        }
        .st-key-upload-params-panel {
            border: 1px solid var(--border);
            border-radius: 24px;
            background: var(--surface);
            box-shadow: var(--shadow);
            padding: 1rem 1.1rem 1.15rem;
            margin-bottom: 1rem;
        }
        .st-key-history-filter-panel,
        .st-key-history-detail-panel,
        .st-key-history-delete-panel,
        .st-key-backtest-control-panel {
            border: 1px solid var(--border);
            border-radius: 24px;
            background: var(--surface);
            box-shadow: var(--shadow);
            padding: 1rem 1.1rem 1.15rem;
            margin-bottom: 1rem;
        }
        .st-key-history-delete-panel {
            border-color: #efc7c2;
            background: linear-gradient(180deg, #fffafa 0%, #ffffff 100%);
        }
        .st-key-history-delete-panel .panel-badge {
            background: #fff0ee;
            border-color: #efc7c2;
            color: #a63a34;
        }
        div[data-testid="stForm"] label,
        div[data-testid="stForm"] label p,
        div[data-testid="stForm"] [data-testid="stWidgetLabel"],
        div[data-testid="stForm"] [data-testid="stWidgetLabel"] p,
        .st-key-upload-params-panel label,
        .st-key-upload-params-panel label p,
        .st-key-upload-params-panel [data-testid="stWidgetLabel"],
        .st-key-upload-params-panel [data-testid="stWidgetLabel"] p,
        .st-key-history-filter-panel label,
        .st-key-history-filter-panel label p,
        .st-key-history-filter-panel [data-testid="stWidgetLabel"],
        .st-key-history-filter-panel [data-testid="stWidgetLabel"] p,
        .st-key-history-detail-panel label,
        .st-key-history-detail-panel label p,
        .st-key-history-detail-panel [data-testid="stWidgetLabel"],
        .st-key-history-detail-panel [data-testid="stWidgetLabel"] p,
        .st-key-history-delete-panel label,
        .st-key-history-delete-panel label p,
        .st-key-history-delete-panel [data-testid="stWidgetLabel"],
        .st-key-history-delete-panel [data-testid="stWidgetLabel"] p,
        .st-key-backtest-control-panel label,
        .st-key-backtest-control-panel label p,
        .st-key-backtest-control-panel [data-testid="stWidgetLabel"],
        .st-key-backtest-control-panel [data-testid="stWidgetLabel"] p,
        div[data-testid="stWidgetLabel"] label,
        div[data-testid="stWidgetLabel"] label p,
        div[data-testid="stWidgetLabel"] p,
        div[data-testid="stWidgetLabel"] span {
            color: var(--text-main) !important;
            font-weight: 600 !important;
        }
        .st-key-history-filter-panel div[data-baseweb="select"] > div,
        .st-key-history-detail-panel div[data-baseweb="select"] > div,
        .st-key-backtest-control-panel div[data-baseweb="select"] > div {
            border: 2px solid #284972 !important;
            border-radius: 14px !important;
            background: #ffffff !important;
            box-shadow: none !important;
            min-height: 40px !important;
        }
        .st-key-history-filter-panel div[data-baseweb="select"] {
            border-radius: 14px !important;
        }
        .st-key-history-filter-panel div[data-baseweb="select"] > div,
        .st-key-history-detail-panel div[data-baseweb="select"] > div,
        .st-key-backtest-control-panel div[data-baseweb="select"] > div {
            padding-left: 0.42rem !important;
            padding-right: 0.68rem !important;
            align-items: center !important;
        }
        .st-key-history-filter-panel div[data-baseweb="select"] > div > div,
        .st-key-history-detail-panel div[data-baseweb="select"] > div > div,
        .st-key-backtest-control-panel div[data-baseweb="select"] > div > div {
            min-height: 34px !important;
            display: flex !important;
            align-items: center !important;
        }
        .st-key-history-filter-panel div[data-baseweb="select"] > div > div:first-child,
        .st-key-history-detail-panel div[data-baseweb="select"] > div > div:first-child,
        .st-key-backtest-control-panel div[data-baseweb="select"] > div > div:first-child {
            margin-left: 0 !important;
            padding-left: 0 !important;
            padding-top: 1px !important;
            padding-bottom: 1px !important;
        }
        .st-key-history-filter-panel div[data-baseweb="select"] svg,
        .st-key-history-detail-panel div[data-baseweb="select"] svg,
        .st-key-backtest-control-panel div[data-baseweb="select"] svg {
            color: #152c4a !important;
            fill: #152c4a !important;
        }
        .st-key-history-filter-panel div[data-baseweb="select"] span,
        .st-key-history-filter-panel div[data-baseweb="select"] div,
        .st-key-history-detail-panel div[data-baseweb="select"] span,
        .st-key-history-detail-panel div[data-baseweb="select"] div,
        .st-key-backtest-control-panel div[data-baseweb="select"] span,
        .st-key-backtest-control-panel div[data-baseweb="select"] div {
            color: var(--text-main) !important;
            font-size: 0.92rem !important;
            font-weight: 400 !important;
            letter-spacing: 0.01em !important;
            line-height: 1.35 !important;
        }
        .st-key-history-filter-panel div[data-baseweb="select"] > div:focus-within,
        .st-key-history-detail-panel div[data-baseweb="select"] > div:focus-within {
            border-color: #2d67b7 !important;
            box-shadow: 0 0 0 3px rgba(45, 103, 183, 0.16) !important;
        }
        .st-key-history-filter-panel .stTextInput div[data-baseweb="input"] > div {
            padding-right: 0.85rem !important;
            box-sizing: border-box !important;
        }
        .st-key-history-filter-panel .stTextInput input {
            padding-right: 1rem !important;
            box-sizing: border-box !important;
        }
        div[data-testid="stForm"] .stNumberInput div[data-baseweb="input"] > div,
        .st-key-history-filter-panel .stNumberInput div[data-baseweb="input"] > div {
            padding-right: 0.8rem !important;
        }
        div[data-testid="stForm"] .stNumberInput input,
        .st-key-history-filter-panel .stNumberInput input {
            padding-right: 0.95rem !important;
            background: transparent !important;
            line-height: 1.35 !important;
        }
        div[data-testid="stForm"] .stNumberInput input[type="number"],
        .st-key-history-filter-panel .stNumberInput input[type="number"] {
            -moz-appearance: textfield !important;
        }
        div[data-testid="stForm"] .stNumberInput input[type="number"]::-webkit-outer-spin-button,
        div[data-testid="stForm"] .stNumberInput input[type="number"]::-webkit-inner-spin-button,
        .st-key-history-filter-panel .stNumberInput input[type="number"]::-webkit-outer-spin-button,
        .st-key-history-filter-panel .stNumberInput input[type="number"]::-webkit-inner-spin-button {
            -webkit-appearance: none !important;
            margin: 0 !important;
        }
        .st-key-backtest-control-panel div[data-baseweb="select"] > div:focus-within {
            border-color: #2d67b7 !important;
            box-shadow: 0 0 0 3px rgba(45, 103, 183, 0.16) !important;
        }
        [data-testid="stFileUploader"] section,
        [data-testid="stFileUploaderDropzone"] {
            border-radius: 20px;
            border: 1.4px dashed #a9c4e8;
            background: linear-gradient(180deg, #f8fbff, #f0f5fd) !important;
            min-height: 132px;
            padding: 0.15rem;
        }
        [data-testid="stFileUploader"] section *,
        [data-testid="stFileUploaderDropzone"] > div,
        [data-testid="stFileUploaderDropzone"] section,
        [data-testid="stFileUploaderDropzone"] div {
            background: transparent !important;
        }
        [data-testid="stFileUploader"] section,
        [data-testid="stFileUploaderDropzone"] section {
            padding: 0.8rem 0.9rem !important;
            border-radius: 18px !important;
        }
        [data-testid="stFileUploader"] svg,
        [data-testid="stFileUploaderDropzone"] svg {
            color: #2e6cbe !important;
            fill: #2e6cbe !important;
        }
        [data-testid="stFileUploader"] button,
        [data-testid="stFileUploader"] [data-testid="stBaseButton-secondary"],
        [data-testid="stFileUploader"] [data-testid="stBaseButton-secondary"] button,
        [data-testid="stFileUploaderDropzone"] button,
        [data-testid="stFileUploaderDropzone"] [data-testid="stBaseButton-secondary"],
        [data-testid="stFileUploaderDropzone"] [data-testid="stBaseButton-secondary"] button {
            border: 1px solid #d5e1f0 !important;
            border-radius: 12px !important;
            min-height: 34px !important;
            padding: 0 0.85rem !important;
            background: linear-gradient(180deg, #ffffff, #f5f9ff) !important;
            color: #22548d !important;
            font-weight: 700 !important;
            font-size: 0.86rem !important;
            box-shadow: 0 6px 16px rgba(20, 55, 104, 0.10) !important;
        }
        [data-testid="stFileUploader"] button:hover,
        [data-testid="stFileUploader"] [data-testid="stBaseButton-secondary"]:hover,
        [data-testid="stFileUploader"] [data-testid="stBaseButton-secondary"] button:hover,
        [data-testid="stFileUploaderDropzone"] button:hover,
        [data-testid="stFileUploaderDropzone"] [data-testid="stBaseButton-secondary"]:hover,
        [data-testid="stFileUploaderDropzone"] [data-testid="stBaseButton-secondary"] button:hover {
            border-color: #8eb2e0 !important;
            background: linear-gradient(180deg, #f7faff, #eef4ff) !important;
            color: #173f74 !important;
            transform: translateY(-1px);
        }
        [data-testid="stFileUploader"] small,
        [data-testid="stFileUploader"] span,
        [data-testid="stFileUploader"] p,
        [data-testid="stFileUploaderDropzone"] small,
        [data-testid="stFileUploaderDropzone"] span,
        [data-testid="stFileUploaderDropzone"] p {
            color: var(--text-subtle) !important;
        }
        [data-testid="stFileUploader"] ul,
        [data-testid="stFileUploader"] ul *,
        [data-testid="stFileUploader"] li,
        [data-testid="stFileUploader"] li *,
        [data-testid="stFileUploader"] [role="list"],
        [data-testid="stFileUploader"] [role="list"] *,
        [data-testid="stFileUploader"] [data-testid*="File"],
        [data-testid="stFileUploader"] [data-testid*="File"] * {
            color: #66788f !important;
        }
        .fixed-image-preview {
            width: min(100%, 448px);
            margin: 0 auto;
        }
        .fixed-image-frame {
            width: 100%;
            aspect-ratio: 1 / 1;
            border-radius: 24px;
            border: 1px solid var(--border);
            background: linear-gradient(180deg, #ffffff 0%, #f5f9ff 100%);
            box-shadow: var(--shadow);
            overflow: hidden;
            padding: 0.75rem;
            box-sizing: border-box;
        }
        .fixed-image-frame img {
            width: 100%;
            height: 100%;
            object-fit: contain;
            display: block;
            border-radius: 18px;
            background: #ffffff;
        }
        .fixed-image-caption {
            margin-top: 0.72rem;
            color: var(--text-subtle);
            font-size: 0.82rem;
            text-align: center;
        }
        div[data-baseweb="input"] > div,
        div[data-baseweb="select"] > div,
        textarea {
            border-radius: 14px !important;
            border-color: #d5e2f1 !important;
            background: #f8fbff !important;
        }
        div[data-baseweb="select"] *,
        div[data-baseweb="select"] span,
        div[data-baseweb="select"] input {
            color: var(--text-main) !important;
        }
        div[data-baseweb="popover"] ul[role="listbox"],
        div[data-baseweb="popover"] [role="listbox"] {
            background: #ffffff !important;
            border: 1px solid var(--border) !important;
            border-radius: 16px !important;
            box-shadow: 0 18px 40px rgba(17, 49, 92, 0.14) !important;
            padding: 0.35rem !important;
        }
        div[data-baseweb="popover"] li,
        div[data-baseweb="popover"] [role="option"] {
            color: #74869b !important;
            border-radius: 12px !important;
            padding: 0.58rem 0.72rem !important;
            font-size: 0.86rem !important;
            background: #ffffff !important;
        }
        div[data-baseweb="popover"] li:hover,
        div[data-baseweb="popover"] [role="option"]:hover {
            background: #eef4ff !important;
        }
        div[data-baseweb="popover"] li[aria-selected="true"],
        div[data-baseweb="popover"] [role="option"][aria-selected="true"] {
            background: #e8f0fd !important;
            color: #1e4f8c !important;
            font-weight: 700 !important;
        }
        .stDateInput input,
        .stNumberInput input,
        .stTextInput input {
            color: var(--text-main) !important;
        }
        .stDateInput input::placeholder,
        .stNumberInput input::placeholder,
        .stTextInput input::placeholder,
        div[data-baseweb="input"] input::placeholder,
        textarea::placeholder {
            color: #90a0b6 !important;
            opacity: 1 !important;
        }
        .stButton > button {
            border-radius: 14px;
            min-height: 42px;
            font-weight: 600;
            transition: all 0.2s ease;
        }
        .stButton > button[kind="secondary"] {
            border: 1px solid #cfddee;
            background: white;
            color: var(--text-main);
        }
        .stButton > button[kind="secondary"]:hover {
            border-color: #8aaee0;
            color: #173f74;
        }
        .stButton > button[kind="primary"] {
            border: none;
            color: white;
            background: linear-gradient(135deg, #2159a8 0%, #3a7dc9 100%);
            box-shadow: 0 10px 24px rgba(23, 63, 116, 0.18);
        }
        .stButton > button[kind="primary"]:hover {
            filter: brightness(1.03);
            transform: translateY(-1px);
        }
        .st-key-history-delete-panel .stButton > button {
            border: none !important;
            color: white !important;
            background: linear-gradient(135deg, #a93a35 0%, #d45a50 100%) !important;
            box-shadow: 0 10px 22px rgba(169, 58, 53, 0.18) !important;
        }
        .st-key-history-delete-panel .stButton > button:hover:enabled {
            filter: brightness(1.04);
            transform: translateY(-1px);
        }
        .st-key-history-delete-panel .stButton > button:disabled {
            opacity: 0.48 !important;
            cursor: not-allowed !important;
            box-shadow: none !important;
        }
        [data-testid="stFormSubmitButton"] > button {
            border: none !important;
            border-radius: 16px !important;
            min-height: 46px !important;
            background: linear-gradient(135deg, #173f74 0%, #2a68b5 100%) !important;
            color: white !important;
            font-weight: 700 !important;
            letter-spacing: 0.02em;
            box-shadow: 0 12px 24px rgba(22, 58, 104, 0.20) !important;
        }
        [data-testid="stFormSubmitButton"] > button:hover {
            filter: brightness(1.04);
            transform: translateY(-1px);
        }
        div[data-testid="stDataFrame"] {
            border: 1px solid var(--border);
            border-radius: 18px;
            overflow: hidden;
            box-shadow: 0 10px 28px rgba(17, 49, 92, 0.08);
            background: white;
        }
        .stAlert {
            border-radius: 18px;
        }
        .stImage img {
            border-radius: 22px;
            border: 1px solid rgba(20, 61, 110, 0.10);
            box-shadow: var(--shadow);
        }
        @media (max-width: 900px) {
            .block-container {
                padding-left: 1rem;
                padding-right: 1rem;
            }
            .topbar,
            .welcome-card {
                padding: 1rem;
            }
            .welcome-card,
            .topbar {
                flex-direction: column;
                align-items: flex-start;
            }
            .topbar-right {
                justify-content: flex-start;
            }
            .info-grid,
            .result-grid {
                grid-template-columns: 1fr;
            }
        }
        </style>
        """
        ,
        unsafe_allow_html=True,
    )


def _extract_error_message(response: requests.Response) -> str:
    try:
        payload = response.json()
        if isinstance(payload, dict) and payload.get("detail"):
            return str(payload["detail"])
    except Exception:
        pass
    return response.text or f"HTTP {response.status_code}"


def api_get(path: str, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    clean_params = {key: value for key, value in (params or {}).items() if value not in (None, "")}
    response = requests.get(f"{BACKEND_URL}{path}", params=clean_params, timeout=120)
    if not response.ok:
        raise RuntimeError(_extract_error_message(response))
    return response.json()


def api_post_json(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = requests.post(f"{BACKEND_URL}{path}", json=payload, timeout=600)
    if not response.ok:
        raise RuntimeError(_extract_error_message(response))
    return response.json()


def api_post_multipart(path: str, files: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    response = requests.post(f"{BACKEND_URL}{path}", files=files, data=data, timeout=600)
    if not response.ok:
        raise RuntimeError(_extract_error_message(response))
    return response.json()


def api_delete(path: str) -> dict[str, Any]:
    response = requests.delete(f"{BACKEND_URL}{path}", timeout=120)
    if not response.ok:
        raise RuntimeError(_extract_error_message(response))
    if not response.content:
        return {}
    return response.json()


def initialize_state() -> None:
    """初始化页面状态，并与 query params 做轻量同步。"""
    valid_keys = set(PAGE_META.keys())
    query_page = st.query_params.get("page", DEFAULT_PAGE)
    if isinstance(query_page, list):
        query_page = query_page[0] if query_page else DEFAULT_PAGE
    default_page = query_page if query_page in valid_keys else DEFAULT_PAGE

    st.session_state.setdefault("page", default_page)
    if query_page in valid_keys and st.session_state["page"] != query_page:
        st.session_state["page"] = query_page

    st.session_state.setdefault("selected_backtest_record_id", None)
    st.session_state.setdefault("upload_result", None)
    st.session_state.setdefault("upload_backtest_result", None)
    st.session_state.setdefault("upload_backtest_error", None)
    st.session_state.setdefault("generate_result", None)
    st.session_state.setdefault("generate_backtest_result", None)
    st.session_state.setdefault("generate_backtest_error", None)
    st.session_state.setdefault("backtest_result", None)
    st.session_state.setdefault("backtest_result_key", None)
    st.session_state.setdefault("backtest_autorun_request", False)

    st.query_params["page"] = st.session_state["page"]


def reset_upload_page_state() -> None:
    """清空上传识别页的结果与表单状态。"""
    for key in [
        "upload_result",
        "upload_backtest_result",
        "upload_backtest_error",
        "upload_page_file",
        "upload_stock_code",
        "upload_start_date",
        "upload_end_date",
        "upload_window_size",
    ]:
        st.session_state.pop(key, None)


def reset_generate_page_state() -> None:
    """清空自动生成识别页的结果与表单状态。"""
    for key in [
        "generate_result",
        "generate_backtest_result",
        "generate_backtest_error",
        "generate_stock_code",
        "generate_start_date",
        "generate_end_date",
        "generate_window_size",
    ]:
        st.session_state.pop(key, None)


def reset_records_page_state() -> None:
    """清空历史记录页的详情选择状态。"""
    for key in [
        "history_detail_select",
    ]:
        st.session_state.pop(key, None)


def reset_backtest_page_state() -> None:
    """清空回测分析页的执行结果与控件状态。"""
    for key in [
        "backtest_result",
        "backtest_result_key",
        "backtest_record_select",
        "backtest_horizon_select",
        "backtest_autorun_request",
        "selected_backtest_record_id",
    ]:
        st.session_state.pop(key, None)


def set_page(page_key: str) -> None:
    """切换当前页面，并保证刷新后状态仍然保留。"""
    if page_key not in PAGE_META:
        return
    current_page = get_current_page()
    if current_page == "upload" and page_key != "upload":
        reset_upload_page_state()
    if current_page == "generate" and page_key != "generate":
        reset_generate_page_state()
    if current_page == "records" and page_key != "records":
        reset_records_page_state()
    if current_page == "backtest" and page_key != "backtest":
        reset_backtest_page_state()
    st.session_state["page"] = page_key
    st.query_params["page"] = page_key
    st.rerun()


def get_current_page() -> str:
    page = st.session_state.get("page", DEFAULT_PAGE)
    return page if page in PAGE_META else DEFAULT_PAGE


def load_health_status() -> tuple[Optional[dict[str, Any]], Optional[str]]:
    try:
        return api_get("/health"), None
    except Exception as exc:
        return None, str(exc)


def load_records_payload(
    limit: int = 50,
    *,
    stock_code: Optional[str] = None,
    predicted_label: Optional[str] = None,
) -> tuple[dict[str, Any], Optional[str]]:
    try:
        result = api_get(
            "/records",
            params={
                "limit": limit,
                "offset": 0,
                "stock_code": stock_code or None,
                "predicted_label": predicted_label or None,
            },
        )
        return result, None
    except Exception as exc:
        return {"total": 0, "items": []}, str(exc)


def record_can_backtest(record: dict[str, Any]) -> bool:
    return bool(record.get("stock_code") and record.get("window_size") and record.get("end_date"))


def remember_record(record_id: int) -> None:
    st.session_state["selected_backtest_record_id"] = record_id


def fetch_backtest_result(record_id: int, horizon_days: int = DEFAULT_BACKTEST_HORIZON) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    try:
        result = api_post_json("/backtest", {"record_id": int(record_id), "horizon_days": int(horizon_days)})
        return result, None
    except Exception as exc:
        return None, str(exc)


def format_datetime_text(value: Optional[str]) -> str:
    if not value:
        return "-"
    timestamp = pd.to_datetime(value, errors="coerce")
    if pd.isna(timestamp):
        return str(value)
    return timestamp.strftime("%Y-%m-%d %H:%M")


def is_today(value: Optional[str]) -> bool:
    if not value:
        return False
    timestamp = pd.to_datetime(value, errors="coerce")
    if pd.isna(timestamp):
        return False
    return timestamp.date() == date.today()


def format_confidence(value: Any) -> str:
    try:
        return f"{float(value):.2%}"
    except Exception:
        return "-"


def format_price_text(value: Any) -> str:
    try:
        return f"{float(value):.2f}"
    except Exception:
        return str(value or "-")


def source_type_label(source_type: Optional[str]) -> str:
    return SOURCE_TYPE_MAP.get(str(source_type), str(source_type or "-"))


def model_display_text(value: Optional[str] = None) -> str:
    text = str(value or "").strip()
    lowered = text.lower()
    if (
        not text
        or lowered in {"remote_api", "openai_compat", "custom_fastapi"}
        or lowered.startswith("qwen2.5-vl + lora")
    ):
        return "Qwen2.5-VL-7B-Instruct"
    return text


def format_backtest_status(summary: dict[str, Any]) -> str:
    if summary.get("is_success") is True:
        return "信号有效"
    if summary.get("is_success") is False:
        return "信号失效"
    return "中性信号"


def parse_optional_nonnegative_int_input(raw_value: str, field_label: str) -> tuple[Optional[int], Optional[str]]:
    text = str(raw_value or "").strip()
    if not text:
        return None, None
    if not text.isdigit():
        return None, f"{field_label}请输入大于等于 0 的整数。"

    value = int(text)
    if value < 0:
        return None, f"{field_label}请输入大于等于 0 的整数。"
    return value, None


def validate_upload_date_inputs(
    stock_code: str,
    start_date_text: str,
    end_date_text: str,
    window_size: Optional[int],
) -> tuple[str, str, Optional[int], list[str], list[str]]:
    try:
        result = api_post_json(
            "/resolve_upload_context",
            {
                "stock_code": stock_code.strip(),
                "start_date": start_date_text.strip(),
                "end_date": end_date_text.strip(),
                "window_size": int(window_size) if window_size is not None else None,
            },
        )
    except Exception as exc:
        return (
            start_date_text.strip(),
            end_date_text.strip(),
            int(window_size) if window_size is not None else None,
            [f"参数校验失败：{exc}"],
            [],
        )

    return (
        str(result.get("start_date") or ""),
        str(result.get("end_date") or ""),
        result.get("window_size"),
        list(result.get("validation_errors") or []),
        list(result.get("notices") or []),
    )


def validate_generate_form_inputs(
    stock_code_text: str,
    start_date_text: str,
    end_date_text: str,
    window_size: Optional[int],
) -> tuple[Optional[dict[str, Any]], list[str], list[str]]:
    try:
        result = api_post_json(
            "/resolve_generate_context",
            {
                "stock_code": stock_code_text.strip(),
                "start_date": start_date_text.strip(),
                "end_date": end_date_text.strip(),
                "window_size": int(window_size) if window_size is not None else None,
            },
        )
    except Exception as exc:
        return None, [f"参数校验失败：{exc}"], []

    return (
        result.get("payload"),
        list(result.get("validation_errors") or []),
        list(result.get("notices") or []),
    )


def build_panel_header(title: str, subtitle: str, badge: Optional[str] = None) -> str:
    badge_html = f'<div class="panel-badge">{escape(badge)}</div>' if badge else ""
    subtitle_html = f"<p>{escape(subtitle)}</p>" if subtitle else ""
    return (
        f'<div class="panel-heading"><div><h3>{escape(title)}</h3>'
        f'{subtitle_html}</div>{badge_html}</div>'
    )


def render_page_banner(title: str, subtitle: str, tags: list[str]) -> None:
    tags_html = "".join(f"<span>{escape(tag)}</span>" for tag in tags)
    tag_row_html = f'<div class="tag-row">{tags_html}</div>' if tags else ""
    st.markdown(
        f"""
        <div class="page-banner">
            <h2>{escape(title)}</h2>
            <p>{escape(subtitle)}</p>
            {tag_row_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_stat_card(title: str, value: str, description: str, tone: str, *, compact: bool = False) -> None:
    card_class = f"stat-card {escape(tone)}"
    if compact:
        card_class += " compact"
    st.markdown(
        f"""
        <div class="{card_class}">
            <div class="stat-label">{escape(title)}</div>
            <div class="stat-value">{escape(value)}</div>
            <div class="stat-desc">{escape(description)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_placeholder(title: str, description: str) -> None:
    st.markdown(
        f"""
        <div class="placeholder-card">
            <strong>{escape(title)}</strong><br/>
            {escape(description)}
        </div>
        """,
        unsafe_allow_html=True,
    )


def uploaded_file_to_data_uri(uploaded_file: Any) -> str:
    """将上传文件转成 data URI，便于固定尺寸预览。"""
    mime_type = getattr(uploaded_file, "type", None) or "image/png"
    encoded = base64.b64encode(uploaded_file.getvalue()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def render_fixed_image_preview(image_src: str, caption: str) -> None:
    """以固定比例卡片展示上传预览与识别图像。"""
    st.markdown(
        f"""
        <div class="fixed-image-preview">
            <div class="fixed-image-frame">
                <img src="{escape(image_src, quote=True)}" alt="{escape(caption, quote=True)}" />
            </div>
            <div class="fixed-image-caption">{escape(caption)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar(current_page: str, health: Optional[dict[str, Any]], health_error: Optional[str]) -> None:
    """渲染深绿色后台风格的侧边导航。"""
    backend_status = "后端在线" if health and health.get("status") == "ok" else "后端离线"

    with st.sidebar:
        st.markdown(
            """
            <div class="sidebar-brand">
                <div class="sidebar-brand-badge" aria-hidden="true">
                    <svg viewBox="0 0 32 32" xmlns="http://www.w3.org/2000/svg">
                        <defs>
                            <linearGradient id="brandTrendLine" x1="0%" y1="0%" x2="100%" y2="100%">
                                <stop offset="0%" stop-color="#dcecff" />
                                <stop offset="100%" stop-color="#ffffff" />
                            </linearGradient>
                        </defs>
                        <path d="M5.2 24.8H26.8" stroke="rgba(255,255,255,0.34)" stroke-width="1.4" stroke-linecap="round" />
                        <g stroke="#ffffff" stroke-width="1.6" stroke-linecap="round">
                            <line x1="8" y1="7.4" x2="8" y2="24.2" />
                            <line x1="16" y1="5.2" x2="16" y2="22.4" />
                            <line x1="24" y1="9.2" x2="24" y2="26.2" />
                        </g>
                        <rect x="6.25" y="11.1" width="3.5" height="8.2" rx="1.15" fill="#ffffff" />
                        <rect x="14.25" y="8.2" width="3.5" height="9.9" rx="1.15" fill="#f3f8ff" opacity="0.98" />
                        <rect x="22.25" y="13.9" width="3.5" height="7.1" rx="1.15" fill="#ffffff" opacity="0.9" />
                        <path d="M5.8 21.3L11.1 17.6L16.1 12.4L21.5 13.8L26.2 9.6" fill="none" stroke="url(#brandTrendLine)" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" />
                        <circle cx="26.2" cy="9.6" r="1.75" fill="#ffffff" />
                    </svg>
                </div>
                <div>
                    <h1>K线图形态识别系统</h1>
                    <p>K-Line Pattern Recognition System</p>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        for page_key, meta in PAGE_META.items():
            if st.button(
                f"{meta['icon']}  {meta['label']}",
                key=f"nav_{page_key}",
                type="primary" if current_page == page_key else "secondary",
                use_container_width=True,
            ):
                set_page(page_key)

        error_block = ""
        if health_error:
            error_block = (
                "<div class='footer-label' style='margin-top:0.7rem;'>状态说明</div>"
                f"<div class='footer-value'>{escape(health_error)}</div>"
            )

        st.markdown(
            f"""
            <div class="sidebar-footer">
                <div class="footer-label">后端地址</div>
                <div class="footer-value">{escape(BACKEND_URL)}</div>
                <div class="footer-status">{escape(backend_status)}</div>
                {error_block}
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_topbar(current_page: str, health: Optional[dict[str, Any]], health_error: Optional[str]) -> None:
    meta = PAGE_META[current_page]
    status_online = bool(health and health.get("status") == "ok")
    status_text = "后端在线" if status_online else "后端离线"
    status_class = "status-online" if status_online else "status-offline"
    mode_text = model_display_text(health.get("model_display_name") if health else None)
    date_text = datetime.now().strftime("%Y年%m月%d日")
    subtitle = health_error or meta["subtitle"]

    st.markdown(
        f"""
        <div class="topbar">
            <div class="topbar-left">
                <div class="topbar-icon">{escape(meta['icon'])}</div>
                <div>
                    <div class="topbar-crumb">{escape(meta['breadcrumb'])}</div>
                    <div class="topbar-title">{escape(meta['title'])}</div>
                    <div class="topbar-subtitle">{escape(subtitle)}</div>
                </div>
            </div>
            <div class="topbar-right">
                <div class="toolbar-chip">{escape(date_text)}</div>
                <div class="toolbar-chip">{escape("基座模型：" + mode_text)}</div>
                <div class="toolbar-chip {status_class}">{escape(status_text)}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def build_records_dataframe(items: list[dict[str, Any]]) -> pd.DataFrame:
    if not items:
        return pd.DataFrame()

    dataframe = pd.DataFrame(items).copy()
    for column in ["stock_code", "predicted_label", "source_type", "window_size", "start_date", "end_date", "backend_mode"]:
        if column not in dataframe.columns:
            dataframe[column] = None

    dataframe["stock_code"] = dataframe["stock_code"].fillna("-")
    dataframe["confidence"] = dataframe["confidence"].apply(format_confidence)
    dataframe["source_type"] = dataframe["source_type"].apply(source_type_label)
    dataframe["window_size"] = dataframe["window_size"].fillna("-")
    dataframe["start_date"] = dataframe["start_date"].fillna("-")
    dataframe["end_date"] = dataframe["end_date"].fillna("-")
    dataframe["backend_mode"] = dataframe["backend_mode"].apply(model_display_text)
    dataframe["created_at"] = dataframe["created_at"].apply(format_datetime_text)

    dataframe = dataframe.rename(
        columns={
            "id": "记录ID",
            "stock_code": "股票代码",
            "predicted_label": "识别类别",
            "confidence": "置信度",
            "source_type": "来源",
            "window_size": "窗口大小",
            "start_date": "起始日期",
            "end_date": "结束日期",
            "backend_mode": "基座模型",
            "created_at": "识别时间",
        }
    )

    return dataframe[
        ["记录ID", "股票代码", "识别类别", "置信度", "来源", "窗口大小", "起始日期", "结束日期", "基座模型", "识别时间"]
    ]


def render_recent_activity_card(records: list[dict[str, Any]]) -> None:
    if not records:
        render_placeholder("最近识别记录", "当前还没有识别数据，你可以先从“上传K线图识别”或“自动生成并识别”开始使用")
        return

    items_html: list[str] = []
    for item in records[:2]:
        stock_text = item.get("stock_code") or "未关联股票"
        tags = [
            source_type_label(item.get("source_type")),
            f"置信度 {format_confidence(item.get('confidence'))}",
        ]
        if item.get("window_size"):
            tags.append(f"窗口 {item['window_size']} 日")
        if record_can_backtest(item):
            tags.append("可直接回测")
        tags_html = "".join(f"<span>{escape(tag)}</span>" for tag in tags)
        items_html.append(
            "<div class='activity-item'>"
            f"<div class='activity-title'>#{int(item['id'])} · {escape(stock_text)} · {escape(str(item['predicted_label']))}</div>"
            f"<div class='activity-meta'>识别时间：{escape(format_datetime_text(item.get('created_at')))} · 结束日期：{escape(str(item.get('end_date') or '-'))} · 基座模型：{escape(model_display_text(item.get('backend_mode')))}</div>"
            f"<div class='activity-tags'>{tags_html}</div>"
            "</div>"
        )

    activity_html = (
        "<div class='content-card'>"
        + build_panel_header("最近识别记录", "展示最近两次识别任务的时间、类别与基础信息", "实时动态")
        + "<div class='activity-list'>"
        + "".join(items_html)
        + "</div></div>"
    )
    st.markdown(activity_html, unsafe_allow_html=True)


def render_system_status_card(
    health: Optional[dict[str, Any]],
    health_error: Optional[str],
    total_records: int,
    ready_backtests: int,
) -> None:
    status_rows = [
        ("系统状态", "运行正常" if health and health.get("status") == "ok" else "暂未连接"),
        ("基座模型", model_display_text(health.get("model_display_name") if health else None)),
        ("模型服务", "已连接" if health and health.get("remote_api_connected") else "未连接"),
        ("回测就绪记录", f"{ready_backtests} 条"),
    ]
    rows_html = "".join(
        f"""
        <div class="info-item">
            <div class="label">{escape(label)}</div>
            <div class="value">{escape(value)}</div>
        </div>
        """
        for label, value in status_rows
    )

    error_html = (
        f'<div class="placeholder-card" style="margin-top:0.95rem;"><strong>连接提示</strong><br/>{escape(health_error)}</div>'
        if health_error
        else ""
    )

    st.markdown(
        f"""
        <div class="content-card">
            {build_panel_header("系统运行状态", "集中展示系统服务状态与关键运行信息", f"总记录 {total_records}")}
            <div class="info-grid">{rows_html}</div>
            {error_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_home_records_table(records: list[dict[str, Any]]) -> None:
    if not records:
        render_placeholder("暂无识别记录", "后端数据库中还没有识别结果，执行一次上传识别或自动生成识别后会在这里显示")
        return

    row_html: list[str] = []
    for item in records:
        row_html.append(
            "<tr>"
            f"<td><span class='record-id'>#{int(item['id'])}</span></td>"
            f"<td>{escape(str(item.get('stock_code') or '-'))}</td>"
            f"<td>{escape(str(item.get('predicted_label') or '-'))}</td>"
            f"<td><span class='record-badge'>{escape(source_type_label(item.get('source_type')))}</span></td>"
            f"<td>{escape(format_confidence(item.get('confidence')))}</td>"
            f"<td>{escape(str(item.get('start_date') or '-'))}</td>"
            f"<td>{escape(str(item.get('end_date') or '-'))}</td>"
            f"<td>{escape(str(item.get('window_size') or '-'))}</td>"
            f"<td>{escape(format_datetime_text(item.get('created_at')))}</td>"
            "</tr>"
        )

    table_html = (
        "<div class='content-card'>"
        + build_panel_header("记录总览", "下表展示全部识别记录，可向下滚动查看更多", "数据看板")
        + "<div class='record-table-wrap'>"
        + "<div class='record-table-scroll'>"
        + "<table class='record-table'>"
        + "<thead><tr><th>记录ID</th><th>股票代码</th><th>识别类别</th><th>来源</th><th>置信度</th><th>开始日期</th><th>结束日期</th><th>窗口大小</th><th>识别时间</th></tr></thead>"
        + "<tbody>"
        + "".join(row_html)
        + "</tbody></table></div></div></div>"
    )
    st.markdown(table_html, unsafe_allow_html=True)


def render_history_records_table(records: list[dict[str, Any]]) -> None:
    if not records:
        render_placeholder("没有匹配记录", "当前筛选条件下没有找到识别记录，可以调整筛选条件后重试")
        return

    row_html: list[str] = []
    for item in records:
        window_text = f"{item['window_size']} 日" if item.get("window_size") else "-"
        row_html.append(
            "<tr>"
            f"<td><span class='record-id'>#{int(item['id'])}</span></td>"
            f"<td>{escape(str(item.get('stock_code') or '-'))}</td>"
            f"<td><span class='pattern-badge'>{escape(normalize_pattern_label(item.get('predicted_label') or '-'))}</span></td>"
            f"<td><span class='record-badge'>{escape(source_type_label(item.get('source_type')))}</span></td>"
            f"<td><span class='history-confidence'>{escape(format_confidence(item.get('confidence')))}</span></td>"
            f"<td>{escape(str(item.get('start_date') or '-'))}</td>"
            f"<td>{escape(str(item.get('end_date') or '-'))}</td>"
            f"<td><span class='window-badge'>{escape(window_text)}</span></td>"
            f"<td>{escape(model_display_text(item.get('backend_mode')))}</td>"
            f"<td><span class='history-time-text'>{escape(format_datetime_text(item.get('created_at')))}</span></td>"
            "</tr>"
        )

    table_html = (
        "<div class='content-card'>"
        + build_panel_header("历史记录表格", "展示符合条件的识别记录", "结果列表")
        + "<div class='record-table-wrap'>"
        + "<div class='record-table-scroll' style='max-height: 420px;'>"
        + "<table class='record-table'>"
        + "<thead><tr><th>记录ID</th><th>股票代码</th><th>识别类别</th><th>来源</th><th>置信度</th><th>开始日期</th><th>结束日期</th><th>窗口大小</th><th>基座模型</th><th>识别时间</th></tr></thead>"
        + "<tbody>"
        + "".join(row_html)
        + "</tbody></table></div></div></div>"
    )
    st.markdown(table_html, unsafe_allow_html=True)


def render_prediction_result_card(
    result: dict[str, Any],
    *,
    title: str,
    subtitle: str,
    badge: str = "识别结果",
    extra_tags: Optional[list[str]] = None,
) -> None:
    prediction = result["prediction"]
    record = result["record"]
    tags = [
        f"记录ID #{record['id']}",
        f"来源：{source_type_label(record.get('source_type'))}",
        f"基座模型：{model_display_text(prediction.get('backend_mode'))}",
    ]
    if record.get("stock_code"):
        tags.append(f"股票代码：{record['stock_code']}")
    tags.append(f"开始日期：{record.get('start_date') or '-'}")
    tags.append(f"结束日期：{record.get('end_date') or '-'}")
    if extra_tags:
        tags.extend(extra_tags)
    tag_html = "".join(f"<span>{escape(tag)}</span>" for tag in tags)

    st.markdown(
        f"""
        <div class="content-card">
            {build_panel_header(title, subtitle, badge)}
            <div class="result-grid">
                <div class="mini-metric">
                    <div class="label">预测类别</div>
                    <div class="value">{escape(str(prediction['label']))}</div>
                </div>
                <div class="mini-metric">
                    <div class="label">置信度</div>
                    <div class="value">{escape(format_confidence(prediction['confidence']))}</div>
                </div>
                <div class="mini-metric">
                    <div class="label">记录时间</div>
                    <div class="value">{escape(format_datetime_text(record.get('created_at')))}</div>
                </div>
                <div class="mini-metric">
                    <div class="label">窗口大小</div>
                    <div class="value">{escape(str(record.get('window_size') or '-'))}</div>
                </div>
            </div>
            <div class="reason-box"><strong>模型说明：</strong>{escape(str(prediction['reason']))}</div>
            <div class="tag-cloud">{tag_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_record_detail_card(detail: dict[str, Any]) -> None:
    stock_text = detail.get("stock_code") or "-"
    html = f"""
        <div class="content-card">
            {build_panel_header("记录详情", "查看单条历史记录的核心信息", f"#{int(detail['id'])}")}
            <div class="info-grid">
                <div class="info-item">
                    <div class="label">股票代码</div>
                    <div class="value">{escape(stock_text)}</div>
                </div>
                <div class="info-item">
                    <div class="label">识别类别</div>
                    <div class="value">{escape(str(detail['predicted_label']))}</div>
                </div>
                <div class="info-item">
                    <div class="label">置信度</div>
                    <div class="value">{escape(format_confidence(detail['confidence']))}</div>
                </div>
                <div class="info-item">
                    <div class="label">来源</div>
                    <div class="value">{escape(source_type_label(detail.get('source_type')))}</div>
                </div>
                <div class="info-item">
                    <div class="label">开始日期</div>
                    <div class="value">{escape(str(detail.get('start_date') or '-'))}</div>
                </div>
                <div class="info-item">
                    <div class="label">结束日期</div>
                    <div class="value">{escape(str(detail.get('end_date') or '-'))}</div>
                </div>
                <div class="info-item">
                    <div class="label">窗口大小</div>
                    <div class="value">{escape(str(detail.get('window_size') or '-'))}</div>
                </div>
                <div class="info-item">
                    <div class="label">基座模型</div>
                    <div class="value">{escape(model_display_text(detail.get('backend_mode')))}</div>
                </div>
                <div class="info-item">
                    <div class="label">识别时间</div>
                    <div class="value">{escape(format_datetime_text(detail.get('created_at')))}</div>
                </div>
            </div>
            <div class="reason-box" style="margin-top:0.95rem;"><strong>识别说明：</strong>{escape(str(detail['reason']))}</div>
        </div>
    """
    st.markdown(html, unsafe_allow_html=True)


def normalize_pattern_label(label: Any) -> str:
    text = str(label or "-").strip()
    if "/" in text:
        chinese_part = text.split("/", 1)[0].strip()
        return chinese_part or text
    return text


def translate_signal_direction(direction: Any) -> str:
    mapping = {
        "bullish": "看涨",
        "bearish": "看跌",
        "neutral": "中性",
    }
    return mapping.get(str(direction or "").strip().lower(), str(direction or "-"))


def build_backtest_price_dataframe(result: dict[str, Any]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    for item in result.get("window_prices", []):
        rows.append(
            {
                "trade_date": pd.to_datetime(item["trade_date"], errors="coerce"),
                "close": float(item["close"]),
                "phase": "识别区间",
                "phase_class": "window",
                "return_rate": None,
            }
        )

    for item in result.get("future_prices", []):
        rows.append(
            {
                "trade_date": pd.to_datetime(item["trade_date"], errors="coerce"),
                "close": float(item["close"]),
                "phase": "未来观察",
                "phase_class": "future",
                "return_rate": item.get("return_rate"),
            }
        )

    dataframe = pd.DataFrame(rows)
    if dataframe.empty:
        return dataframe

    dataframe = dataframe.dropna(subset=["trade_date"]).sort_values("trade_date").reset_index(drop=True)
    return dataframe


def build_backtest_table_html(price_df: pd.DataFrame) -> str:
    row_html: list[str] = []
    for _, row in price_df.iterrows():
        trade_date_text = pd.Timestamp(row["trade_date"]).strftime("%Y-%m-%d")
        phase_class = str(row.get("phase_class") or "")
        phase_text = str(row.get("phase") or "-")
        close_text = format_price_text(row.get("close"))
        return_text = "-"
        if pd.notna(row.get("return_rate")):
            return_text = f"{float(row['return_rate']):.2%}"
        row_html.append(
            "<tr>"
            f"<td>{escape(trade_date_text)}</td>"
            f"<td><span class='phase-badge {escape(phase_class)}'>{escape(phase_text)}</span></td>"
            f"<td><span class='price-text'>{escape(close_text)}</span></td>"
            f"<td><span class='return-text'>{escape(return_text)}</span></td>"
            "</tr>"
        )

    return (
        "<div class='backtest-table-wrap'>"
        "<div class='backtest-table-scroll'>"
        "<table class='backtest-table'>"
        "<thead><tr><th>交易日期</th><th>阶段</th><th>收盘价</th><th>相对收益率</th></tr></thead>"
        f"<tbody>{''.join(row_html)}</tbody>"
        "</table></div></div>"
    )


def render_backtest_visual(result: dict[str, Any], *, title: str, image_url: Optional[str] = None) -> None:
    summary = result["summary"]
    phase_label = normalize_pattern_label(summary["predicted_label"])
    signal_text = translate_signal_direction(summary["signal_direction"])
    future_direction_text = translate_signal_direction(summary.get("future_direction"))
    future_return_text = f"{summary['future_return']:.2%}"
    current_close_text = format_price_text(summary.get("current_close"))
    future_close_text = format_price_text(summary.get("future_close"))
    price_df = build_backtest_price_dataframe(result)

    kpi_html = f"""
        <div class="backtest-kpi-row">
            <div class="backtest-kpi-card">
                <div class="label">识别形态</div>
                <div class="value">{escape(phase_label)}</div>
            </div>
            <div class="backtest-kpi-card">
                <div class="label">识别信号</div>
                <div class="value">{escape(signal_text)}</div>
            </div>
            <div class="backtest-kpi-card">
                <div class="label">未来{int(summary['horizon_days'])}日收益</div>
                <div class="value">{escape(future_return_text)}</div>
            </div>
        </div>
    """
    st.markdown(kpi_html, unsafe_allow_html=True)

    left, right = st.columns([1.25, 0.95])
    with left:
        st.markdown(
            build_panel_header(
                title,
                f"展示识别区间内每个交易日及后续 {int(summary['horizon_days'])} 个交易日的收盘价变化",
                "价格轨迹",
            ),
            unsafe_allow_html=True,
        )
        if not price_df.empty:
            min_close = float(price_df["close"].min())
            max_close = float(price_df["close"].max())
            close_span = max_close - min_close
            y_padding = close_span * 0.1 if close_span > 0 else max(abs(min_close) * 0.03, 1)
            y_domain = [min_close - y_padding, max_close + y_padding]

            base_chart = alt.Chart(price_df).encode(
                x=alt.X("trade_date:T", title="交易日期", axis=alt.Axis(format="%m-%d", labelAngle=0)),
                y=alt.Y("close:Q", title="收盘价", scale=alt.Scale(domain=y_domain, zero=False)),
                tooltip=[
                    alt.Tooltip("trade_date:T", title="交易日期", format="%Y-%m-%d"),
                    alt.Tooltip("phase:N", title="阶段"),
                    alt.Tooltip("close:Q", title="收盘价", format=".2f"),
                ],
            )
            line_chart = base_chart.mark_line(color="#245fae", strokeWidth=3, interpolate="monotone")
            point_chart = base_chart.mark_point(filled=True, size=90).encode(
                color=alt.Color(
                    "phase:N",
                    scale=alt.Scale(
                        domain=["识别区间", "未来观察"],
                        range=["#245fae", "#d9852b"],
                    ),
                    legend=None,
                )
            )
            st.altair_chart((line_chart + point_chart).properties(height=300), use_container_width=True)
            st.markdown(build_backtest_table_html(price_df), unsafe_allow_html=True)
        else:
            render_placeholder("暂无可视化数据", "当前回测暂未返回足够的价格序列，暂时无法绘制曲线")

    with right:
        summary_html = f"""
            <div class="content-card">
                {build_panel_header("结论摘要", "用于直观查看回测结论", format_backtest_status(summary))}
                <div class="info-grid">
                    <div class="info-item">
                        <div class="label">股票代码</div>
                        <div class="value">{escape(str(summary['stock_code']))}</div>
                    </div>
                    <div class="info-item">
                        <div class="label">未来方向</div>
                        <div class="value">{escape(future_direction_text)}</div>
                    </div>
                    <div class="info-item">
                        <div class="label">当前收盘价</div>
                        <div class="value">{escape(current_close_text)}</div>
                    </div>
                    <div class="info-item">
                        <div class="label">未来{int(summary['horizon_days'])}日收盘价</div>
                        <div class="value">{escape(future_close_text)}</div>
                    </div>
                </div>
                <div class="reason-box" style="margin-top:0.95rem;"><strong>说明：</strong>{escape(str(summary['note']))}</div>
            </div>
        """
        st.markdown(summary_html, unsafe_allow_html=True)
        if image_url:
            render_fixed_image_preview(image_url, "对应识别图像")


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


def _render_upload_page_legacy() -> None:
    render_page_banner(
        "上传K线图识别",
        "上传本地 K 线图图片，系统会返回识别类别、置信度与可用于后续回测的记录信息",
        [],
    )

    form_col, info_col = st.columns([1.18, 0.92])
    with form_col:
        with st.form("upload_predict_form", clear_on_submit=False):
            st.markdown(
                build_panel_header("上传参数面板", "上传图片与填写可选的行情辅助字段，便于后续回测"),
                unsafe_allow_html=True,
            )
            upload = st.file_uploader("上传 K 线图图片", type=["png", "jpg", "jpeg", "bmp"])
            stock_code = st.text_input("股票代码（可选）", value="")
            start_date = st.text_input("开始日期（可选）", value="", placeholder="2024-01-01")
            end_date = st.text_input("结束日期（可选）", value="", placeholder="2024-06-30")
            window_size = st.number_input("窗口大小（可选）", min_value=20, max_value=240, value=30, step=1)
            submitted = st.form_submit_button("开始识别", type="primary", use_container_width=True)
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
        if "upload" in locals() and upload is not None:
            st.image(upload, caption="待识别图片预览", use_container_width=True)
        else:
            render_placeholder("图片预览区", "上传图片后，这里会显示待识别的 K 线图预览")

    if submitted:
        if upload is None:
            st.error("请先上传一张 K 线图。")
        else:
            with st.spinner("正在调用后端完成图片识别..."):
                try:
                    files = {"file": (upload.name, upload.getvalue(), upload.type or "image/png")}
                    data = {
                        "stock_code": stock_code.strip(),
                        "start_date": start_date.strip(),
                        "end_date": end_date.strip(),
                        "window_size": int(window_size),
                    }
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

    image_col, result_col = st.columns([1.08, 1.0])
    with image_col:
        if result["record"].get("image_url"):
            st.image(result["record"]["image_url"], caption="识别图像", use_container_width=True)
        else:
            render_placeholder("识别图像", "当前记录暂未返回可访问的图像地址")
    with result_col:
        render_prediction_result_card(
            result,
            title="上传识别结果",
            subtitle="展示模型输出、记录信息与结果标签",
            extra_tags=["页面来源：上传K线图识别"],
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


def render_upload_page() -> None:
    render_page_banner(
        "上传K线图识别",
        "上传本地 K 线图图片，系统会返回识别类别、置信度与可用于后续回测的记录信息",
        [],
    )

    form_col, info_col = st.columns([1.18, 0.92])
    with form_col:
        upload = st.file_uploader(
            "上传 K 线图图片",
            type=["png", "jpg", "jpeg", "bmp"],
            key="upload_page_file",
        )
        with st.form("upload_predict_form", clear_on_submit=False):
            st.markdown(
                build_panel_header("上传参数面板", "上传图片与填写可选的行情辅助字段，便于后续回测"),
                unsafe_allow_html=True,
            )
            stock_code = st.text_input("股票代码（可选）", value="")
            start_date = st.text_input("开始日期（可选）", value="", placeholder="2024-01-01")
            end_date = st.text_input("结束日期（可选）", value="", placeholder="2024-06-30")
            window_size = st.number_input("窗口大小（可选）", min_value=20, max_value=240, value=30, step=1)
            submitted = st.form_submit_button("开始识别", type="primary", use_container_width=True)

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
            with st.spinner("正在调用后端完成图片识别..."):
                try:
                    files = {"file": (upload.name, upload.getvalue(), upload.type or "image/png")}
                    data = {
                        "stock_code": stock_code.strip(),
                        "start_date": start_date.strip(),
                        "end_date": end_date.strip(),
                        "window_size": int(window_size),
                    }
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


def render_history_page() -> None:
    render_page_banner(
        "历史识别记录",
        "支持按股票代码与识别类别筛选结果，并可查看单条记录详情",
        [],
    )

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
