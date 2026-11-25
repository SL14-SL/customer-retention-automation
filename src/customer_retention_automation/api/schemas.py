"""Request models for the customer retention API."""

from typing import Literal

from pydantic import BaseModel, Field


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
