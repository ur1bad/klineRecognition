from __future__ import annotations

import time
from html import escape

import streamlit as st

from frontend.shared import (
    api_post_json,
    build_panel_header,
    clear_auth_state,
    format_datetime_text,
    get_authenticated_user,
    render_page_banner,
)


def render_profile_page() -> None:
    _inject_profile_css()
    user = get_authenticated_user() or {}
    role_text = "管理员" if user.get("role") == "admin" else "普通用户"
    status_text = "启用" if user.get("is_active") else "禁用"

    render_page_banner(
        "个人中心",
        "查看当前账号信息，并维护登录密码",
        [],
    )

    info_col, password_col = st.columns([0.95, 1.05])
    with info_col:
        _render_profile_info_card(user, role_text, status_text)
    with password_col:
        _render_change_password_card()


def _render_profile_info_card(user: dict[str, object], role_text: str, status_text: str) -> None:
    st.markdown(
        f"""
        <div class="content-card">
            {build_panel_header("账号信息", "当前登录账号的基础信息", "个人资料")}
            <div class="info-grid">
                <div class="info-item">
                    <div class="label">用户名</div>
                    <div class="value">{escape(str(user.get("username") or "-"))}</div>
                </div>
                <div class="info-item">
                    <div class="label">账号角色</div>
                    <div class="value">{escape(role_text)}</div>
                </div>
                <div class="info-item">
                    <div class="label">账号状态</div>
                    <div class="value">{escape(status_text)}</div>
                </div>
                <div class="info-item">
                    <div class="label">识别记录数</div>
                    <div class="value">{escape(str(user.get("record_count") or 0))}</div>
                </div>
                <div class="info-item">
                    <div class="label">最近登录</div>
                    <div class="value">{escape(format_datetime_text(user.get("last_login_at")))}</div>
                </div>
                <div class="info-item">
                    <div class="label">创建时间</div>
                    <div class="value">{escape(format_datetime_text(user.get("created_at")))}</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_change_password_card() -> None:
    with st.container(key="profile-password-panel"):
        st.markdown(
            build_panel_header("修改密码", "输入当前密码并确认新密码", "安全设置"),
            unsafe_allow_html=True,
        )
        with st.form("profile_change_password_form", clear_on_submit=True):
            current_password = st.text_input(
                "当前密码",
                type="password",
                placeholder="请输入当前登录密码",
                key="profile_current_password",
            )
            new_password = st.text_input(
                "新密码",
                type="password",
                placeholder="至少6位",
                key="profile_new_password",
            )
            confirm_password = st.text_input(
                "确认新密码",
                type="password",
                placeholder="再次输入新密码",
                key="profile_confirm_password",
            )
            submitted = st.form_submit_button("修改密码", type="primary", use_container_width=True)

    if not submitted:
        return

    if new_password != confirm_password:
        st.error("两次输入的新密码不一致。")
        return

    try:
        api_post_json(
            "/auth/change_password",
            {"current_password": current_password, "new_password": new_password},
        )
    except Exception as exc:
        st.error(f"修改失败：{exc}")
        return

    st.toast("密码已修改，请重新登录", icon=":material/check_circle:", duration=2)
    time.sleep(2)
    clear_auth_state()
    st.rerun()


def _inject_profile_css() -> None:
    st.markdown(
        """
        <style>
        .st-key-profile-password-panel {
            padding: 1.15rem 1.2rem;
            border-radius: 24px;
            background: var(--surface);
            border: 1px solid var(--border);
            box-shadow: var(--shadow);
            margin-bottom: 1rem;
        }
        .st-key-profile-password-panel div[data-testid="stForm"] {
            border: 0 !important;
            padding: 0.2rem 0 0.4rem !important;
            background: transparent !important;
            box-shadow: none !important;
        }
        .st-key-profile-password-panel .stTextInput div[data-baseweb="input"],
        .st-key-profile-password-panel .stTextInput div[data-baseweb="input"] > div {
            min-height: 46px;
            border-radius: 14px !important;
            border-color: rgba(197, 214, 234, 0.92) !important;
            background: rgba(239, 246, 252, 0.92) !important;
            box-shadow: none !important;
        }
        .st-key-profile-password-panel .stTextInput input {
            color: var(--text-main) !important;
            background: transparent !important;
            font-size: 0.95rem !important;
        }
        .st-key-profile-password-panel .stTextInput input::placeholder {
            color: #90a0b6 !important;
            opacity: 1 !important;
        }
        .st-key-profile-password-panel [data-testid="stFormSubmitButton"] > button {
            border: none !important;
            color: #ffffff !important;
            background: linear-gradient(135deg, #1f5f96 0%, #277f75 100%) !important;
            box-shadow: 0 14px 26px rgba(31, 95, 150, 0.20) !important;
        }
        .st-key-profile-password-panel [data-testid="stFormSubmitButton"] > button:hover {
            filter: brightness(1.04);
            transform: translateY(-1px);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
