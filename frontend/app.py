from __future__ import annotations

from frontend.pages.backtest import render_backtest_page
from frontend.pages.generate import render_auto_page
from frontend.pages.home import render_home_page
from frontend.pages.market import render_market_page
from frontend.pages.records import render_history_page
from frontend.pages.upload import render_upload_page
from frontend.shared import (
    get_current_page,
    initialize_state,
    inject_css,
    load_health_status,
    render_sidebar,
    render_topbar,
)


def main() -> None:
    inject_css()
    initialize_state()

    current_page = get_current_page()
    health, health_error = load_health_status()

    render_sidebar(current_page, health, health_error)
    render_topbar(current_page, health, health_error)

    if current_page == "home":
        render_home_page(health, health_error)
    elif current_page == "market":
        render_market_page()
    elif current_page == "upload":
        render_upload_page()
    elif current_page == "generate":
        render_auto_page()
    elif current_page == "records":
        render_history_page()
    elif current_page == "backtest":
        render_backtest_page()
    else:
        render_home_page(health, health_error)
