"""Tests for SQLite-backed synthetic retention batch evaluations."""

import sqlite3
from pathlib import Path

import pytest

from customer_retention_automation.simulation.batch import (
    evaluate_customer_batch,
    load_customers,
)
from customer_retention_automation.simulation.churn import (
    list_churn_events,
)
from customer_retention_automation.simulation.evaluations import (
    list_customer_evaluations,
    list_evaluation_rounds,
)


@pytest.fixture
def customer_database(tmp_path: Path) -> Path:
    """Create an isolated SQLite database with two synthetic customers."""
    database = tmp_path / "customers.sqlite"

    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            CREATE TABLE customers (
                customerID TEXT PRIMARY KEY,
                churn_probability REAL NOT NULL
            )
            """
        )

        connection.executemany(
            """
            INSERT INTO customers (customerID, churn_probability)
            VALUES (?, ?)
            """,
            [
                ("synthetic-001", 0.9),
                ("synthetic-002", 0.4),
            ],
        )

    return database


def test_load_customers(customer_database: Path) -> None:
    customers = load_customers(customer_database)

    assert customers == [
        ("synthetic-001", 0.9),
        ("synthetic-002", 0.4),
    ]


def test_missing_customer_database_is_rejected(
    tmp_path: Path,
) -> None:
    with pytest.raises(FileNotFoundError):
        load_customers(tmp_path / "missing.sqlite")


def test_batch_creates_evaluations(
    tmp_path: Path,
    customer_database: Path,
) -> None:
    database = tmp_path / "retention.sqlite"

    result = evaluate_customer_batch(
        customer_database=customer_database,
        retention_database=database,
        round_id="day-000",
        simulation_day=0,
    )

    assert result["created"] == 2
    assert result["skipped_duplicates"] == 0
    assert result["round_created"] is True

    history = list_customer_evaluations(database, "synthetic-001")

    assert history[0]["churn_probability"] == 0.9
    assert history[0]["action"] == "offer_discount"


def test_batch_is_idempotent(
    tmp_path: Path,
    customer_database: Path,
) -> None:
    database = tmp_path / "retention.sqlite"

    arguments = {
        "customer_database": customer_database,
        "retention_database": database,
        "round_id": "day-000",
        "simulation_day": 0,
    }

    first = evaluate_customer_batch(**arguments)
    second = evaluate_customer_batch(**arguments)

    assert first["created"] == 2
    assert second["created"] == 0
    assert second["skipped_duplicates"] == 2
    assert second["round_created"] is False


def test_later_round_creates_new_evaluations(
    tmp_path: Path,
    customer_database: Path,
) -> None:
    database = tmp_path / "retention.sqlite"

    evaluate_customer_batch(customer_database, database, "day-000", 0)
    evaluate_customer_batch(customer_database, database, "day-030", 30)

    history = list_customer_evaluations(database, "synthetic-001")

    assert len(history) == 2
    assert [row["simulation_day"] for row in history] == [0, 30]

    rounds = list_evaluation_rounds(database)

    assert len(rounds) == 2
    assert all(row["customer_count"] == 2 for row in rounds)


def test_empty_customer_dataset_is_rejected(
    tmp_path: Path,
) -> None:
    source = tmp_path / "empty.sqlite"
    database = tmp_path / "retention.sqlite"

    with sqlite3.connect(source) as connection:
        connection.execute(
            """
            CREATE TABLE customers (
                customerID TEXT PRIMARY KEY,
                churn_probability REAL NOT NULL
            )
            """
        )

    with pytest.raises(ValueError, match="no customers"):
        evaluate_customer_batch(
            source,
            database,
            "day-000",
            0,
        )

    assert not database.exists()


def test_churn_enabled_batch_excludes_cancelled_customers(
    tmp_path: Path,
    customer_database: Path,
) -> None:
    database = tmp_path / "retention_churn_sim.sqlite"

    day_zero = evaluate_customer_batch(
        customer_database,
        database,
        "day-000",
        0,
        with_churn=True,
        churn_rate=1.0,
    )

    assert day_zero["customers_evaluated"] == 2
    assert day_zero["customers_churned"] == 0

    day_thirty = evaluate_customer_batch(
        customer_database,
        database,
        "day-030",
        30,
        with_churn=True,
        churn_rate=1.0,
    )

    assert day_thirty["customers_evaluated"] == 0
    assert day_thirty["customers_active"] == 0
    assert day_thirty["customers_churned"] == 2
    assert day_thirty["new_churn_events"] == 2

    day_sixty = evaluate_customer_batch(
        customer_database,
        database,
        "day-060",
        60,
        with_churn=True,
        churn_rate=1.0,
    )

    assert day_sixty["customers_evaluated"] == 0
    assert day_sixty["new_churn_events"] == 0

    history = list_customer_evaluations(database, "synthetic-001")

    assert [row["simulation_day"] for row in history] == [0]
    assert len(list_churn_events(database)) == 2


def test_churn_enabled_batch_is_idempotent(
    tmp_path: Path,
    customer_database: Path,
) -> None:
    database = tmp_path / "retention_churn_sim.sqlite"

    evaluate_customer_batch(
        customer_database,
        database,
        "day-000",
        0,
        with_churn=True,
    )

    first = evaluate_customer_batch(
        customer_database,
        database,
        "day-030",
        30,
        with_churn=True,
    )

    second = evaluate_customer_batch(
        customer_database,
        database,
        "day-030",
        30,
        with_churn=True,
    )

    assert second["created"] == 0
    assert second["skipped_duplicates"] == first["customers_evaluated"]
    assert second["new_churn_events"] == 0


def test_churn_enabled_batch_rejects_invalid_day(
    tmp_path: Path,
    customer_database: Path,
) -> None:
    database = tmp_path / "retention_churn_sim.sqlite"

    with pytest.raises(ValueError, match="days 0, 30, 60"):
        evaluate_customer_batch(
            customer_database,
            database,
            "day-015",
            15,
            with_churn=True,
        )

    assert not database.exists()
