from __future__ import annotations

from frontend.pages.auth import render_auth_page
from frontend.pages.backtest import render_backtest_page
from frontend.pages.generate import render_auto_page
from frontend.pages.home import render_home_page
from frontend.pages.market import render_market_page
from frontend.pages.profile import render_profile_page
from frontend.pages.records import render_history_page
from frontend.pages.stock_detail import render_stock_detail_page
from frontend.pages.upload import render_upload_page
from frontend.pages.users import render_user_management_page
from frontend.shared import (
    get_current_page,
    initialize_state,
    inject_css,
    is_authenticated,
    load_health_status,
    render_sidebar,
    render_topbar,
)


def main() -> None:
    inject_css()
    initialize_state()

    if not is_authenticated():
        render_auth_page()
        return

    current_page = get_current_page()
    health, health_error = load_health_status()

    render_sidebar(current_page, health, health_error)
    render_topbar(current_page, health, health_error)

    if current_page == "home":
        render_home_page(health, health_error)
    elif current_page == "market":
        render_market_page()
    elif current_page == "stock_detail":
        render_stock_detail_page()
    elif current_page == "upload":
        render_upload_page()
    elif current_page == "generate":
        render_auto_page()
    elif current_page == "records":
        render_history_page()
    elif current_page == "backtest":
        render_backtest_page()
    elif current_page == "profile":
        render_profile_page()
    elif current_page == "users":
        render_user_management_page()
    else:
        render_home_page(health, health_error)
