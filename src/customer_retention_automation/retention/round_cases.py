"""Round-specific retention cases for recurring customer evaluations."""

import sqlite3
from pathlib import Path
from typing import Literal

RetentionAction = Literal[
    "offer_discount",
    "send_email",
    "no_action",
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS retention_round_cases (
    case_id TEXT PRIMARY KEY,
    round_id TEXT NOT NULL,
    customer_id TEXT NOT NULL,
    action TEXT NOT NULL
        CHECK (action IN ('offer_discount', 'send_email', 'no_action')),
    status TEXT NOT NULL
        CHECK (
            status IN (
                'pending',
                'approved',
                'rejected',
                'completed',
                'dispatch_failed'
            )
        ),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (round_id, customer_id),
    FOREIGN KEY (round_id, customer_id)
        REFERENCES retention_evaluations(round_id, customer_id)
)
"""


def _connect(database: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(database, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_round_case_database(database: Path) -> None:
    """Initialize round-case storage and its evaluation dependencies."""
    from customer_retention_automation.simulation.evaluations import (
        initialize_evaluation_database,
    )

    initialize_evaluation_database(database)

    with _connect(database) as connection:
        connection.execute(SCHEMA)

        existing_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(retention_round_cases)")
        }

        new_columns = {
            "approval_url": "TEXT",
            "approval_execution_id": "TEXT",
            "proposed_discount_percent": "REAL",
        }

        for column_name, column_type in new_columns.items():
            if column_name not in existing_columns:
                connection.execute(
                    f"ALTER TABLE retention_round_cases "
                    f"ADD COLUMN {column_name} {column_type}"
                )


def build_case_id(round_id: str, customer_id: str) -> str:
    """Build a stable identifier for a customer in one evaluation round."""
    if not round_id.strip() or not customer_id.strip():
        raise ValueError("Round ID and customer ID must not be empty")

    if ":" in round_id or ":" in customer_id:
        raise ValueError("Round ID and customer ID must not contain ':'")

    return f"{round_id}:{customer_id}"


def create_round_case(
    database: Path,
    round_id: str,
    customer_id: str,
    action: RetentionAction,
) -> bool:
    """Create a case only when the matching evaluation exists."""
    case_id = build_case_id(round_id, customer_id)

    if action not in {"offer_discount", "send_email", "no_action"}:
        raise ValueError(f"Unsupported retention action: {action}")

    initialize_round_case_database(database)

    with _connect(database) as connection:
        connection.execute("BEGIN IMMEDIATE")

        evaluation = connection.execute(
            """
            SELECT action
            FROM retention_evaluations
            WHERE round_id = ?
              AND customer_id = ?
            """,
            (round_id, customer_id),
        ).fetchone()

        if evaluation is None:
            raise ValueError("No recorded evaluation for this customer and round")

        if evaluation["action"] != action:
            raise ValueError("Case action does not match the recorded evaluation")

        status = "completed" if action == "no_action" else "pending"

        cursor = connection.execute(
            """
            INSERT OR IGNORE INTO retention_round_cases (
                case_id,
                round_id,
                customer_id,
                action,
                status
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                case_id,
                round_id,
                customer_id,
                action,
                status,
            ),
        )

        return cursor.rowcount == 1


def get_round_case(
    database: Path,
    case_id: str,
) -> dict | None:
    """Return one round-specific case."""
    initialize_round_case_database(database)

    with _connect(database) as connection:
        row = connection.execute(
            """
            SELECT
                c.case_id,
                c.round_id,
                r.simulation_day,
                c.customer_id,
                c.action,
                c.status,
                e.churn_probability,
                c.created_at,
                c.updated_at,
                c.approval_execution_id,
                c.proposed_discount_percent
            FROM retention_round_cases AS c
            JOIN retention_evaluation_rounds AS r
                ON r.round_id = c.round_id
            JOIN retention_evaluations AS e
                ON e.round_id = c.round_id
               AND e.customer_id = c.customer_id
            WHERE c.case_id = ?
            """,
            (case_id,),
        ).fetchone()

        return dict(row) if row is not None else None


def list_round_cases(
    database: Path,
    *,
    round_id: str | None = None,
    customer_id: str | None = None,
) -> list[dict]:
    """List round cases, optionally filtered by round or customer."""
    initialize_round_case_database(database)

    query = """
        SELECT
            c.case_id,
            c.round_id,
            r.simulation_day,
            c.customer_id,
            c.action,
            c.status,
            e.churn_probability,
            c.created_at,
            c.approval_execution_id,
            c.proposed_discount_percent,
            c.updated_at
        FROM retention_round_cases AS c
        JOIN retention_evaluation_rounds AS r
            ON r.round_id = c.round_id
        JOIN retention_evaluations AS e
            ON e.round_id = c.round_id
           AND e.customer_id = c.customer_id
        WHERE (? IS NULL OR c.round_id = ?)
          AND (? IS NULL OR c.customer_id = ?)
        ORDER BY r.simulation_day, c.customer_id
    """

    with _connect(database) as connection:
        rows = connection.execute(
            query,
            (round_id, round_id, customer_id, customer_id),
        ).fetchall()

        return [dict(row) for row in rows]


