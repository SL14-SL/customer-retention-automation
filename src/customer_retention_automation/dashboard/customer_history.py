"""Customer-level risk and retention action history."""

import altair as alt
import pandas as pd
import streamlit as st

from customer_retention_automation.dashboard.api_client import (
    RetentionAPIError,
    fetch_churn_customer,
)
from customer_retention_automation.dashboard.data_processing import (
    customer_case_history,
)
from customer_retention_automation.dashboard.theme import GREEN, TERRACOTTA

ACTION_LABELS = {
    "no_action": "No action",
    "send_email": "Customer outreach",
    "offer_discount": "Discount offer",
}


def render_customer_history(cases: list[dict]) -> None:
    """Render risk evaluations and workflow cases for a customer."""
    st.subheader("Customer History")
    st.caption(
        "Individual churn-risk evaluations, simulated cancellations "
        "and executed retention actions across simulation rounds."
    )

    customer_ids = sorted({case["customer_id"] for case in cases})

    if not customer_ids:
        st.info("No customer cases available.")
        return

    default_index = (
        customer_ids.index("synthetic-0121") if "synthetic-0121" in customer_ids else 0
    )

    selected_customer = st.selectbox(
        "Customer",
        customer_ids,
        index=default_index,
        key="history_customer",
    )

    try:
        customer_data = fetch_churn_customer(selected_customer)
    except (RetentionAPIError, KeyError, ValueError) as exc:
        st.error(f"Unable to load customer history: {exc}")
        return

    evaluations = customer_data.get("evaluations", [])
    history = customer_case_history(cases, selected_customer)

    churn_status = customer_data.get("status", "unknown")
    churn_day = customer_data.get("churn_day")

    if not evaluations:
        st.info("No risk evaluations recorded for this customer.")
        return

    risk_frame = pd.DataFrame(evaluations)
    risk_frame = risk_frame.sort_values("simulation_day")

    risk_frame["Risk (%)"] = risk_frame["churn_probability"].astype(float) * 100

    first_risk = float(risk_frame.iloc[0]["Risk (%)"])
    latest_risk = float(risk_frame.iloc[-1]["Risk (%)"])

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Customer status", churn_status.capitalize())

    with col2:
        st.metric("Latest churn risk", f"{latest_risk:.1f}%")

    with col3:
        st.metric(
            "Risk change",
            f"{latest_risk - first_risk:+.1f} pp",
        )

    with col4:
        st.metric("Evaluations", len(evaluations))

    if churn_day is not None:
        st.warning(
            f"This customer cancelled on simulated day {churn_day}. "
            "No further regular evaluations are available after churn."
        )

    st.divider()
    st.markdown("#### Churn risk development")

    chart = (
        alt.Chart(risk_frame)
        .mark_line(
            point=True,
            strokeWidth=3,
            color=GREEN,
        )
        .encode(
            x=alt.X(
                "simulation_day:Q",
                title="Simulation day",
                scale=alt.Scale(domain=[0, 60]),
                axis=alt.Axis(values=[0, 30, 60], labelAngle=0),
            ),
            y=alt.Y(
                "Risk (%):Q",
                title="Churn risk (%)",
                scale=alt.Scale(domain=[0, 100]),
            ),
            tooltip=[
                alt.Tooltip(
                    "simulation_day:Q",
                    title="Day",
                ),
                alt.Tooltip(
                    "Risk (%):Q",
                    title="Churn risk (%)",
                    format=".2f",
                ),
            ],
        )
        .properties(height=300)
    )

    if churn_day is not None:
        marker_frame = pd.DataFrame({"Churn day": [churn_day]})

        churn_marker = (
            alt.Chart(marker_frame)
            .mark_rule(
                color=TERRACOTTA,
                strokeDash=[6, 4],
                strokeWidth=2,
            )
            .encode(
                x=alt.X("Churn day:Q"),
                tooltip=["Churn day:Q"],
            )
        )

        chart = alt.layer(chart, churn_marker)

    st.altair_chart(chart, width="stretch")

    st.divider()
    st.markdown("#### Evaluation history")

    evaluation_rows = pd.DataFrame(
        [
            {
                "Round": evaluation["round_id"],
                "Day": evaluation["simulation_day"],
                "Churn risk (%)": (float(evaluation["churn_probability"]) * 100),
                "Suggested action": ACTION_LABELS.get(
                    evaluation["action"],
                    evaluation["action"],
                ),
                "Evaluated": evaluation.get("created_at"),
            }
            for evaluation in evaluations
        ]
    )

    st.dataframe(
        evaluation_rows,
        hide_index=True,
        width="stretch",
        column_config={
            "Round": st.column_config.TextColumn("Round", alignment="left"),
            "Day": st.column_config.NumberColumn("Day", alignment="left"),
            "Churn risk (%)": st.column_config.NumberColumn(
                "Churn risk (%)",
                format="%.2f%%",
                alignment="left",
            ),
            "Suggested action": st.column_config.TextColumn(
                "Suggested action", alignment="left"
            ),
            "Evaluated": st.column_config.TextColumn("Evaluated", alignment="left"),
        },
    )

    st.divider()
    st.markdown("#### Retention workflow history")

    if not history:
        st.info("No retention workflow cases recorded.")
    else:
        action_rows = pd.DataFrame(
            [
                {
                    "Round": case["round_id"],
                    "Action": ACTION_LABELS.get(case["action"], case["action"]),
                    "Status": case["status"].replace("_", " ").capitalize(),
                    "Discount (%)": case.get("proposed_discount_percent"),
                    "Updated": case.get("updated_at"),
                }
                for case in history
            ]
        )

        st.dataframe(
            action_rows,
            hide_index=True,
            width="stretch",
            column_config={
                "Round": st.column_config.TextColumn("Round", alignment="left"),
                "Action": st.column_config.TextColumn("Action", alignment="left"),
                "Status": st.column_config.TextColumn("Status", alignment="left"),
                "Discount (%)": st.column_config.NumberColumn(
                    "Discount (%)",
                    format="%.1f%%",
                    alignment="left",
                ),
                "Updated": st.column_config.TextColumn("Updated", alignment="left"),
            },
        )

    st.caption(
        "Risk changes and cancellations are synthetic. "
        "No causal effect of retention measures is implied."
    )
