"""Simulate approval decisions through existing n8n waiting forms."""

import argparse
import hashlib
import json
import subprocess
import time
from urllib.parse import urlsplit

import httpx

API_URL = "http://localhost:8001"
CONTAINER = "customer-retention-automation-api-1"
DATABASE = "/app/data/retention_churn_sim.sqlite"


def load_pending_approvals(round_id: str) -> list[dict]:
    """Read pending approvals and their signed form URLs from Docker."""
    query_script = """
import json
import sqlite3
import sys

database, round_id = sys.argv[1:3]

with sqlite3.connect(database) as connection:
    connection.row_factory = sqlite3.Row
    rows = connection.execute(
        '''
        SELECT case_id, customer_id, approval_url,
               approval_execution_id
        FROM retention_round_cases
        WHERE round_id = ?
          AND action = 'offer_discount'
          AND status = 'pending'
          AND approval_url IS NOT NULL
          AND approval_execution_id IS NOT NULL
        ORDER BY customer_id
        ''',
        (round_id,),
    ).fetchall()

print(json.dumps([dict(row) for row in rows]))
"""

    result = subprocess.run(
        [
            "docker",
            "exec",
            CONTAINER,
            "python",
            "-c",
            query_script,
            DATABASE,
            round_id,
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    return json.loads(result.stdout)


def choose_decision(
    case_id: str,
    seed: int,
    approval_rate: float,
) -> str:
    """Assign a reproducible decision independently per case."""
    value = hashlib.sha256(f"{seed}:{case_id}".encode()).digest()

    fraction = int.from_bytes(value[:8], "big") / 2**64

    return "approved" if fraction < approval_rate else "rejected"


def validate_form_url(url: str) -> None:
    """Do not send signed approval data to unexpected destinations."""
    parsed = urlsplit(url)

    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"localhost", "127.0.0.1"}
        or parsed.port != 5679
        or not parsed.path.startswith("/form-waiting/")
        or "signature=" not in parsed.query
    ):
        raise ValueError("Unexpected n8n approval URL")


def get_case(client: httpx.Client, case_id: str) -> dict:
    response = client.get(f"{API_URL}/retention/round-cases/{case_id}")
    response.raise_for_status()
    return response.json()


def submit_approval(
    client: httpx.Client,
    case: dict,
    decision: str,
) -> None:
    """Submit the n8n form and verify the resulting case status."""
    case_id = case["case_id"]
    approval_url = case["approval_url"]

    validate_form_url(approval_url)

    current = get_case(client, case_id)

    if current["status"] != "pending":
        print(f"SKIP {case_id}: {current['status']}")
        return

    if str(current["approval_execution_id"]) != str(case["approval_execution_id"]):
        raise RuntimeError("Approval execution ID mismatch")

    # Browser form field: field-0 = approved/rejected.
    # Multipart form data mirrors a browser form submission.
    response = client.post(
        approval_url,
        files={"field-0": (None, decision)},
        timeout=30.0,
    )
    response.raise_for_status()

    expected = "completed" if decision == "approved" else "rejected"

    # n8n resumes the workflow after the form submission.
    # Its downstream API calls may complete slightly later.
    for _ in range(15):
        updated = get_case(client, case_id)

        if updated["status"] == expected:
            print(f"OK   {case_id}: {decision} -> {expected}")
            return

        time.sleep(1)

    updated = get_case(client, case_id)

    raise RuntimeError(f"{case_id}: expected {expected}, found {updated['status']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulate n8n retention approvals.")
    parser.add_argument("--round", default="day-000")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--approval-rate", type=float, default=0.7)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually submit the n8n forms",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of forms to submit",
    )

    args = parser.parse_args()

    if not 0 <= args.approval_rate <= 1:
        parser.error("--approval-rate must be between 0 and 1")

    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")

    cases = load_pending_approvals(args.round)

    decisions = [
        (
            case,
            choose_decision(
                case["case_id"],
                args.seed,
                args.approval_rate,
            ),
        )
        for case in cases
    ]

    approved = sum(decision == "approved" for _, decision in decisions)

    print(f"Round: {args.round}")
    print(f"Pending approvals: {len(decisions)}")
    print(f"Planned approvals: {approved}")
    print(f"Planned rejections: {len(decisions) - approved}")

    if not args.apply:
        print("\nDRY RUN: no forms submitted")
        for case, decision in decisions[:10]:
            print(f"  {case['case_id']}: {decision}")
        return

    if args.limit is not None:
        decisions = decisions[: args.limit]

    print(f"\nSubmitting {len(decisions)} forms")

    with httpx.Client(timeout=30.0) as client:
        for case, decision in decisions:
            try:
                submit_approval(client, case, decision)
            except (httpx.HTTPError, RuntimeError, ValueError) as exc:
                print(f"FAILED {case['case_id']}: {exc}")
                print("Stopped. Inspect the case before retrying.")
                raise SystemExit(1) from exc

    print("\nFinished. All submitted cases verified.")


if __name__ == "__main__":
    main()
