"""Searchable retention case history."""

import pandas as pd
import streamlit as st

from customer_retention_automation.dashboard.data_processing import (
    prepare_case_rows,
)

ROUND_OPTIONS = ["All rounds", "day-000", "day-030", "day-060"]

ACTION_LABELS = {
    "no_action": "No action",
    "send_email": "Customer outreach",
    "offer_discount": "Discount offer",
}

STATUS_LABELS = {
    "pending": "Pending",
    "approved": "Approved",
    "rejected": "Rejected",
    "completed": "Completed",
    "dispatch_failed": "Dispatch failed",
}


def render_cases(cases: list[dict]) -> None:
    """Render the round-specific retention case history."""
    st.subheader("Retention Cases")
    st.caption(
        "Browse customer actions across all three simulation rounds. "
        "A customer can have one case in each round."
    )

    search_col, round_col = st.columns([2, 1])

    with search_col:
        search = st.text_input(
            "Customer ID",
            placeholder="Search synthetic customers...",
            key="cases_customer_search",
        )

    with round_col:
        selected_round = st.selectbox(
            "Simulation round",
            ROUND_OPTIONS,
            key="cases_round",
        )

    action_col, status_col = st.columns(2)

    with action_col:
        selected_action = st.selectbox(
            "Action",
            ["All actions", *ACTION_LABELS.values()],
            key="cases_action",
        )

    with status_col:
        selected_status = st.selectbox(
            "Status",
            ["All statuses", *STATUS_LABELS.values()],
            key="cases_status",
        )

    visible_cases = [
        case
        for case in cases
        if search.lower() in case["customer_id"].lower()
        and (selected_round == "All rounds" or case["round_id"] == selected_round)
        and (
            selected_action == "All actions"
            or ACTION_LABELS.get(case["action"]) == selected_action
        )
        and (
            selected_status == "All statuses"
            or STATUS_LABELS.get(case["status"]) == selected_status
        )
    ]

    total_col, completed_col, pending_col = st.columns(3)

    with total_col:
        st.metric("Matching cases", len(visible_cases))

    with completed_col:
        st.metric(
            "Completed",
            sum(case["status"] == "completed" for case in visible_cases),
        )

    with pending_col:
        st.metric(
            "Pending",
            sum(case["status"] == "pending" for case in visible_cases),
        )

    st.caption(f"Showing {len(visible_cases)} of {len(cases)} cases")

    if not visible_cases:
        st.info("No cases match the selected filters.")
        return

    rows = prepare_case_rows(visible_cases)
    frame = pd.DataFrame(rows)

    frame["Action"] = frame["Action"].map(ACTION_LABELS)
    frame["Status"] = frame["Status"].map(STATUS_LABELS)

    frame = frame.sort_values(
        ["Round", "Customer"],
        ascending=[True, True],
        kind="stable",
    )

    st.dataframe(
        frame,
        hide_index=True,
        width="stretch",
        column_config={
            **{
                column: st.column_config.TextColumn(
                    column,
                    alignment="left",
                )
                for column in frame.columns
                if column not in {"Churn risk (%)", "Discount (%)"}
            },
            "Churn risk (%)": st.column_config.NumberColumn(
                "Churn risk (%)",
                format="%.2f%%",
                alignment="left",
            ),
            "Discount (%)": st.column_config.NumberColumn(
                "Discount (%)",
                format="%.1f%%",
                alignment="left",
            ),
        },
    )

    csv_data = frame.to_csv(index=False).encode("utf-8")

    st.download_button(
        "Export filtered cases as CSV",
        data=csv_data,
        file_name="retention_cases.csv",
        mime="text/csv",
        key="cases_download",
    )

    st.caption(
        "All customer records and risk scores are synthetic. "
        "Completed means the chosen workflow action was processed."
    )
