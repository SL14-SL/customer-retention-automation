"""Tests for round-specific retention cases."""

import sqlite3

import pytest

from customer_retention_automation.retention.round_cases import (
    RoundCaseConflictError,
    build_case_id,
    create_round_case,
    decide_round_case,
    get_round_case,
    list_round_cases,
    mark_round_dispatch_failed,
    register_round_approval_link,
)
from customer_retention_automation.simulation.evaluations import (
    create_evaluation_round,
    record_evaluation,
)


@pytest.fixture
def database(tmp_path):
    database = tmp_path / "retention_rounds.sqlite"

    create_evaluation_round(database, "day-000", 0)
    create_evaluation_round(database, "day-030", 30)
    create_evaluation_round(database, "day-060", 60)

    record_evaluation(database, "day-000", "synthetic-0121", 0.92, "offer_discount")
    record_evaluation(database, "day-030", "synthetic-0121", 0.63, "send_email")
    record_evaluation(database, "day-060", "synthetic-0121", 0.22, "no_action")
    record_evaluation(database, "day-000", "synthetic-0139", 0.6, "send_email")

    return database


def create_discount_case(database):
    case_id = "day-000:synthetic-0121"

    create_round_case(database, "day-000", "synthetic-0121", "offer_discount")
    return case_id


def register_discount_approval(database, case_id):
    return register_round_approval_link(
        database,
        case_id,
        "http://localhost:5678/form/test",
        "execution-123",
        10.0,
    )


def test_build_case_id():
    assert build_case_id("day-030", "synthetic-0121") == "day-030:synthetic-0121"


@pytest.mark.parametrize(
    ("round_id", "customer_id"),
    [
        ("", "synthetic-0121"),
        ("day-000", ""),
        ("day:000", "synthetic-0121"),
        ("day-000", "synthetic:0121"),
    ],
)
def test_invalid_case_id(round_id, customer_id):
    with pytest.raises(ValueError):
        build_case_id(round_id, customer_id)


def test_create_discount_case(database):
    created = create_round_case(
        database,
        "day-000",
        "synthetic-0121",
        "offer_discount",
    )
    assert created

    case = get_round_case(database, "day-000:synthetic-0121")

    assert case is not None
    assert case["status"] == "pending"
    assert case["action"] == "offer_discount"
    assert case["simulation_day"] == 0
    assert case["churn_probability"] == pytest.approx(0.92)


def test_customer_can_have_cases_in_multiple_rounds(database):
    assert create_round_case(database, "day-000", "synthetic-0121", "offer_discount")
    assert create_round_case(database, "day-030", "synthetic-0121", "send_email")
    assert create_round_case(database, "day-060", "synthetic-0121", "no_action")

    cases = list_round_cases(database, customer_id="synthetic-0121")

    assert len(cases) == 3
    assert [case["simulation_day"] for case in cases] == [0, 30, 60]
    assert [case["status"] for case in cases] == [
        "pending",
        "pending",
        "completed",
    ]


def test_duplicate_case_is_ignored(database):
    assert create_round_case(database, "day-000", "synthetic-0121", "offer_discount")
    assert not create_round_case(
        database, "day-000", "synthetic-0121", "offer_discount"
    )
    assert len(list_round_cases(database)) == 1


def test_action_must_match_evaluation(database):
    with pytest.raises(ValueError, match="does not match"):
        create_round_case(database, "day-000", "synthetic-0121", "send_email")


def test_missing_evaluation_cannot_create_case(database):
    with pytest.raises(ValueError, match="No recorded evaluation"):
        create_round_case(database, "day-030", "synthetic-0139", "send_email")
    assert list_round_cases(database) == []


def test_no_action_is_completed_immediately(database):
    assert create_round_case(database, "day-060", "synthetic-0121", "no_action")

    case = get_round_case(database, "day-060:synthetic-0121")
    assert case is not None
    assert case["status"] == "completed"


def test_filter_cases_by_round(database):
    create_round_case(database, "day-000", "synthetic-0121", "offer_discount")
    create_round_case(database, "day-030", "synthetic-0121", "send_email")

    cases = list_round_cases(database, round_id="day-030")

    assert len(cases) == 1
    assert cases[0]["round_id"] == "day-030"


def test_unknown_case_returns_none(database):
    assert get_round_case(database, "missing") is None


def test_invalid_action_is_rejected(database):
    with pytest.raises(ValueError, match="Unsupported retention action"):
        create_round_case(
            database,
            "day-000",
            "synthetic-0121",
            "invalid_action",
        )


def test_approve_round_case(database):
    case_id = create_discount_case(database)
    register_discount_approval(database, case_id)

    case = decide_round_case(database, case_id, "approved", "execution-123")

    assert case["status"] == "approved"


