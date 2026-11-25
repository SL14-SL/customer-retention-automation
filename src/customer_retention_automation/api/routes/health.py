"""Healthcheck endpoint for the retention API."""

from fastapi import APIRouter

router = APIRouter(tags=["Health"])


@router.get("/health")
def health() -> dict[str, str]:
    """Check whether the API process is running."""
    return {"status": "ok"}
