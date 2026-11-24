"""Overview page for the synthetic retention simulation."""

import altair as alt
import pandas as pd
import streamlit as st

from customer_retention_automation.dashboard.data_processing import (
    summarize_all_rounds,
    summarize_total,
)
from customer_retention_automation.dashboard.theme import (
    ACTION_COLORS,
    DECISION_COLORS,
    GREEN,
)


def style_chart(chart: alt.Chart) -> alt.Chart:
    """Apply readable typography to dashboard charts."""
    return chart.configure_axis(
        titleFontSize=16,
        labelFontSize=15,
        titlePadding=14,
        labelPadding=8,
    ).configure_legend(
        titleFontSize=16,
        labelFontSize=15,
        labelLimit=250,
        symbolSize=160,
    )


def render_overview(
    cases: list[dict],
    email_jobs: list[dict],
) -> None:
    """Render the overall retention simulation results."""
    totals = summarize_total(cases)
    rounds = summarize_all_rounds(cases)

    st.subheader("Simulation Overview")
    st.caption(
        "Three simulation rounds with fictional customers, "
        "synthetic churn risks and simulated retention actions."
    )

    simulated_emails = sum(job["status"] == "simulated" for job in email_jobs)

    # Main KPIs
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Processed cases", totals["total"])

    with col2:
        st.metric(
            "Approved discounts",
            totals["approved_discounts"],
        )

    with col3:
        st.metric(
            "Rejected discounts",
            totals["rejected_discounts"],
        )

    with col4:
        st.metric("Simulated emails", simulated_emails)

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Pending cases", totals["pending"])

    with col2:
        st.metric(
            "Discount approval rate",
            f"{totals['approval_rate']:.1%}",
        )

    with col3:
        st.metric(
            "Failed dispatches",
            totals["dispatch_failed"],
        )

    st.divider()

    # Round-level data
    round_frame = pd.DataFrame(rounds)

    round_frame["Round"] = round_frame["simulation_day"].map(lambda day: f"Day {day}")

    # Charts
    left, right = st.columns(2, gap="large")

    with left:
        st.markdown("#### Customers evaluated per round")

        customers_chart = (
            alt.Chart(round_frame)
            .mark_line(
                point=True,
                strokeWidth=3,
                color=GREEN,
            )
            .encode(
                x=alt.X(
                    "simulation_day:O",
                    title="Simulation day",
                    sort=[0, 30, 60],
                    axis=alt.Axis(labelAngle=0),
                ),
                y=alt.Y(
                    "total:Q",
                    title="Customers",
                    scale=alt.Scale(zero=True),
                ),
                tooltip=[
                    alt.Tooltip(
                        "Round:N",
                        title="Round",
                    ),
                    alt.Tooltip(
                        "total:Q",
                        title="Customers",
                    ),
                ],
            )
            .properties(height=300)
        )

        customers_chart = style_chart(customers_chart)

        st.altair_chart(
            customers_chart,
            width="stretch",
        )

        st.caption(
            "Each round contains the customers still active "
            "at the beginning of that evaluation. "
            "Customer counts are not unique across rounds."
        )

    with right:
        st.markdown("#### Retention actions per round")

        actions_frame = round_frame[
            [
                "Round",
                "no_action",
                "send_email",
                "offer_discount",
            ]
        ].melt(
            id_vars="Round",
            var_name="Action",
            value_name="Cases",
        )

        actions_frame["Action"] = actions_frame["Action"].map(
            {
                "no_action": "No action",
                "send_email": "Customer outreach",
                "offer_discount": "Discount offer",
            }
        )

        actions_chart = (
            alt.Chart(actions_frame)
            .mark_bar()
            .encode(
                x=alt.X(
                    "Round:N",
                    sort=["Day 0", "Day 30", "Day 60"],
                    title="Simulation round",
                    axis=alt.Axis(labelAngle=0),
                ),
                y=alt.Y(
                    "Cases:Q",
                    title="Cases",
                ),
                color=alt.Color(
                    "Action:N",
                    title=None,
                    scale=alt.Scale(
                        domain=list(ACTION_COLORS),
                        range=list(ACTION_COLORS.values()),
                    ),
                    legend=alt.Legend(
                        orient="top",
                        direction="horizontal",
                        columns=3,
                        labelFontSize=15,
                        symbolSize=160,
                        labelLimit=250,
                    ),
                ),
                tooltip=[
                    "Round:N",
                    "Action:N",
                    "Cases:Q",
                ],
            )
            .properties(height=300)
        )
        actions_chart = style_chart(actions_chart)

        st.altair_chart(
            actions_chart,
            width="stretch",
        )

    st.divider()

    # Approval decisions per round
    st.markdown("#### Discount approvals")

    approval_frame = round_frame[
        [
            "Round",
            "approved_discounts",
            "rejected_discounts",
        ]
    ].melt(
        id_vars="Round",
        var_name="Decision",
        value_name="Cases",
    )

    approval_frame["Decision"] = approval_frame["Decision"].map(
        {
            "approved_discounts": "Approved",
            "rejected_discounts": "Rejected",
        }
    )

    approvals_chart = (
        alt.Chart(approval_frame)
        .mark_bar()
        .encode(
            x=alt.X(
                "Round:N",
                sort=["Day 0", "Day 30", "Day 60"],
                title="Simulation round",
                axis=alt.Axis(labelAngle=0),
            ),
            y=alt.Y(
                "Cases:Q",
                title="Discount offers",
            ),
            color=alt.Color(
                "Decision:N",
                title="Decision",
                scale=alt.Scale(
                    domain=list(DECISION_COLORS),
                    range=list(DECISION_COLORS.values()),
                ),
            ),
            tooltip=[
                "Round:N",
                "Decision:N",
                "Cases:Q",
            ],
        )
        .properties(height=260)
    )
    approvals_chart = style_chart(approvals_chart)

    st.altair_chart(
        approvals_chart,
        width="stretch",
    )

    st.divider()

    # Summary table
    st.markdown("#### Round summary")

    summary_table = round_frame[
        [
            "Round",
            "total",
            "no_action",
            "send_email",
            "offer_discount",
            "approved_discounts",
            "rejected_discounts",
            "pending",
        ]
    ].rename(
        columns={
            "total": "Customers",
            "no_action": "No action",
            "send_email": "Outreach",
            "offer_discount": "Discount offers",
            "approved_discounts": "Approved",
            "rejected_discounts": "Rejected",
            "pending": "Pending",
        }
    )

    st.dataframe(
        summary_table,
        hide_index=True,
        width="stretch",
        column_config={
            column: st.column_config.TextColumn(
                column,
                alignment="left",
            )
            for column in summary_table.columns
        },
    )

    st.info(
        "All churn events are simulated independently of "
        "retention actions. Approved discounts and simulated "
        "emails do not demonstrate prevented cancellations."
    )
