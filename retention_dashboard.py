"""Streamlit dashboard for the synthetic customer retention demo."""

import streamlit as st

from customer_retention_automation.dashboard.api_client import (
    RetentionAPIError,
    fetch_all_round_cases,
    fetch_round_email_jobs,
)
from customer_retention_automation.dashboard.approvals import (
    render_approvals,
)
from customer_retention_automation.dashboard.cases import (
    render_cases,
)
from customer_retention_automation.dashboard.customer_history import (
    render_customer_history,
)
from customer_retention_automation.dashboard.emails import (
    render_emails,
)
from customer_retention_automation.dashboard.overview import (
    render_overview,
)

st.set_page_config(
    page_title="Retention Center",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)


def main() -> None:
    """Render the retention dashboard."""
    header_col, refresh_col = st.columns([5, 1])

    with header_col:
        st.title("Retention Center")

    with refresh_col:
        st.write("")
        if st.button("↻ Refresh", width="stretch"):
            st.rerun()

    try:
        cases = fetch_all_round_cases()
        email_jobs = fetch_round_email_jobs()
    except (
        RetentionAPIError,
        KeyError,
        ValueError,
        TypeError,
    ) as exc:
        st.error(f"Unable to load retention data: {exc}")
        st.stop()

    (
        overview_tab,
        cases_tab,
        approvals_tab,
        emails_tab,
        history_tab,
    ) = st.tabs(
        [
            "Overview",
            "Retention Cases",
            "Approval Decisions",
            "Email Outbox",
            "Customer History",
        ]
    )

    with overview_tab:
        render_overview(cases, email_jobs)

    with cases_tab:
        render_cases(cases)

    with approvals_tab:
        render_approvals(cases)

    with emails_tab:
        render_emails(email_jobs)

    with history_tab:
        render_customer_history(cases)

    st.divider()
    st.caption(
        "Local portfolio demonstration · "
        "Fictional customers and synthetic churn risks · "
        "No real emails sent or cancellations prevented"
    )


if __name__ == "__main__":
    main()
