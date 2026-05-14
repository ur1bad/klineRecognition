from __future__ import annotations

from html import escape
from typing import Any

import streamlit as st

from frontend.shared import (
    api_get,
    api_patch_json,
    api_post_json,
    build_panel_header,
    format_datetime_text,
    get_authenticated_user,
    render_page_banner,
    render_placeholder,
    render_stat_card,
)


ROLE_OPTIONS = [("普通用户", "user"), ("管理员", "admin")]
STATUS_OPTIONS = [("启用", True), ("禁用", False)]


def render_user_management_page() -> None:
    _inject_user_management_css()
    render_page_banner(
        "用户管理",
        "维护系统登录账号、账号角色和启用状态",
        [],
    )
    delete_notice = st.session_state.pop("admin_delete_notice", None)
    if delete_notice:
        st.toast(str(delete_notice), icon=":material/check_circle:", duration=3)
    create_notice = st.session_state.pop("admin_create_notice", None)
    if create_notice:
        st.toast(str(create_notice), icon=":material/check_circle:", duration=3)
    update_notice = st.session_state.pop("admin_update_notice", None)
    if update_notice:
        st.toast(str(update_notice), icon=":material/check_circle:", duration=3)

    try:
        payload = api_get("/admin/users")
    except Exception as exc:
        st.error(f"获取用户列表失败：{exc}")
        return

    users = list(payload.get("items") or [])
    active_count = sum(1 for user in users if user.get("is_active"))
    admin_count = sum(1 for user in users if user.get("role") == "admin")

    metric_col1, metric_col2, metric_col3 = st.columns(3)
    with metric_col1:
        render_stat_card("用户总数", str(payload.get("total", len(users))), "系统当前已创建的账号数量", "emerald", compact=True)
    with metric_col2:
        render_stat_card("启用账号", str(active_count), "当前可以登录系统的账号数量", "forest", compact=True)
    with metric_col3:
        render_stat_card("管理员账号", str(admin_count), "拥有用户管理入口的账号数量", "sage", compact=True)

    _render_users_table(users)

    form_col, manage_col = st.columns([0.95, 1.05])
    with form_col:
        _render_create_user_panel()
    with manage_col:
        _render_edit_user_panel(users)


def _render_users_table(users: list[dict[str, Any]]) -> None:
    if not users:
        render_placeholder("暂无用户", "当前系统还没有可管理的用户账号")
        return

    rows: list[str] = []
    for user in users:
        role_text = "管理员" if user.get("role") == "admin" else "普通用户"
        status_text = "启用" if user.get("is_active") else "禁用"
        rows.append(
            "<tr>"
            f"<td><span class='record-id'>#{int(user['id'])}</span></td>"
            f"<td>{escape(str(user.get('username') or '-'))}</td>"
            f"<td><span class='record-badge'>{escape(role_text)}</span></td>"
            f"<td><span class='pattern-badge'>{escape(status_text)}</span></td>"
            f"<td>{escape(str(user.get('record_count') or 0))}</td>"
            f"<td>{escape(format_datetime_text(user.get('last_login_at')))}</td>"
            f"<td>{escape(format_datetime_text(user.get('created_at')))}</td>"
            "</tr>"
        )

    table_html = (
        "<div class='content-card'>"
        + build_panel_header("账号列表", "展示系统内全部用户账号及其状态", "人员管理")
        + "<div class='record-table-wrap'>"
        + "<div class='record-table-scroll' style='max-height: 360px;'>"
        + "<table class='record-table'>"
        + "<thead><tr><th>ID</th><th>用户名</th><th>角色</th><th>状态</th><th>识别记录数</th><th>最近登录</th><th>创建时间</th></tr></thead>"
        + "<tbody>"
        + "".join(rows)
        + "</tbody></table></div></div></div>"
    )
    st.markdown(table_html, unsafe_allow_html=True)


def _render_create_user_panel() -> None:
    with st.container(key="admin-create-user-panel"):
        st.markdown(
            build_panel_header("新增用户", "创建普通用户或管理员账号", "创建账号"),
            unsafe_allow_html=True,
        )
        with st.form("admin_create_user_form", clear_on_submit=True):
            username = st.text_input("用户名", placeholder="3-32位字母、数字或下划线", key="admin_create_username")
            password = st.text_input("初始密码", type="password", placeholder="至少6位", key="admin_create_password")
            role_label = st.selectbox(
                "账号角色",
                options=ROLE_OPTIONS,
                format_func=lambda option: option[0],
                key="admin_create_role",
            )
            is_active = st.checkbox("创建后启用账号", value=True, key="admin_create_active")
            submitted = st.form_submit_button("创建用户", type="primary", use_container_width=True)

    if not submitted:
        return

    try:
        api_post_json(
            "/admin/users",
            {
                "username": username.strip(),
                "password": password,
                "role": role_label[1],
                "is_active": bool(is_active),
            },
        )
    except Exception as exc:
        st.error(f"创建失败：{exc}")
        return

    st.session_state["admin_create_notice"] = "用户已创建"
    st.rerun()


