"""Approval decisions for retention discount offers."""

import altair as alt
import pandas as pd
import streamlit as st

from customer_retention_automation.dashboard.data_processing import (
    prepare_approval_rows,
)
from customer_retention_automation.dashboard.theme import (
    DECISION_COLORS,
)

ROUND_OPTIONS = ["All rounds", "day-000", "day-030", "day-060"]


def render_approvals(cases: list[dict]) -> None:
    """Render discount decision metrics and searchable history."""
    st.subheader("Approval Decisions")
    st.caption(
        "Human-approval workflow simulation for proposed customer retention discounts."
    )

    discount_cases = [case for case in cases if case["action"] == "offer_discount"]

    round_col, decision_col = st.columns(2)

    with round_col:
        selected_round = st.selectbox(
            "Simulation round",
            ROUND_OPTIONS,
            key="approvals_round",
        )

    with decision_col:
        selected_decision = st.selectbox(
            "Decision",
            [
                "All decisions",
                "Approved",
                "Rejected",
                "Pending",
                "Dispatch failed",
            ],
            key="approvals_decision",
        )

    rows = prepare_approval_rows(discount_cases)

    visible_rows = [
        row
        for row in rows
        if (selected_round == "All rounds" or row["Round"] == selected_round)
        and (
            selected_decision == "All decisions" or row["Decision"] == selected_decision
        )
    ]

    approved = sum(row["Decision"] == "Approved" for row in visible_rows)

    rejected = sum(row["Decision"] == "Rejected" for row in visible_rows)

    pending = sum(row["Decision"] == "Pending" for row in visible_rows)

    decided = approved + rejected
    approval_rate = approved / decided if decided else 0.0

    metric_cols = st.columns(4)

    with metric_cols[0]:
        st.metric("Discount offers", len(visible_rows))

    with metric_cols[1]:
        st.metric("Approved", approved)

    with metric_cols[2]:
        st.metric("Rejected", rejected)

    with metric_cols[3]:
        st.metric("Approval rate", f"{approval_rate:.1%}")

    if pending:
        st.warning(f"{pending} discount proposals are awaiting decisions.")

    st.divider()

    st.markdown("#### Decision distribution")

    decision_frame = pd.DataFrame(
        [
            {"Decision": "Approved", "Cases": approved},
            {"Decision": "Rejected", "Cases": rejected},
        ]
    )

    if decided:
        chart = (
            alt.Chart(decision_frame)
            .mark_bar()
            .encode(
                x=alt.X(
                    "Decision:N",
                    title=None,
                    sort=["Approved", "Rejected"],
                    axis=alt.Axis(labelAngle=0),
                ),
                y=alt.Y(
                    "Cases:Q",
                    title="Discount offers",
                ),
                color=alt.Color(
                    "Decision:N",
                    scale=alt.Scale(
                        domain=list(DECISION_COLORS),
                        range=list(DECISION_COLORS.values()),
                    ),
                    legend=None,
                ),
                tooltip=[
                    "Decision:N",
                    "Cases:Q",
                ],
            )
            .properties(height=250)
        )

        st.altair_chart(chart, width="stretch")
    else:
        st.info("No recorded decisions for this selection.")

    st.divider()

    st.markdown("#### Discount case history")

    search = st.text_input(
        "Search customer ID",
        placeholder="Search discount cases...",
        key="approvals_customer_search",
    )

    filtered_rows = [
        row for row in visible_rows if search.lower() in row["Customer"].lower()
    ]

    st.caption(f"{len(filtered_rows)} of {len(visible_rows)} offers shown")

    if not filtered_rows:
        st.info("No discount offers match the selected filters.")
        return

    frame = pd.DataFrame(filtered_rows).sort_values(
        ["Round", "Customer"],
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

    st.caption(
        "Approved discounts appear as completed cases after "
        "their simulated emails have been processed. "
        "Approval decisions in this demo are simulated."
    )
