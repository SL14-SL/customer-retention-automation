"""Generate a temporary n8n credential import payload."""

import json
import os
import sys

CREDENTIAL_ID = "1OoEC812MPns7ct1"
CREDENTIAL_NAME = "Retention API"
CREDENTIAL_TYPE = "httpHeaderAuth"


def build_credential(api_key: str) -> dict:
    """Build a Header Auth credential with the expected workflow ID."""
    if not api_key:
        raise ValueError("RETENTION_API_KEY must not be empty")

    return {
        "id": CREDENTIAL_ID,
        "name": CREDENTIAL_NAME,
        "type": CREDENTIAL_TYPE,
        "data": {
            "name": "X-API-Key",
            "value": api_key,
        },
    }


def main() -> None:
    """Write the credential payload for the n8n CLI."""
    api_key = os.getenv("RETENTION_API_KEY")

    if not api_key:
        print(
            "RETENTION_API_KEY is not configured",
            file=sys.stderr,
        )
        raise SystemExit(1)

    print(json.dumps([build_credential(api_key)]))


if __name__ == "__main__":
    main()
