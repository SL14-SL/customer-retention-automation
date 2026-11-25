"""API endpoints for round-specific retention cases."""

from fastapi import APIRouter, Depends, HTTPException

from customer_retention_automation.api.config import (
    churn_simulation_database,
)
from customer_retention_automation.api.schemas import (
    RoundApprovalLinkRequest,
    RoundCaseDecisionRequest,
    RoundCaseRequest,
)
from customer_retention_automation.api.security import (
    require_api_key,
)
from customer_retention_automation.retention.round_cases import (
    RoundCaseConflictError,
    create_round_case,
    decide_round_case,
    get_round_case,
    list_round_cases,
    mark_round_dispatch_failed,
    register_round_approval_link,
)

router = APIRouter(
    prefix="/retention/round-cases",
    tags=["Retention Cases"],
)


@router.post(
    "",
    status_code=201,
    dependencies=[Depends(require_api_key)],
)
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


@router.get("")
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


@router.get("/{case_id}")
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


@router.post(
    "/{case_id}/decision",
    dependencies=[Depends(require_api_key)],
)
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


@router.post(
    "/{case_id}/approval-link",
    dependencies=[Depends(require_api_key)],
)
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


@router.post(
    "/{case_id}/dispatch-failed",
    dependencies=[Depends(require_api_key)],
)
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