class RoundCaseConflictError(Exception):
    """The requested case transition is not allowed."""


def decide_round_case(
    database: Path,
    case_id: str,
    decision: Literal["approved", "rejected"],
    approval_execution_id: str,
) -> dict:
    """Decide a pending discount offer from its registered execution."""
    if decision not in {"approved", "rejected"}:
        raise ValueError("Decision must be approved or rejected")

    if not approval_execution_id.strip():
        raise ValueError("Approval execution ID must not be empty")

    initialize_round_case_database(database)

    with _connect(database) as connection:
        connection.execute("BEGIN IMMEDIATE")

        row = connection.execute(
            """
            SELECT
                action,
                status,
                approval_execution_id
            FROM retention_round_cases
            WHERE case_id = ?
            """,
            (case_id,),
        ).fetchone()

        if row is None:
            raise LookupError("Retention case not found")

        if row["action"] != "offer_discount":
            raise RoundCaseConflictError("Only discount offers require approval")

        if row["status"] != "pending":
            raise RoundCaseConflictError(
                "Only pending cases can be approved or rejected"
            )

        if (
            row["approval_execution_id"] is None
            or row["approval_execution_id"] != approval_execution_id
        ):
            raise RoundCaseConflictError(
                "Approval execution does not match the registered execution"
            )

        connection.execute(
            """
            UPDATE retention_round_cases
            SET status = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE case_id = ?
            """,
            (decision, case_id),
        )

    result = get_round_case(database, case_id)

    if result is None:
        raise RuntimeError("Updated case could not be retrieved")

    return result


def register_round_approval_link(
    database: Path,
    case_id: str,
    approval_url: str,
    approval_execution_id: str,
    proposed_discount_percent: float,
) -> bool:
    """Register the approval execution and proposed discount."""
    if not approval_url.startswith(("http://", "https://")):
        raise ValueError("A valid HTTP approval URL is required")

    if not approval_execution_id.strip():
        raise ValueError("Approval execution ID must not be empty")

    if not 0 < proposed_discount_percent <= 100:
        raise ValueError("Discount must be between 0 and 100 percent")

    initialize_round_case_database(database)

    with _connect(database) as connection:
        connection.execute("BEGIN IMMEDIATE")

        case = connection.execute(
            """
            SELECT
                action,
                status,
                approval_url,
                approval_execution_id,
                proposed_discount_percent
            FROM retention_round_cases
            WHERE case_id = ?
            """,
            (case_id,),
        ).fetchone()

        if case is None:
            raise LookupError("Retention case not found")

        if case["action"] != "offer_discount":
            raise RoundCaseConflictError("Only discount cases support approval links")

        if case["status"] != "pending":
            raise RoundCaseConflictError("Approval link requires a pending case")

        if case["approval_execution_id"] is not None:
            if (
                case["approval_execution_id"] == approval_execution_id
                and case["approval_url"] == approval_url
                and case["proposed_discount_percent"] == proposed_discount_percent
            ):
                return False

            raise RoundCaseConflictError("An approval execution is already registered")

        connection.execute(
            """
            UPDATE retention_round_cases
            SET approval_url = ?,
                approval_execution_id = ?,
                proposed_discount_percent = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE case_id = ?
            """,
            (
                approval_url,
                approval_execution_id,
                proposed_discount_percent,
                case_id,
            ),
        )

        return True


def mark_round_dispatch_failed(
    database: Path,
    case_id: str,
) -> dict:
    """Mark a discount case as failed before approval registration."""
    initialize_round_case_database(database)

    with _connect(database) as connection:
        connection.execute("BEGIN IMMEDIATE")

        case = connection.execute(
            """
            SELECT action, status, approval_execution_id
            FROM retention_round_cases
            WHERE case_id = ?
            """,
            (case_id,),
        ).fetchone()

        if case is None:
            raise LookupError("Retention case not found")

        if case["action"] != "offer_discount":
            raise RoundCaseConflictError(
                "Only discount cases support approval dispatch"
            )

        if case["status"] != "pending":
            raise RoundCaseConflictError("Only pending cases can fail dispatch")

        if case["approval_execution_id"] is not None:
            raise RoundCaseConflictError("Approval execution already registered")

        connection.execute(
            """
            UPDATE retention_round_cases
            SET status = 'dispatch_failed',
                approval_url = NULL,
                approval_execution_id = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE case_id = ?
            """,
            (case_id,),
        )

    result = get_round_case(database, case_id)
    assert result is not None
    return result
