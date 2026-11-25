"""API endpoints for simulated retention emails."""

from fastapi import APIRouter, HTTPException

from customer_retention_automation.api.config import (
    churn_simulation_database,
)
from customer_retention_automation.retention.round_cases import (
    RoundCaseConflictError,
)
from customer_retention_automation.retention.round_email import (
    create_round_email_job,
    list_round_email_jobs,
    simulate_round_email,
)

router = APIRouter(
    tags=["Retention Emails"],
)


@router.post(
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


@router.post("/retention/round-cases/{case_id}/simulate-email")
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


@router.get("/retention/round-email-jobs")
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
