"""Deterministic simulation of customer cancellations."""

import hashlib
import math
import sqlite3
from pathlib import Path

INTERVAL_DAYS = 30
DEFAULT_CHURN_RATE = 0.05

SCHEMA = """
CREATE TABLE IF NOT EXISTS customer_churn_events (
    customer_id TEXT PRIMARY KEY,
    churn_day INTEGER NOT NULL CHECK (churn_day >= 0),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""

RUN_SCHEMA = """
CREATE TABLE IF NOT EXISTS churn_simulation_runs (
    simulation_day INTEGER PRIMARY KEY,
    churn_rate REAL NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""


def _connect(database: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(database, timeout=10)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_churn_database(database: Path) -> None:
    """Create the churn tables without changing existing data."""
    database.parent.mkdir(parents=True, exist_ok=True)

    with _connect(database) as connection:
        connection.execute(SCHEMA)
        connection.execute(RUN_SCHEMA)


def should_churn(
    customer_id: str,
    simulation_day: int,
    churn_rate: float = DEFAULT_CHURN_RATE,
) -> bool:
    """Reproducibly decide whether a customer churns in one interval."""
    if not customer_id.strip():
        raise ValueError("Customer ID must not be empty")

    if simulation_day < INTERVAL_DAYS or simulation_day % INTERVAL_DAYS:
        raise ValueError("Simulation day must be a positive multiple of 30")

    if not math.isfinite(churn_rate) or not 0 <= churn_rate <= 1:
        raise ValueError("Churn rate must be between 0 and 1")

    key = f"retention-churn-v1:{customer_id}:{simulation_day}"
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    value = int.from_bytes(digest[:8], "big") / 2**64

    return value < churn_rate


def list_churn_events(database: Path) -> list[dict]:
    """List all recorded cancellation events."""
    initialize_churn_database(database)

    with _connect(database) as connection:
        rows = connection.execute(
            """
            SELECT customer_id, churn_day, created_at
            FROM customer_churn_events
            ORDER BY churn_day, customer_id
            """
        ).fetchall()

    return [dict(row) for row in rows]


def list_active_customers(
    database: Path,
    customer_ids: list[str],
    simulation_day: int,
) -> list[str]:
    """Return customers who have not churned by the selected day."""
    if simulation_day < 0:
        raise ValueError("Simulation day must be non-negative")

    initialize_churn_database(database)

    with _connect(database) as connection:
        churned = {
            row["customer_id"]
            for row in connection.execute(
                """
                SELECT customer_id
                FROM customer_churn_events
                WHERE churn_day <= ?
                """,
                (simulation_day,),
            ).fetchall()
        }

    return [
        customer_id
        for customer_id in dict.fromkeys(customer_ids)
        if customer_id not in churned
    ]


def simulate_churn_period(
    database: Path,
    customer_ids: list[str],
    simulation_day: int,
    churn_rate: float = DEFAULT_CHURN_RATE,
) -> dict:
    """Simulate one chronological interval with duplicate protection."""
    # Validate before modifying the database.
    if simulation_day < INTERVAL_DAYS or simulation_day % INTERVAL_DAYS:
        raise ValueError("Simulation day must be a positive multiple of 30")

    if not math.isfinite(churn_rate) or not 0 <= churn_rate <= 1:
        raise ValueError("Churn rate must be between 0 and 1")

    customers = sorted(set(customer_ids))

    if not customers or any(not customer_id.strip() for customer_id in customers):
        raise ValueError("Customer IDs must be non-empty")

    initialize_churn_database(database)

    with _connect(database) as connection:
        connection.execute("BEGIN IMMEDIATE")

        runs = connection.execute(
            """
            SELECT simulation_day, churn_rate
            FROM churn_simulation_runs
            ORDER BY simulation_day
            """
        ).fetchall()

        existing_run = next(
            (row for row in runs if row["simulation_day"] == simulation_day),
            None,
        )

        if existing_run is not None:
            if not math.isclose(
                existing_run["churn_rate"],
                churn_rate,
                rel_tol=0,
                abs_tol=1e-12,
            ):
                raise ValueError("Simulation day already uses another churn rate")

            created = 0
        else:
            expected_day = (
                runs[-1]["simulation_day"] + INTERVAL_DAYS if runs else INTERVAL_DAYS
            )

            if simulation_day != expected_day:
                raise ValueError(f"Next simulation day must be {expected_day}")

            already_churned = {
                row["customer_id"]
                for row in connection.execute(
                    "SELECT customer_id FROM customer_churn_events"
                ).fetchall()
            }

            new_events = [
                (customer_id, simulation_day)
                for customer_id in customers
                if customer_id not in already_churned
                and should_churn(customer_id, simulation_day, churn_rate)
            ]

            connection.executemany(
                """
                INSERT INTO customer_churn_events
                    (customer_id, churn_day)
                VALUES (?, ?)
                """,
                new_events,
            )

            connection.execute(
                """
                INSERT INTO churn_simulation_runs
                    (simulation_day, churn_rate)
                VALUES (?, ?)
                """,
                (simulation_day, churn_rate),
            )

            created = len(new_events)

        churned_count = connection.execute(
            """
            SELECT COUNT(*)
            FROM customer_churn_events
            WHERE churn_day <= ?
            """,
            (simulation_day,),
        ).fetchone()[0]

    return {
        "simulation_day": simulation_day,
        "customers_in_population": len(customers),
        "new_churn_events": created,
        "total_churn_events": churned_count,
        "remaining_active": len(customers) - churned_count,
    }
