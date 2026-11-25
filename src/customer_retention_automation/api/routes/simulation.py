"""API endpoints for synthetic churn simulation data."""

import sqlite3

from fastapi import APIRouter, HTTPException

from customer_retention_automation.api.config import (
    churn_simulation_database,
)
from customer_retention_automation.simulation.churn import (
    list_churn_events,
)
from customer_retention_automation.simulation.evaluations import (
    list_customer_evaluations,
    list_evaluated_customers,
    list_evaluation_rounds,
)

router = APIRouter(
    prefix="/retention/churn-simulation",
    tags=["Simulation"],
)


@router.get("/overview")
def get_churn_simulation_overview() -> dict:
    """Return evaluation rounds and simulated cancellation counts."""
    database = churn_simulation_database()

    rounds = list_evaluation_rounds(database)
    events = list_churn_events(database)
    customer_ids = list_evaluated_customers(database)

    population = len(customer_ids)

    round_summaries = [
        {
            **round_data,
            "new_churn_events": sum(
                event["churn_day"] == round_data["simulation_day"] for event in events
            ),
            "total_churn_events": sum(
                event["churn_day"] <= round_data["simulation_day"] for event in events
            ),
        }
        for round_data in rounds
    ]

    latest_day = rounds[-1]["simulation_day"] if rounds else None

    churned = (
        sum(event["churn_day"] <= latest_day for event in events)
        if latest_day is not None
        else 0
    )

    return {
        "population": population,
        "latest_simulation_day": latest_day,
        "active_customers": population - churned,
        "churned_customers": churned,
        "rounds": round_summaries,
    }


@router.get("/customers")
def get_churn_simulation_customers() -> dict:
    """List all customers included in the churn simulation."""
    customers = list_evaluated_customers(churn_simulation_database())

    return {
        "count": len(customers),
        "customers": customers,
    }


@router.get("/customers/{customer_id}")
def get_churn_simulation_customer(customer_id: str) -> dict:
    """Return customer evaluations and simulated churn status."""
    database = churn_simulation_database()

    evaluations = list_customer_evaluations(
        database,
        customer_id,
    )

    if not evaluations:
        raise HTTPException(
            status_code=404,
            detail="Customer has no evaluation history",
        )

    rounds = list_evaluation_rounds(database)
    latest_day = rounds[-1]["simulation_day"]

    event = next(
        (
            item
            for item in list_churn_events(database)
            if item["customer_id"] == customer_id and item["churn_day"] <= latest_day
        ),
        None,
    )

    return {
        "customer_id": customer_id,
        "status": "churned" if event else "active",
        "churn_day": event["churn_day"] if event else None,
        "latest_simulation_day": latest_day,
        "count": len(evaluations),
        "evaluations": evaluations,
    }


@router.get("/rounds/{round_id}/customers")
def get_simulation_round_customers(round_id: str) -> dict:
    """Return evaluated customers and actions for one round."""
    database = churn_simulation_database()

    with sqlite3.connect(database) as connection:
        connection.row_factory = sqlite3.Row

        round_row = connection.execute(
            """
            SELECT round_id, simulation_day
            FROM retention_evaluation_rounds
            WHERE round_id = ?
            """,
            (round_id,),
        ).fetchone()

        if round_row is None:
            raise HTTPException(
                status_code=404,
                detail="Simulation round not found",
            )

        rows = connection.execute(
            """
            SELECT
                round_id,
                customer_id,
                churn_probability,
                action
            FROM retention_evaluations
            WHERE round_id = ?
            ORDER BY customer_id
            """,
            (round_id,),
        ).fetchall()

    return {
        "round_id": round_row["round_id"],
        "simulation_day": round_row["simulation_day"],
        "count": len(rows),
        "customers": [dict(row) for row in rows],
    }
