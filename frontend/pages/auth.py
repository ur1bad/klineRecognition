from __future__ import annotations

import streamlit as st

from frontend.shared import api_post_json, store_auth_payload


def render_auth_page() -> None:
    _inject_auth_css()

    with st.container(key="auth-page"):
        left, right = st.columns([1.05, 0.95], gap="large")

        with left:
            st.markdown(
                """
                <div class="auth-hero-card">
                    <div class="auth-hero-content">
                        <div class="welcome-pill">K-Line Pattern Recognition System</div>
                        <div class="auth-hero-title"><span>K线图</span><span>形态识别系统</span></div>
                        <div class="auth-chart-mark" aria-hidden="true">
                            <span class="candle candle-a"></span>
                            <span class="candle candle-b"></span>
                            <span class="candle candle-c"></span>
                            <span class="candle candle-d"></span>
                            <span class="trend-line"></span>
                        </div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with right:
            with st.container(key="auth-form-shell"):
                login_tab, register_tab = st.tabs(["登录", "注册"])
                with login_tab:
                    _render_login_form()
                with register_tab:
                    _render_register_form()


def _inject_auth_css() -> None:
    st.markdown(
        """
        <style>
        .st-key-auth-page {
            min-height: calc(100vh - 4.8rem);
            display: flex;
            align-items: center;
        }
        .st-key-auth-page [data-testid="column"] {
            display: flex;
            align-items: center;
        }
        .st-key-auth-page [data-testid="column"] > div {
            width: 100%;
        }
        .auth-hero-card {
            min-height: min(620px, calc(100vh - 8rem));
            display: flex;
            align-items: center;
            overflow: hidden;
            position: relative;
            padding: clamp(2rem, 4vw, 3.5rem);
            border-radius: 28px;
            background:
                linear-gradient(145deg, rgba(22, 56, 98, 0.98) 0%, rgba(29, 79, 134, 0.97) 56%, rgba(37, 111, 132, 0.96) 100%);
            color: white;
            box-shadow: 0 20px 46px rgba(14, 38, 74, 0.24);
        }
        .auth-hero-card::before {
            content: "";
            position: absolute;
            inset: 1.15rem;
            border-radius: 24px;
            border: 1px solid rgba(255, 255, 255, 0.10);
            pointer-events: none;
        }
        .auth-hero-card::after {
            content: "";
            position: absolute;
            width: 16rem;
            height: 16rem;
            right: -5rem;
            bottom: -5rem;
            border-radius: 50%;
            background: rgba(255, 255, 255, 0.08);
            pointer-events: none;
        }
        .auth-hero-content {
            position: relative;
            z-index: 1;
            width: 100%;
        }
        .st-key-auth-page a[href^="#"],
        .st-key-auth-page [data-testid="stHeaderActionElements"] {
            display: none !important;
            visibility: hidden !important;
        }
        .auth-hero-title {
            margin: 0;
            font-size: clamp(2.15rem, 4vw, 3.35rem);
            line-height: 1.12;
            letter-spacing: 0;
            font-weight: 800;
        }
        .auth-hero-title span {
            display: block;
        }
        .auth-chart-mark {
            position: relative;
            width: min(100%, 380px);
            height: 150px;
            margin-top: 2.2rem;
            border-radius: 22px;
            background:
                linear-gradient(rgba(255,255,255,0.08) 1px, transparent 1px),
                linear-gradient(90deg, rgba(255,255,255,0.08) 1px, transparent 1px);
            background-size: 100% 37px, 76px 100%;
        }
        .auth-chart-mark .candle {
            position: absolute;
            bottom: 30px;
            width: 18px;
            border-radius: 7px;
            background: rgba(255, 255, 255, 0.88);
            box-shadow: 0 0 0 1px rgba(255,255,255,0.12);
        }
        .auth-chart-mark .candle::before,
        .auth-chart-mark .candle::after {
            content: "";
            position: absolute;
            left: 50%;
            width: 2px;
            transform: translateX(-50%);
            background: rgba(255,255,255,0.68);
            border-radius: 999px;
        }
        .auth-chart-mark .candle::before {
            top: -22px;
            height: 22px;
        }
        .auth-chart-mark .candle::after {
            bottom: -18px;
            height: 18px;
        }
        .auth-chart-mark .candle-a { left: 34px; height: 56px; opacity: 0.72; }
        .auth-chart-mark .candle-b { left: 118px; height: 86px; bottom: 42px; }
        .auth-chart-mark .candle-c { left: 204px; height: 68px; bottom: 34px; opacity: 0.82; }
        .auth-chart-mark .candle-d { left: 292px; height: 98px; bottom: 46px; }
        .auth-chart-mark .trend-line {
            position: absolute;
            left: 28px;
            right: 34px;
            bottom: 54px;
            height: 3px;
            border-radius: 999px;
            background: linear-gradient(90deg, rgba(199, 234, 255, 0.20), rgba(255,255,255,0.94));
            transform: rotate(-10deg);
            transform-origin: left center;
        }
        .st-key-auth-form-shell {
            min-height: min(620px, calc(100vh - 8rem));
            display: flex;
            flex-direction: column;
            justify-content: center;
        }
        .st-key-auth-form-shell [data-testid="stTabs"] {
            padding: 1.2rem 1.2rem 1.3rem;
            border-radius: 24px;
            background: linear-gradient(180deg, rgba(247,250,255,0.96) 0%, rgba(239,246,252,0.96) 100%);
            border: 1px solid var(--border);
            box-shadow: var(--shadow);
        }
        .st-key-auth-form-shell [data-baseweb="tab-list"] {
            width: 100%;
            display: grid !important;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 0.72rem;
            padding: 0.5rem;
            border-radius: 18px;
            background: rgba(226, 237, 249, 0.78);
            border: 1px solid #d8e3f1;
        }
        .st-key-auth-form-shell [data-baseweb="tab-border"],
        .st-key-auth-form-shell [data-baseweb="tab-highlight"] {
            display: none !important;
        }
        .st-key-auth-form-shell button[role="tab"] {
            width: 100%;
            height: 46px;
            justify-content: center;
            border-radius: 14px !important;
            color: #173f74 !important;
            font-weight: 700 !important;
            background: transparent !important;
        }
        .st-key-auth-form-shell button[role="tab"][aria-selected="true"] {
            color: #ffffff !important;
            background: linear-gradient(135deg, #215f8e 0%, #2e8177 100%) !important;
            box-shadow: 0 12px 22px rgba(31, 95, 150, 0.18);
        }
        .st-key-auth-form-shell button[role="tab"] p {
            color: inherit !important;
            font-weight: 700 !important;
        }
        .st-key-auth-form-shell div[data-testid="stForm"] {
            border: 0 !important;
            padding: 1.05rem 0 0;
            background: transparent !important;
            box-shadow: none !important;
        }
        .st-key-auth-form-shell .stTextInput div[data-baseweb="input"],
        .st-key-auth-form-shell .stTextInput div[data-baseweb="input"] > div {
            min-height: 46px;
            border-radius: 14px !important;
            border-color: rgba(197, 214, 234, 0.92) !important;
            background: rgba(239, 246, 252, 0.92) !important;
            box-shadow: none !important;
        }
        .st-key-auth-form-shell .stTextInput input {
            color: var(--text-main) !important;
            background: transparent !important;
            font-size: 0.95rem !important;
        }
        .st-key-auth-form-shell .stTextInput input::placeholder {
            color: #90a0b6 !important;
            opacity: 1 !important;
        }
        .st-key-auth-form-shell .stTextInput input:-webkit-autofill {
            -webkit-box-shadow: 0 0 0 1000px rgba(239, 246, 252, 0.92) inset !important;
            -webkit-text-fill-color: var(--text-main) !important;
        }
        .st-key-auth-form-shell [data-testid="stFormSubmitButton"] > button {
            border: none !important;
            color: #ffffff !important;
            background: linear-gradient(135deg, #1f5f96 0%, #277f75 100%) !important;
            box-shadow: 0 14px 26px rgba(31, 95, 150, 0.22) !important;
        }
        .st-key-auth-form-shell [data-testid="stFormSubmitButton"] > button:hover {
            filter: brightness(1.04);
            transform: translateY(-1px);
        }
        @media (max-width: 900px) {
            .st-key-auth-page,
            .st-key-auth-form-shell,
            .auth-hero-card {
                min-height: auto;
            }
            .auth-hero-card {
                padding: 2rem;
                margin-bottom: 1rem;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_login_form() -> None:
    with st.form("auth_login_form", clear_on_submit=False):
        username = st.text_input("用户名", key="auth_login_username", placeholder="请输入用户名")
        password = st.text_input("密码", key="auth_login_password", type="password", placeholder="请输入密码")
        submitted = st.form_submit_button("登录系统", type="primary", use_container_width=True)

    if not submitted:
        return

    try:
        payload = api_post_json("/auth/login", {"username": username.strip(), "password": password})
    except Exception as exc:
        st.error(f"登录失败：{exc}")
        return

    store_auth_payload(payload)
    st.rerun()


def _render_register_form() -> None:
    with st.form("auth_register_form", clear_on_submit=False):
        username = st.text_input("注册用户名", key="auth_register_username", placeholder="3-32位字母、数字或下划线")
        password = st.text_input("注册密码", key="auth_register_password", type="password", placeholder="至少6位")
        confirm_password = st.text_input("确认密码", key="auth_register_confirm", type="password", placeholder="再次输入密码")
        submitted = st.form_submit_button("注册并登录", type="primary", use_container_width=True)

    if not submitted:
        return

    if password != confirm_password:
        st.error("两次输入的密码不一致。")
        return

    try:
        payload = api_post_json("/auth/register", {"username": username.strip(), "password": password})
    except Exception as exc:
        st.error(f"注册失败：{exc}")
        return

    store_auth_payload(payload)
    st.rerun()
