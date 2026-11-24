"""Simulated email jobs belonging to round-specific retention cases."""

import sqlite3
from pathlib import Path

from customer_retention_automation.retention.round_cases import (
    RoundCaseConflictError,
    _connect,
    initialize_round_case_database,
)

EMAIL_SCHEMA = """
CREATE TABLE IF NOT EXISTS retention_round_email_jobs (
    case_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'simulated')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    simulated_at TEXT,
    FOREIGN KEY (case_id)
        REFERENCES retention_round_cases(case_id)
)
"""


def initialize_round_email_database(database: Path) -> None:
    """Create email storage without changing existing case data."""
    initialize_round_case_database(database)

    with _connect(database) as connection:
        connection.execute(EMAIL_SCHEMA)


def _get_email_job(
    connection: sqlite3.Connection,
    case_id: str,
) -> dict | None:
    row = connection.execute(
        """
        SELECT
            case_id,
            customer_id,
            subject,
            body,
            status,
            created_at,
            simulated_at
        FROM retention_round_email_jobs
        WHERE case_id = ?
        """,
        (case_id,),
    ).fetchone()

    return dict(row) if row is not None else None


def create_round_email_job(
    database: Path,
    case_id: str,
) -> tuple[dict, bool]:
    """Create one simulated email job per eligible retention case."""
    initialize_round_email_database(database)

    with _connect(database) as connection:
        connection.execute("BEGIN IMMEDIATE")

        case = connection.execute(
            """
            SELECT
                case_id,
                customer_id,
                action,
                status,
                proposed_discount_percent
            FROM retention_round_cases
            WHERE case_id = ?
            """,
            (case_id,),
        ).fetchone()

        if case is None:
            raise LookupError("Retention case not found")

        existing_job = _get_email_job(connection, case_id)

        if existing_job is not None:
            return existing_job, False

        if case["action"] == "offer_discount":
            if case["status"] != "approved":
                raise RoundCaseConflictError(
                    "Discount must be approved before creating email"
                )

            discount = case["proposed_discount_percent"]

            if discount is None:
                raise RoundCaseConflictError(
                    "Discount percentage has not been registered"
                )

            subject = "Your approved retention offer"
            body = (
                f"Hello {case['customer_id']},\n\n"
                "Your retention offer has been approved.\n"
                f"Your proposed discount is {discount:g}%.\n\n"
                "This is a simulated email."
            )

        elif case["action"] == "send_email":
            if case["status"] != "pending":
                raise RoundCaseConflictError("Outreach case must be pending")

            subject = "We would like to hear from you"
            body = (
                f"Hello {case['customer_id']},\n\n"
                "We would like to check in with you about your service.\n\n"
                "This is a simulated email."
            )

        else:
            raise RoundCaseConflictError("No-action cases cannot create email jobs")

        connection.execute(
            """
            INSERT INTO retention_round_email_jobs (
                case_id,
                customer_id,
                subject,
                body
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                case_id,
                case["customer_id"],
                subject,
                body,
            ),
        )

        job = _get_email_job(connection, case_id)
        assert job is not None

        return job, True


def simulate_round_email(
    database: Path,
    case_id: str,
) -> tuple[dict, bool]:
    """Simulate email delivery and complete the associated case."""
    initialize_round_email_database(database)

    with _connect(database) as connection:
        connection.execute("BEGIN IMMEDIATE")

        job = _get_email_job(connection, case_id)

        if job is None:
            raise LookupError("Email job not found")

        if job["status"] == "simulated":
            return job, False

        case = connection.execute(
            """
            SELECT action, status
            FROM retention_round_cases
            WHERE case_id = ?
            """,
            (case_id,),
        ).fetchone()

        if case is None:
            raise LookupError("Retention case not found")

        allowed = (
            case["action"] == "offer_discount" and case["status"] == "approved"
        ) or (case["action"] == "send_email" and case["status"] == "pending")

        if not allowed:
            raise RoundCaseConflictError("Case is not eligible for email simulation")

        connection.execute(
            """
            UPDATE retention_round_email_jobs
            SET status = 'simulated',
                simulated_at = CURRENT_TIMESTAMP
            WHERE case_id = ?
            """,
            (case_id,),
        )

        connection.execute(
            """
            UPDATE retention_round_cases
            SET status = 'completed',
                updated_at = CURRENT_TIMESTAMP
            WHERE case_id = ?
            """,
            (case_id,),
        )

        updated = _get_email_job(connection, case_id)
        assert updated is not None

        return updated, True


def list_round_email_jobs(
    database: Path,
    *,
    customer_id: str | None = None,
) -> list[dict]:
    """List simulated email jobs, optionally for one customer."""
    initialize_round_email_database(database)

    with _connect(database) as connection:
        rows = connection.execute(
            """
            SELECT
                j.case_id,
                c.round_id,
                r.simulation_day,
                j.customer_id,
                c.action,
                j.subject,
                j.body,
                j.status,
                j.created_at,
                j.simulated_at
            FROM retention_round_email_jobs AS j
            JOIN retention_round_cases AS c
                ON c.case_id = j.case_id
            JOIN retention_evaluation_rounds AS r
                ON r.round_id = c.round_id
            WHERE (? IS NULL OR j.customer_id = ?)
            ORDER BY r.simulation_day, j.customer_id
            """,
            (customer_id, customer_id),
        ).fetchall()

        return [dict(row) for row in rows]
