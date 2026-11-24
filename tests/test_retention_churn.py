"""Tests for deterministic customer churn events."""

import pytest

from customer_retention_automation.simulation.churn import (
    list_active_customers,
    list_churn_events,
    should_churn,
    simulate_churn_period,
)


@pytest.fixture
def database(tmp_path):
    return tmp_path / "churn_simulation.sqlite"


@pytest.fixture
def customers():
    return [f"synthetic-{number:04d}" for number in range(100)]


def test_churn_decision_is_deterministic():
    first = should_churn("synthetic-0001", 30)
    second = should_churn("synthetic-0001", 30)

    assert first == second


def test_zero_churn_rate():
    assert not should_churn("synthetic-0001", 30, 0.0)


def test_full_churn_rate():
    assert should_churn("synthetic-0001", 30, 1.0)


@pytest.mark.parametrize("churn_rate", [-0.1, 1.1, float("nan")])
def test_invalid_churn_rate(churn_rate):
    with pytest.raises(ValueError, match="Churn rate"):
        should_churn("synthetic-0001", 30, churn_rate)


def test_first_churn_period(database, customers):
    result = simulate_churn_period(
        database, customers, simulation_day=30, churn_rate=1.0
    )

    assert result["new_churn_events"] == 100
    assert result["remaining_active"] == 0
    assert len(list_churn_events(database)) == 100


def test_churn_period_is_idempotent(database, customers):
    first = simulate_churn_period(database, customers, 30, 0.05)
    second = simulate_churn_period(database, customers, 30, 0.05)

    assert second["new_churn_events"] == 0
    assert second["total_churn_events"] == first["total_churn_events"]
    assert list_churn_events(database) == list_churn_events(database)


def test_churned_customers_do_not_churn_twice(database, customers):
    simulate_churn_period(database, customers, 30, 1.0)
    second = simulate_churn_period(database, customers, 60, 1.0)

    assert second["new_churn_events"] == 0
    assert second["total_churn_events"] == 100
    assert len(list_churn_events(database)) == 100


def test_churned_customers_are_excluded(database, customers):
    simulate_churn_period(database, customers, 30, 1.0)

    assert list_active_customers(database, customers, 0) == customers
    assert list_active_customers(database, customers, 30) == []
    assert list_active_customers(database, customers, 60) == []


def test_no_churn_preserves_active_customers(database, customers):
    simulate_churn_period(database, customers, 30, 0.0)

    active = list_active_customers(database, customers, 30)

    assert active == customers


def test_periods_must_be_chronological(database, customers):
    with pytest.raises(ValueError, match="Next simulation day"):
        simulate_churn_period(database, customers, 60, 0.05)


def test_existing_period_cannot_change_rate(database, customers):
    simulate_churn_period(database, customers, 30, 0.05)

    with pytest.raises(ValueError, match="another churn rate"):
        simulate_churn_period(database, customers, 30, 0.10)


def test_simulation_is_reproducible_across_databases(tmp_path, customers):
    first_database = tmp_path / "first.sqlite"
    second_database = tmp_path / "second.sqlite"

    for database in (first_database, second_database):
        simulate_churn_period(database, customers, 30, 0.05)
        simulate_churn_period(database, customers, 60, 0.05)

    first_events = [
        (row["customer_id"], row["churn_day"])
        for row in list_churn_events(first_database)
    ]
    second_events = [
        (row["customer_id"], row["churn_day"])
        for row in list_churn_events(second_database)
    ]

    assert first_events == second_events
