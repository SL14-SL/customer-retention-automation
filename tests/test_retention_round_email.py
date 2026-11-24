"""Tests for round-specific simulated email delivery."""

import pytest

from customer_retention_automation.retention.round_cases import (
    RoundCaseConflictError,
    create_round_case,
    decide_round_case,
    get_round_case,
    register_round_approval_link,
)
from customer_retention_automation.retention.round_email import (
    create_round_email_job,
    list_round_email_jobs,
    simulate_round_email,
)
from customer_retention_automation.simulation.evaluations import (
    create_evaluation_round,
    record_evaluation,
)


@pytest.fixture
def database(tmp_path):
    database = tmp_path / "simulation.sqlite"

    for round_id, day, probability, action in [
        ("day-000", 0, 0.9, "offer_discount"),
        ("day-030", 30, 0.65, "send_email"),
        ("day-060", 60, 0.2, "no_action"),
    ]:
        create_evaluation_round(database, round_id, day)
        record_evaluation(
            database,
            round_id,
            "synthetic-0121",
            probability,
            action,
        )
        create_round_case(
            database,
            round_id,
            "synthetic-0121",
            action,
        )

    return database


def register_discount(database):
    case_id = "day-000:synthetic-0121"

    register_round_approval_link(
        database,
        case_id,
        "http://localhost:5678/form/test",
        "execution-123",
        10.0,
    )


def test_approved_discount_creates_email(database):
    case_id = "day-000:synthetic-0121"

    register_discount(database)
    decide_round_case(database, case_id, "approved", "execution-123")

    job, created = create_round_email_job(database, case_id)

    assert created
    assert job["case_id"] == case_id
    assert job["status"] == "pending"
    assert "retention offer" in job["subject"]
    assert "10%" in job["body"]


def test_discount_requires_approval(database):
    with pytest.raises(RoundCaseConflictError):
        create_round_email_job(
            database,
            "day-000:synthetic-0121",
        )


def test_outreach_creates_email_without_approval(database):
    job, created = create_round_email_job(
        database,
        "day-030:synthetic-0121",
    )

    assert created
    assert job["status"] == "pending"


def test_no_action_cannot_create_email(database):
    with pytest.raises(RoundCaseConflictError):
        create_round_email_job(
            database,
            "day-060:synthetic-0121",
        )


def test_email_job_is_idempotent(database):
    case_id = "day-030:synthetic-0121"

    first, first_created = create_round_email_job(database, case_id)
    second, second_created = create_round_email_job(database, case_id)

    assert first_created
    assert not second_created
    assert first == second
    assert len(list_round_email_jobs(database)) == 1


def test_simulated_delivery_completes_target_case(database):
    case_id = "day-030:synthetic-0121"

    create_round_email_job(database, case_id)

    job, simulated = simulate_round_email(database, case_id)

    assert simulated
    assert job["status"] == "simulated"
    assert job["simulated_at"] is not None

    case = get_round_case(database, case_id)

    assert case is not None
    assert case["status"] == "completed"

    discount = get_round_case(
        database,
        "day-000:synthetic-0121",
    )

    assert discount is not None
    assert discount["status"] == "pending"


def test_simulated_delivery_is_idempotent(database):
    case_id = "day-030:synthetic-0121"

    create_round_email_job(database, case_id)

    first, first_simulated = simulate_round_email(database, case_id)
    second, second_simulated = simulate_round_email(database, case_id)

    assert first_simulated
    assert not second_simulated
    assert first == second


def test_two_rounds_can_have_separate_emails(database):
    discount_id = "day-000:synthetic-0121"
    outreach_id = "day-030:synthetic-0121"

    register_discount(database)
    decide_round_case(database, discount_id, "approved", "execution-123")

    create_round_email_job(database, discount_id)
    create_round_email_job(database, outreach_id)

    simulate_round_email(database, discount_id)
    simulate_round_email(database, outreach_id)

    jobs = list_round_email_jobs(
        database,
        customer_id="synthetic-0121",
    )

    assert len(jobs) == 2
    assert [job["case_id"] for job in jobs] == [
        discount_id,
        outreach_id,
    ]
    assert all(job["status"] == "simulated" for job in jobs)


def test_missing_case_is_rejected(database):
    with pytest.raises(LookupError):
        create_round_email_job(database, "day-000:missing")


def test_missing_email_job_is_rejected(database):
    with pytest.raises(LookupError):
        simulate_round_email(
            database,
            "day-030:synthetic-0121",
        )


def test_rejected_discount_cannot_create_email(database):
    case_id = "day-000:synthetic-0121"

    register_discount(database)
    decide_round_case(database, case_id, "rejected", "execution-123")

    with pytest.raises(RoundCaseConflictError):
        create_round_email_job(database, case_id)