def _render_edit_user_panel(users: list[dict[str, Any]]) -> None:
    if not users:
        return

    option_map = {f"#{user['id']} | {user.get('username')}": user for user in users}
    current_user = get_authenticated_user() or {}

    with st.container(key="admin-edit-user-panel"):
        st.markdown(
            build_panel_header("账号维护", "调整角色和启用状态", "权限设置"),
            unsafe_allow_html=True,
        )

        user_options = list(option_map.keys())
        if st.session_state.get("admin_selected_user") not in user_options:
            st.session_state["admin_selected_user"] = user_options[0]
        selected_label = st.selectbox("选择用户", options=user_options, key="admin_selected_user")
        selected_user = option_map[selected_label]
        user_id = int(selected_user["id"])
        role_index = 1 if selected_user.get("role") == "admin" else 0
        status_index = 0 if selected_user.get("is_active") else 1
        record_count = int(selected_user.get("record_count") or 0)
        is_current_user = int(current_user.get("id") or 0) == user_id
        delete_confirmed = st.checkbox(
            f"确认删除 {selected_user.get('username')} 及其 {record_count} 条识别记录和对应图片",
            key=f"admin_delete_confirm_{user_id}",
            disabled=is_current_user,
        )

        with st.form("admin_update_user_form", clear_on_submit=False):
            selected_role = st.selectbox(
                "账号角色",
                options=ROLE_OPTIONS,
                index=role_index,
                format_func=lambda option: option[0],
                key=f"admin_update_role_{user_id}",
            )
            selected_status = st.selectbox(
                "账号状态",
                options=STATUS_OPTIONS,
                index=status_index,
                format_func=lambda option: option[0],
                key=f"admin_update_status_{user_id}",
            )
            save_col, delete_col = st.columns(2)
            with save_col:
                update_clicked = st.form_submit_button(
                    "保存账号设置",
                    type="primary",
                    use_container_width=True,
                    key="admin_save_user_button",
                )
            with delete_col:
                with st.container(key="admin-delete-user-action"):
                    delete_clicked = st.form_submit_button(
                        "删除用户",
                        use_container_width=True,
                        key="admin_delete_user_button",
                        disabled=is_current_user or not delete_confirmed,
                    )

    if delete_clicked:
        if int(current_user.get("id") or 0) == user_id:
            st.error("不能删除当前登录的管理员账号。")
            return
        try:
            result = api_post_json(f"/admin/users/{user_id}/delete", {})
        except Exception as exc:
            st.error(f"删除失败：{exc}")
            return
        records_deleted = int(result.get("records_deleted") or 0)
        images_deleted = int(result.get("images_deleted") or 0)
        for key in [
            "admin_selected_user",
            f"admin_update_role_{user_id}",
            f"admin_update_status_{user_id}",
            f"admin_delete_confirm_{user_id}",
        ]:
            st.session_state.pop(key, None)
        st.session_state["admin_delete_notice"] = (
            f"用户已删除，清理 {records_deleted} 条识别记录、{images_deleted} 张图片"
        )
        st.rerun()

    if update_clicked:
        if int(current_user.get("id") or 0) == user_id and (selected_role[1] != "admin" or selected_status[1] is False):
            st.error("不能降级或禁用当前登录的管理员账号。")
            return
        try:
            api_patch_json(
                f"/admin/users/{user_id}",
                {"role": selected_role[1], "is_active": bool(selected_status[1])},
            )
        except Exception as exc:
            st.error(f"保存失败：{exc}")
            return
        st.session_state["admin_update_notice"] = "账号设置已保存"
        st.rerun()