def test_reject_round_case(database):
    case_id = create_discount_case(database)
    register_discount_approval(database, case_id)

    case = decide_round_case(database, case_id, "rejected", "execution-123")

    assert case["status"] == "rejected"


def test_decision_only_changes_target_case(database):
    case_id = create_discount_case(database)
    create_round_case(database, "day-030", "synthetic-0121", "send_email")
    register_discount_approval(database, case_id)

    decide_round_case(database, case_id, "approved", "execution-123")

    other = get_round_case(database, "day-030:synthetic-0121")

    assert other is not None
    assert other["status"] == "pending"


def test_decision_cannot_be_changed(database):
    case_id = create_discount_case(database)
    register_discount_approval(database, case_id)

    decide_round_case(database, case_id, "approved", "execution-123")

    with pytest.raises(RoundCaseConflictError):
        decide_round_case(database, case_id, "rejected", "execution-123")


def test_outreach_does_not_support_approval(database):
    create_round_case(database, "day-030", "synthetic-0121", "send_email")

    with pytest.raises(RoundCaseConflictError):
        decide_round_case(
            database,
            "day-030:synthetic-0121",
            "approved",
            "execution-123",
        )


def test_missing_case_cannot_be_approved(database):
    with pytest.raises(LookupError):
        decide_round_case(
            database,
            "day-000:missing",
            "approved",
            "execution-123",
        )


def test_register_approval_link(database):
    case_id = create_discount_case(database)

    created = register_round_approval_link(
        database,
        case_id,
        "http://localhost:5678/form/test-approval",
        "execution-123",
        10.0,
    )

    assert created is True

    with sqlite3.connect(database) as connection:
        row = connection.execute(
            """
            SELECT
                approval_url,
                approval_execution_id,
                proposed_discount_percent
            FROM retention_round_cases
            WHERE case_id = ?
            """,
            (case_id,),
        ).fetchone()

    assert row == (
        "http://localhost:5678/form/test-approval",
        "execution-123",
        10.0,
    )


def test_register_approval_link_is_idempotent(database):
    case_id = create_discount_case(database)

    arguments = (
        database,
        case_id,
        "http://localhost:5678/form/test",
        "execution-123",
        10.0,
    )

    assert register_round_approval_link(*arguments)
    assert not register_round_approval_link(*arguments)


def test_cannot_replace_existing_approval_execution(database):
    case_id = create_discount_case(database)

    register_round_approval_link(
        database,
        case_id,
        "http://localhost/form/1",
        "execution-1",
        10.0,
    )

    with pytest.raises(RoundCaseConflictError):
        register_round_approval_link(
            database,
            case_id,
            "http://localhost/form/2",
            "execution-2",
            20.0,
        )


def test_mark_dispatch_failed(database):
    case_id = create_discount_case(database)

    failed = mark_round_dispatch_failed(database, case_id)

    assert failed["status"] == "dispatch_failed"

    stored = get_round_case(database, case_id)
    assert stored is not None
    assert stored["status"] == "dispatch_failed"


def test_cannot_mark_registered_approval_as_failed(database):
    case_id = create_discount_case(database)

    register_round_approval_link(
        database,
        case_id,
        "http://localhost/form/1",
        "execution-1",
        10.0,
    )

    with pytest.raises(RoundCaseConflictError):
        mark_round_dispatch_failed(database, case_id)

    case = get_round_case(database, case_id)
    assert case is not None
    assert case["status"] == "pending"


def test_outreach_cannot_mark_dispatch_failed(database):
    create_round_case(database, "day-030", "synthetic-0121", "send_email")

    with pytest.raises(RoundCaseConflictError):
        mark_round_dispatch_failed(database, "day-030:synthetic-0121")


def test_dispatch_failure_only_affects_target_case(database):
    discount_id = create_discount_case(database)
    outreach_id = "day-030:synthetic-0121"

    create_round_case(database, "day-030", "synthetic-0121", "send_email")

    mark_round_dispatch_failed(database, discount_id)

    discount = get_round_case(database, discount_id)
    outreach = get_round_case(database, outreach_id)

    assert discount is not None
    assert outreach is not None
    assert discount["status"] == "dispatch_failed"
    assert outreach["status"] == "pending"


def test_invalid_approval_url_is_rejected(database):
    case_id = create_discount_case(database)

    with pytest.raises(ValueError):
        register_round_approval_link(
            database,
            case_id,
            "not-a-url",
            "execution-123",
            10.0,
        )


def test_wrong_execution_cannot_approve(database):
    case_id = create_discount_case(database)
    register_discount_approval(database, case_id)

    with pytest.raises(RoundCaseConflictError):
        decide_round_case(
            database,
            case_id,
            "approved",
            "execution-wrong",
        )

    case = get_round_case(database, case_id)
    assert case is not None
    assert case["status"] == "pending"
