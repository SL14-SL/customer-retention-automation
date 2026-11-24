"""Tests for recurring synthetic retention evaluations."""

import pytest

from customer_retention_automation.simulation.evaluations import (
    create_evaluation_round,
    list_customer_evaluations,
    list_evaluation_rounds,
    record_evaluation,
)


@pytest.fixture
def database(tmp_path):
    return tmp_path / "retention.sqlite"


def test_create_round(database):
    assert create_evaluation_round(database, "day-000", 0)

    rounds = list_evaluation_rounds(database)

    assert len(rounds) == 1
    assert rounds[0]["round_id"] == "day-000"
    assert rounds[0]["simulation_day"] == 0
    assert rounds[0]["customer_count"] == 0


def test_round_creation_is_idempotent(database):
    assert create_evaluation_round(database, "day-000", 0)
    assert not create_evaluation_round(database, "day-000", 0)

    assert len(list_evaluation_rounds(database)) == 1


def test_same_day_cannot_have_different_round_id(database):
    create_evaluation_round(database, "day-000", 0)

    with pytest.raises(ValueError, match="already assigned"):
        create_evaluation_round(database, "another-round", 0)


def test_round_id_cannot_change_day(database):
    create_evaluation_round(database, "day-000", 0)

    with pytest.raises(ValueError, match="already assigned"):
        create_evaluation_round(database, "day-000", 30)


def test_record_customer_evaluation(database):
    create_evaluation_round(database, "day-000", 0)

    assert record_evaluation(
        database, "day-000", "synthetic-0121", 0.92, "offer_discount"
    )

    history = list_customer_evaluations(database, "synthetic-0121")

    assert len(history) == 1
    assert history[0]["churn_probability"] == pytest.approx(0.92)
    assert history[0]["action"] == "offer_discount"


def test_duplicate_evaluation_is_ignored(database):
    create_evaluation_round(database, "day-000", 0)

    assert record_evaluation(
        database, "day-000", "synthetic-0121", 0.92, "offer_discount"
    )

    assert not record_evaluation(
        database, "day-000", "synthetic-0121", 0.10, "no_action"
    )

    history = list_customer_evaluations(database, "synthetic-0121")

    assert len(history) == 1
    assert history[0]["churn_probability"] == pytest.approx(0.92)


def test_customer_can_be_evaluated_in_later_round(database):
    create_evaluation_round(database, "day-000", 0)
    create_evaluation_round(database, "day-030", 30)
    create_evaluation_round(database, "day-060", 60)

    evaluations = [
        ("day-000", 0.92, "offer_discount"),
        ("day-030", 0.63, "send_email"),
        ("day-060", 0.22, "no_action"),
    ]

    for round_id, risk, action in evaluations:
        assert record_evaluation(
            database,
            round_id,
            "synthetic-0121",
            risk,
            action,
        )

    history = list_customer_evaluations(database, "synthetic-0121")

    assert len(history) == 3
    assert [row["simulation_day"] for row in history] == [0, 30, 60]
    assert [row["action"] for row in history] == [
        "offer_discount",
        "send_email",
        "no_action",
    ]


def test_unknown_round_is_rejected(database):
    with pytest.raises(KeyError, match="Unknown evaluation round"):
        record_evaluation(database, "missing", "synthetic-0121", 0.8, "no_action")


@pytest.mark.parametrize("probability", [-0.1, 1.1])
def test_invalid_risk_is_rejected(database, probability):
    create_evaluation_round(database, "day-000", 0)

    with pytest.raises(ValueError, match="between 0 and 1"):
        record_evaluation(
            database,
            "day-000",
            "synthetic-0121",
            probability,
            "no_action",
        )


def test_invalid_action_is_rejected(database):
    create_evaluation_round(database, "day-000", 0)

    with pytest.raises(ValueError, match="Unsupported action"):
        record_evaluation(
            database,
            "day-000",
            "synthetic-0121",
            0.8,
            "invalid_action",
        )