def _inject_user_management_css() -> None:
    st.markdown(
        """
        <style>
        .st-key-admin-create-user-panel,
        .st-key-admin-edit-user-panel {
            padding: 1.15rem 1.2rem;
            border-radius: 24px;
            background: var(--surface);
            border: 1px solid var(--border);
            box-shadow: var(--shadow);
            margin-bottom: 1rem;
        }
        .st-key-admin-create-user-panel div[data-testid="stForm"],
        .st-key-admin-edit-user-panel div[data-testid="stForm"] {
            border: 0 !important;
            padding: 0.2rem 0 0.4rem !important;
            background: transparent !important;
            box-shadow: none !important;
        }
        .st-key-admin-create-user-panel .stTextInput div[data-baseweb="input"],
        .st-key-admin-create-user-panel .stTextInput div[data-baseweb="input"] > div,
        .st-key-admin-edit-user-panel .stTextInput div[data-baseweb="input"],
        .st-key-admin-edit-user-panel .stTextInput div[data-baseweb="input"] > div {
            min-height: 46px;
            border-radius: 14px !important;
            border-color: rgba(197, 214, 234, 0.92) !important;
            background: rgba(239, 246, 252, 0.92) !important;
            box-shadow: none !important;
        }
        .st-key-admin-create-user-panel .stTextInput input,
        .st-key-admin-edit-user-panel .stTextInput input {
            color: var(--text-main) !important;
            background: transparent !important;
            font-size: 0.95rem !important;
        }
        .st-key-admin-create-user-panel .stTextInput input::placeholder,
        .st-key-admin-edit-user-panel .stTextInput input::placeholder {
            color: #90a0b6 !important;
            opacity: 1 !important;
        }
        .st-key-admin-create-user-panel div[data-baseweb="select"] > div,
        .st-key-admin-edit-user-panel div[data-baseweb="select"] > div {
            min-height: 46px;
            border-radius: 14px !important;
            border-color: rgba(197, 214, 234, 0.92) !important;
            background: rgba(239, 246, 252, 0.92) !important;
            box-shadow: none !important;
        }
        .st-key-admin-create-user-panel div[data-baseweb="select"] *,
        .st-key-admin-edit-user-panel div[data-baseweb="select"] * {
            color: var(--text-main) !important;
        }
        .st-key-admin_selected_user div[data-baseweb="select"] > div {
            min-height: 46px;
            border-radius: 14px !important;
            border-color: rgba(197, 214, 234, 0.92) !important;
            background: rgba(239, 246, 252, 0.92) !important;
            box-shadow: none !important;
        }
        .st-key-admin_selected_user div[data-baseweb="select"] *,
        .st-key-admin_selected_user [data-baseweb="select"] *,
        .st-key-admin_selected_user [data-testid="stWidgetLabel"],
        .st-key-admin_selected_user [data-testid="stWidgetLabel"] p {
            color: var(--text-main) !important;
        }
        .st-key-admin-create-user-panel [data-testid="stCheckbox"],
        .st-key-admin-edit-user-panel [data-testid="stCheckbox"] {
            padding: 0.2rem 0 0.55rem;
        }
        .st-key-admin-create-user-panel [data-testid="stFormSubmitButton"] > button,
        .st-key-admin-edit-user-panel [data-testid="stFormSubmitButton"] > button {
            border: none !important;
            color: #ffffff !important;
            background: linear-gradient(135deg, #1f5f96 0%, #277f75 100%) !important;
            box-shadow: 0 14px 26px rgba(31, 95, 150, 0.20) !important;
        }
        .st-key-admin-create-user-panel [data-testid="stFormSubmitButton"] > button:hover,
        .st-key-admin-edit-user-panel [data-testid="stFormSubmitButton"] > button:hover {
            filter: brightness(1.04);
            transform: translateY(-1px);
        }
        .st-key-admin-delete-user-action [data-testid="stFormSubmitButton"] > button,
        .st-key-admin-edit-user-panel .st-key-admin-delete-user-action [data-testid="stFormSubmitButton"] > button,
        .st-key-admin-edit-user-panel .st-key-admin_delete_user_button button,
        .st-key-admin-edit-user-panel .st-key-admin-delete-user-button button,
        .st-key-admin-edit-user-panel .st-key-admin_delete_user_button [data-testid="stFormSubmitButton"] > button,
        .st-key-admin-edit-user-panel .st-key-admin-delete-user-button [data-testid="stFormSubmitButton"] > button {
            background: linear-gradient(135deg, #b94a48 0%, #8f3432 100%) !important;
            color: #ffffff !important;
            border-color: transparent !important;
            box-shadow: 0 14px 26px rgba(143, 52, 50, 0.18) !important;
        }
        .st-key-admin-delete-user-action [data-testid="stFormSubmitButton"] > button:hover,
        .st-key-admin-edit-user-panel .st-key-admin-delete-user-action [data-testid="stFormSubmitButton"] > button:hover,
        .st-key-admin-edit-user-panel .st-key-admin_delete_user_button button:hover,
        .st-key-admin-edit-user-panel .st-key-admin-delete-user-button button:hover,
        .st-key-admin-edit-user-panel .st-key-admin_delete_user_button [data-testid="stFormSubmitButton"] > button:hover,
        .st-key-admin-edit-user-panel .st-key-admin-delete-user-button [data-testid="stFormSubmitButton"] > button:hover {
            filter: brightness(1.04);
            transform: translateY(-1px);
        }
        .st-key-admin-delete-user-action [data-testid="stFormSubmitButton"] > button:disabled,
        .st-key-admin-edit-user-panel .st-key-admin-delete-user-action [data-testid="stFormSubmitButton"] > button:disabled,
        .st-key-admin-edit-user-panel .st-key-admin_delete_user_button button:disabled,
        .st-key-admin-edit-user-panel .st-key-admin-delete-user-button button:disabled,
        .st-key-admin-edit-user-panel .st-key-admin_delete_user_button [data-testid="stFormSubmitButton"] > button:disabled,
        .st-key-admin-edit-user-panel .st-key-admin-delete-user-button [data-testid="stFormSubmitButton"] > button:disabled {
            background: #d9e2ee !important;
            color: #7d8da2 !important;
            border-color: transparent !important;
            box-shadow: none !important;
            transform: none !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
