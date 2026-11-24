"""Tests for deterministic churn-risk simulation."""

import pytest

from customer_retention_automation.simulation.simulation import (
    determine_action,
    simulate_evaluation,
)


@pytest.mark.parametrize(
    ("probability", "expected"),
    [
        (0.95, "offer_discount"),
        (0.80, "offer_discount"),
        (0.79, "send_email"),
        (0.50, "send_email"),
        (0.49, "no_action"),
        (0.10, "no_action"),
    ],
)
def test_determine_action(probability, expected):
    assert determine_action(probability) == expected


def test_day_zero_preserves_baseline():
    result = simulate_evaluation("synthetic-0121", 0.92, 0)

    assert result["churn_probability"] == 0.92
    assert result["action"] == "offer_discount"


def test_simulation_is_reproducible():
    first = simulate_evaluation("synthetic-0121", 0.92, 30)
    second = simulate_evaluation("synthetic-0121", 0.92, 30)

    assert first == second


def test_later_rounds_can_have_different_risks():
    day_30 = simulate_evaluation("synthetic-0121", 0.5, 30)
    day_60 = simulate_evaluation("synthetic-0121", 0.5, 60)

    assert day_30["churn_probability"] != day_60["churn_probability"]


@pytest.mark.parametrize("day", [0, 30, 60, 90])
def test_probabilities_stay_in_valid_range(day):
    for baseline in (0.0, 0.1, 0.5, 0.9, 1.0):
        result = simulate_evaluation("synthetic-0121", baseline, day)
        assert 0 <= result["churn_probability"] <= 1


def test_invalid_probability():
    with pytest.raises(ValueError, match="Baseline probability"):
        simulate_evaluation("synthetic-0121", 1.5, 30)


def test_invalid_simulation_day():
    with pytest.raises(ValueError, match="Simulation day"):
        simulate_evaluation("synthetic-0121", 0.8, -30)


def test_empty_customer_id():
    with pytest.raises(ValueError, match="Customer ID"):
        simulate_evaluation("", 0.8, 30)
