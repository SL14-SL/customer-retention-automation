"""API-key authentication for retention workflow operations."""

import os
import secrets

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(
    name="X-API-Key",
    auto_error=False,
)


def require_api_key(
    provided_key: str | None = Security(api_key_header),
) -> None:
    """Validate API keys when authentication is configured."""
    expected_key = os.getenv("RETENTION_API_KEY")

    # Preserve the self-contained local demo mode.
    if not expected_key:
        return

    if not provided_key or not secrets.compare_digest(
        provided_key,
        expected_key,
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "APIKey"},
        )
