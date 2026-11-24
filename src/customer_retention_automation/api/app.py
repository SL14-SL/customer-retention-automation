"""FastAPI application for synthetic customer retention automation."""

import os
import sqlite3
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from customer_retention_automation.retention.round_cases import (
    RoundCaseConflictError,
    create_round_case,
    decide_round_case,
    get_round_case,
    list_round_cases,
    mark_round_dispatch_failed,
    register_round_approval_link,
)
from customer_retention_automation.retention.round_email import (
    create_round_email_job,
    list_round_email_jobs,
    simulate_round_email,
)
from customer_retention_automation.simulation.churn import (
    list_churn_events,
)
from customer_retention_automation.simulation.evaluations import (
    list_customer_evaluations,
    list_evaluated_customers,
    list_evaluation_rounds,
)

app = FastAPI(
    title="Customer Retention Automation API",
    description=(
        "Synthetic churn simulation, round-specific retention "
        "cases, human approvals and simulated emails."
    ),
)


def churn_simulation_database() -> Path:
    """Return the SQLite database used for the retention simulation."""
    return Path(
        os.getenv(
            "CHURN_SIM_DATABASE",
            "data/retention_churn_sim.sqlite",
        )
    )


class RoundCaseRequest(BaseModel):
    """Request to create a retention case."""

    round_id: str = Field(min_length=1)
    customer_id: str = Field(min_length=1)
    action: Literal["offer_discount", "send_email", "no_action"]


class RoundCaseDecisionRequest(BaseModel):
    """Decision from a registered n8n approval execution."""

    status: Literal["approved", "rejected"]
    approval_execution_id: str = Field(min_length=1)


class RoundApprovalLinkRequest(BaseModel):
    """Register an n8n approval form for a discount case."""

    approval_url: str = Field(min_length=1)
    approval_execution_id: str = Field(min_length=1)
    proposed_discount_percent: float = Field(gt=0, le=100)


@app.get("/health")
def health() -> dict[str, str]:
    """Check whether the API process is running."""
    return {"status": "ok"}


@app.get("/retention/churn-simulation/overview")
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


@app.get("/retention/churn-simulation/customers")
def get_churn_simulation_customers() -> dict:
    """List all customers included in the churn simulation."""
    customers = list_evaluated_customers(churn_simulation_database())

    return {
        "count": len(customers),
        "customers": customers,
    }


@app.get("/retention/churn-simulation/customers/{customer_id}")
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


@app.get("/retention/churn-simulation/rounds/{round_id}/customers")
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


@app.post("/retention/round-cases", status_code=201)
def create_retention_round_case(payload: RoundCaseRequest) -> dict:
    """Create a customer case for one evaluation round."""
    database = churn_simulation_database()

    try:
        created = create_round_case(
            database=database,
            round_id=payload.round_id,
            customer_id=payload.customer_id,
            action=payload.action,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    if not created:
        raise HTTPException(
            status_code=409,
            detail="Retention case already exists for this round",
        )

    case_id = f"{payload.round_id}:{payload.customer_id}"
    case = get_round_case(database, case_id)

    if case is None:
        raise HTTPException(
            status_code=500,
            detail="Created case could not be retrieved",
        )

    return case


@app.get("/retention/round-cases")
def get_retention_round_cases(
    round_id: str | None = None,
    customer_id: str | None = None,
) -> dict:
    """List cases, optionally filtered by round and customer."""
    cases = list_round_cases(
        churn_simulation_database(),
        round_id=round_id,
        customer_id=customer_id,
    )

    return {
        "count": len(cases),
        "cases": cases,
    }


@app.get("/retention/round-cases/{case_id}")
def get_retention_round_case(case_id: str) -> dict:
    """Retrieve one round-specific retention case."""
    case = get_round_case(
        churn_simulation_database(),
        case_id,
    )

    if case is None:
        raise HTTPException(
            status_code=404,
            detail="Retention case not found",
        )

    return case


@app.post("/retention/round-cases/{case_id}/decision")
def decide_retention_round_case(
    case_id: str,
    payload: RoundCaseDecisionRequest,
) -> dict:
    """Approve or reject a registered discount proposal."""
    try:
        return decide_round_case(
            database=churn_simulation_database(),
            case_id=case_id,
            decision=payload.status,
            approval_execution_id=payload.approval_execution_id,
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc
    except RoundCaseConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc


@app.post(
    "/retention/round-cases/{case_id}/email-job",
    status_code=201,
)
def create_retention_round_email_job(case_id: str) -> dict:
    """Create an email job for an eligible retention case."""
    try:
        job, created = create_round_email_job(
            churn_simulation_database(),
            case_id,
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc
    except RoundCaseConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    if not created:
        raise HTTPException(
            status_code=409,
            detail="Email job already exists for this case",
        )

    return job


@app.post("/retention/round-cases/{case_id}/simulate-email")
def simulate_retention_round_email(case_id: str) -> dict:
    """Simulate delivery and complete an eligible retention case."""
    try:
        job, simulated = simulate_round_email(
            churn_simulation_database(),
            case_id,
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc
    except RoundCaseConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    return {
        **job,
        "simulated_now": simulated,
    }


@app.get("/retention/round-email-jobs")
def get_retention_round_email_jobs(
    customer_id: str | None = None,
) -> dict:
    """List round-specific simulated email jobs."""
    jobs = list_round_email_jobs(
        churn_simulation_database(),
        customer_id=customer_id,
    )

    return {
        "count": len(jobs),
        "jobs": jobs,
    }


@app.post("/retention/round-cases/{case_id}/approval-link")
def register_retention_round_approval_link(
    case_id: str,
    payload: RoundApprovalLinkRequest,
) -> dict:
    """Register the n8n execution handling a discount approval."""
    try:
        created = register_round_approval_link(
            database=churn_simulation_database(),
            case_id=case_id,
            approval_url=payload.approval_url,
            approval_execution_id=payload.approval_execution_id,
            proposed_discount_percent=payload.proposed_discount_percent,
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc
    except RoundCaseConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    return {
        "case_id": case_id,
        "registered_now": created,
    }


@app.post("/retention/round-cases/{case_id}/dispatch-failed")
def mark_retention_round_dispatch_failed(case_id: str) -> dict:
    """Record a failed approval dispatch."""
    try:
        return mark_round_dispatch_failed(
            churn_simulation_database(),
            case_id,
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc
    except RoundCaseConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc
