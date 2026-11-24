"""Persistent evaluation rounds for synthetic customer retention."""

import sqlite3
from pathlib import Path
from typing import Literal

RetentionAction = Literal[
    "offer_discount",
    "send_email",
    "no_action",
]

ROUND_SCHEMA = """
CREATE TABLE IF NOT EXISTS retention_evaluation_rounds (
    round_id TEXT PRIMARY KEY,
    simulation_day INTEGER NOT NULL UNIQUE
        CHECK (simulation_day >= 0),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""

EVALUATION_SCHEMA = """
CREATE TABLE IF NOT EXISTS retention_evaluations (
    round_id TEXT NOT NULL,
    customer_id TEXT NOT NULL,
    churn_probability REAL NOT NULL
        CHECK (churn_probability >= 0 AND churn_probability <= 1),
    action TEXT NOT NULL
        CHECK (action IN ('offer_discount', 'send_email', 'no_action')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (round_id, customer_id),
    FOREIGN KEY (round_id)
        REFERENCES retention_evaluation_rounds(round_id)
)
"""


def _connect(database: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(database, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_evaluation_database(database: Path) -> None:
    """Create evaluation tables without modifying existing cases."""
    database.parent.mkdir(parents=True, exist_ok=True)

    with _connect(database) as connection:
        connection.execute(ROUND_SCHEMA)
        connection.execute(EVALUATION_SCHEMA)


def create_evaluation_round(
    database: Path,
    round_id: str,
    simulation_day: int,
) -> bool:
    """Create a simulation round; return False if it already exists."""
    if not round_id.strip():
        raise ValueError("Round ID must not be empty")

    if simulation_day < 0:
        raise ValueError("Simulation day must be non-negative")

    initialize_evaluation_database(database)

    with _connect(database) as connection:
        existing = connection.execute(
            """
            SELECT round_id, simulation_day
            FROM retention_evaluation_rounds
            WHERE round_id = ? OR simulation_day = ?
            """,
            (round_id, simulation_day),
        ).fetchone()

        if existing is not None:
            if (
                existing["round_id"] == round_id
                and existing["simulation_day"] == simulation_day
            ):
                return False

            raise ValueError("Round ID or simulation day is already assigned")

        connection.execute(
            """
            INSERT INTO retention_evaluation_rounds (
                round_id, simulation_day
            )
            VALUES (?, ?)
            """,
            (round_id, simulation_day),
        )
        return True


def record_evaluation(
    database: Path,
    round_id: str,
    customer_id: str,
    churn_probability: float,
    action: RetentionAction,
) -> bool:
    """Record one customer evaluation per round."""
    if not customer_id.strip():
        raise ValueError("Customer ID must not be empty")

    if not 0 <= churn_probability <= 1:
        raise ValueError("Churn probability must be between 0 and 1")

    if action not in {"offer_discount", "send_email", "no_action"}:
        raise ValueError(f"Unsupported action: {action}")

    initialize_evaluation_database(database)

    with _connect(database) as connection:
        round_exists = connection.execute(
            """
            SELECT 1
            FROM retention_evaluation_rounds
            WHERE round_id = ?
            """,
            (round_id,),
        ).fetchone()

        if round_exists is None:
            raise KeyError(f"Unknown evaluation round: {round_id}")

        cursor = connection.execute(
            """
            INSERT OR IGNORE INTO retention_evaluations (
                round_id,
                customer_id,
                churn_probability,
                action
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                round_id,
                customer_id,
                churn_probability,
                action,
            ),
        )

        return cursor.rowcount == 1


def list_evaluation_rounds(database: Path) -> list[dict]:
    """Return simulation rounds in chronological order."""
    initialize_evaluation_database(database)

    with _connect(database) as connection:
        rows = connection.execute(
            """
            SELECT
                r.round_id,
                r.simulation_day,
                r.created_at,
                COUNT(e.customer_id) AS customer_count
            FROM retention_evaluation_rounds AS r
            LEFT JOIN retention_evaluations AS e
                ON e.round_id = r.round_id
            GROUP BY r.round_id, r.simulation_day, r.created_at
            ORDER BY r.simulation_day
            """
        ).fetchall()

        return [dict(row) for row in rows]


def list_customer_evaluations(
    database: Path,
    customer_id: str,
) -> list[dict]:
    """Return a customer's risk and action history."""
    initialize_evaluation_database(database)

    with _connect(database) as connection:
        rows = connection.execute(
            """
            SELECT
                e.round_id,
                r.simulation_day,
                e.customer_id,
                e.churn_probability,
                e.action,
                e.created_at
            FROM retention_evaluations AS e
            JOIN retention_evaluation_rounds AS r
                ON r.round_id = e.round_id
            WHERE e.customer_id = ?
            ORDER BY r.simulation_day
            """,
            (customer_id,),
        ).fetchall()

        return [dict(row) for row in rows]


def list_evaluated_customers(database: Path) -> list[str]:
    """Return all distinct evaluated customer IDs."""
    initialize_evaluation_database(database)

    with _connect(database) as connection:
        rows = connection.execute(
            """
            SELECT DISTINCT customer_id
            FROM retention_evaluations
            ORDER BY customer_id
            """
        ).fetchall()

        return [row["customer_id"] for row in rows]
