"""Data preparation and metrics for the retention dashboard."""

from collections import Counter
from typing import Any

from customer_retention_automation.dashboard.api_client import ROUND_IDS

ACTIONS = ("no_action", "send_email", "offer_discount")


def summarize_round_cases(cases: list[dict]) -> dict[str, Any]:
    """Calculate retention case metrics for one dataset."""
    actions = Counter(case["action"] for case in cases)
    statuses = Counter(case["status"] for case in cases)

    discounts = [case for case in cases if case["action"] == "offer_discount"]

    discount_statuses = Counter(case["status"] for case in discounts)

    return {
        "total": len(cases),
        "no_action": actions["no_action"],
        "send_email": actions["send_email"],
        "offer_discount": actions["offer_discount"],
        "completed": statuses["completed"],
        "rejected": statuses["rejected"],
        "pending": statuses["pending"],
        "dispatch_failed": statuses["dispatch_failed"],
        "approved_discounts": discount_statuses["completed"],
        "rejected_discounts": discount_statuses["rejected"],
        "pending_discounts": discount_statuses["pending"],
        "approval_rate": (
            discount_statuses["completed"]
            / (discount_statuses["completed"] + discount_statuses["rejected"])
            if (discount_statuses["completed"] + discount_statuses["rejected"])
            else 0.0
        ),
    }


def summarize_all_rounds(
    cases: list[dict],
) -> list[dict[str, Any]]:
    """Create one summary row per simulation round."""
    summaries = []

    for round_id in ROUND_IDS:
        round_cases = [case for case in cases if case["round_id"] == round_id]

        summary = summarize_round_cases(round_cases)
        summary["round_id"] = round_id
        summary["simulation_day"] = int(round_id.split("-")[1])

        summaries.append(summary)

    return summaries


def summarize_total(cases: list[dict]) -> dict[str, Any]:
    """Calculate metrics across all simulation rounds."""
    return summarize_round_cases(cases)


def prepare_case_rows(cases: list[dict]) -> list[dict]:
    """Prepare display rows for the cases table."""
    rows = []

    for case in cases:
        rows.append(
            {
                "Round": case["round_id"],
                "Customer": case["customer_id"],
                "Action": case["action"],
                "Status": case["status"],
                "Churn risk (%)": round(
                    float(case["churn_probability"]) * 100,
                    2,
                ),
                "Discount (%)": case.get("proposed_discount_percent"),
                "Created": case.get("created_at"),
                "Updated": case.get("updated_at"),
            }
        )

    return rows


def prepare_approval_rows(cases: list[dict]) -> list[dict]:
    """Prepare discount cases for the approval overview."""
    rows = []

    for case in cases:
        if case["action"] != "offer_discount":
            continue

        status = case["status"]

        if status == "completed":
            decision = "Approved"
        elif status == "rejected":
            decision = "Rejected"
        elif status == "pending":
            decision = "Pending"
        else:
            decision = status.replace("_", " ").title()

        rows.append(
            {
                "Round": case["round_id"],
                "Customer": case["customer_id"],
                "Decision": decision,
                "Churn risk (%)": round(
                    float(case["churn_probability"]) * 100,
                    2,
                ),
                "Discount (%)": case.get("proposed_discount_percent"),
                "Execution ID": case.get("approval_execution_id"),
            }
        )

    return rows


def customer_case_history(
    cases: list[dict],
    customer_id: str,
) -> list[dict]:
    """Return a customer's cases ordered by simulation day."""
    matching = [case for case in cases if case["customer_id"] == customer_id]

    return sorted(
        matching,
        key=lambda case: int(case["round_id"].split("-")[1]),
    )
