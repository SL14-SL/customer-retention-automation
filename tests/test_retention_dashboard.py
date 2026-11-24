"""Tests for the modular retention dashboard."""

import json
from io import BytesIO
from unittest.mock import patch

import pytest

from customer_retention_automation.dashboard import api_client
from customer_retention_automation.dashboard.data_processing import (
    customer_case_history,
    prepare_approval_rows,
    prepare_case_rows,
    summarize_all_rounds,
    summarize_round_cases,
    summarize_total,
)


@pytest.fixture
def sample_cases() -> list[dict]:
    """Return representative cases from three simulation rounds."""
    return [
        {
            "case_id": "day-000:synthetic-0001",
            "round_id": "day-000",
            "customer_id": "synthetic-0001",
            "action": "offer_discount",
            "status": "completed",
            "churn_probability": 0.92,
            "proposed_discount_percent": 10.0,
            "approval_execution_id": "201",
            "created_at": "2026-11-23 10:00:00",
            "updated_at": "2026-11-23 10:05:00",
        },
        {
            "case_id": "day-000:synthetic-0002",
            "round_id": "day-000",
            "customer_id": "synthetic-0002",
            "action": "offer_discount",
            "status": "rejected",
            "churn_probability": 0.85,
            "proposed_discount_percent": 10.0,
            "approval_execution_id": "202",
            "created_at": "2026-11-23 10:00:00",
            "updated_at": "2026-11-23 10:06:00",
        },
        {
            "case_id": "day-000:synthetic-0003",
            "round_id": "day-000",
            "customer_id": "synthetic-0003",
            "action": "send_email",
            "status": "completed",
            "churn_probability": 0.75,
            "proposed_discount_percent": None,
            "created_at": "2026-11-23 10:00:00",
            "updated_at": "2026-11-23 10:01:00",
        },
        {
            "case_id": "day-030:synthetic-0001",
            "round_id": "day-030",
            "customer_id": "synthetic-0001",
            "action": "no_action",
            "status": "completed",
            "churn_probability": 0.30,
            "proposed_discount_percent": None,
            "created_at": "2026-11-24 10:00:00",
            "updated_at": "2026-11-24 10:00:00",
        },
        {
            "case_id": "day-060:synthetic-0001",
            "round_id": "day-060",
            "customer_id": "synthetic-0001",
            "action": "offer_discount",
            "status": "pending",
            "churn_probability": 0.88,
            "proposed_discount_percent": 10.0,
            "approval_execution_id": "301",
            "created_at": "2026-11-24 11:00:00",
            "updated_at": "2026-11-24 11:00:00",
        },
    ]


def test_round_summary_counts_actions_and_statuses(
    sample_cases: list[dict],
) -> None:
    summary = summarize_round_cases(sample_cases)

    assert summary["total"] == 5
    assert summary["no_action"] == 1
    assert summary["send_email"] == 1
    assert summary["offer_discount"] == 3

    assert summary["completed"] == 3
    assert summary["rejected"] == 1
    assert summary["pending"] == 1
    assert summary["dispatch_failed"] == 0


def test_discount_approval_rate_excludes_pending_cases(
    sample_cases: list[dict],
) -> None:
    summary = summarize_total(sample_cases)

    assert summary["approved_discounts"] == 1
    assert summary["rejected_discounts"] == 1
    assert summary["pending_discounts"] == 1
    assert summary["approval_rate"] == pytest.approx(0.5)


def test_empty_case_summary() -> None:
    summary = summarize_round_cases([])

    assert summary["total"] == 0
    assert summary["approved_discounts"] == 0
    assert summary["rejected_discounts"] == 0
    assert summary["approval_rate"] == 0.0


def test_summarize_all_rounds(
    sample_cases: list[dict],
) -> None:
    summaries = summarize_all_rounds(sample_cases)

    assert len(summaries) == 3
    assert [row["round_id"] for row in summaries] == [
        "day-000",
        "day-030",
        "day-060",
    ]
    assert [row["simulation_day"] for row in summaries] == [
        0,
        30,
        60,
    ]
    assert [row["total"] for row in summaries] == [
        3,
        1,
        1,
    ]


def test_prepare_case_rows_converts_risk_to_percent(
    sample_cases: list[dict],
) -> None:
    rows = prepare_case_rows(sample_cases)

    assert len(rows) == 5

    first = rows[0]
    assert first["Round"] == "day-000"
    assert first["Customer"] == "synthetic-0001"
    assert first["Churn risk (%)"] == pytest.approx(92.0)
    assert first["Discount (%)"] == 10.0


def test_prepare_approval_rows_only_includes_discounts(
    sample_cases: list[dict],
) -> None:
    rows = prepare_approval_rows(sample_cases)

    assert len(rows) == 3
    assert [row["Decision"] for row in rows] == [
        "Approved",
        "Rejected",
        "Pending",
    ]


def test_customer_history_is_ordered_by_round(
    sample_cases: list[dict],
) -> None:
    shuffled = list(reversed(sample_cases))

    history = customer_case_history(
        shuffled,
        "synthetic-0001",
    )

    assert [case["round_id"] for case in history] == [
        "day-000",
        "day-030",
        "day-060",
    ]


def test_customer_history_unknown_customer(
    sample_cases: list[dict],
) -> None:
    assert (
        customer_case_history(
            sample_cases,
            "synthetic-9999",
        )
        == []
    )


@pytest.mark.parametrize(
    "round_id",
    ["day-000", "day-030", "day-060"],
)
def test_fetch_round_cases_uses_correct_filter(
    monkeypatch: pytest.MonkeyPatch,
    round_id: str,
) -> None:
    captured = {}

    def fake_get_json(
        path: str,
        params: dict[str, str] | None = None,
    ) -> dict:
        captured["path"] = path
        captured["params"] = params
        return {"cases": [{"round_id": round_id}]}

    monkeypatch.setattr(
        api_client,
        "get_json",
        fake_get_json,
    )

    cases = api_client.fetch_round_cases(round_id)

    assert captured["path"] == "/retention/round-cases"
    assert captured["params"] == {"round_id": round_id}
    assert cases == [{"round_id": round_id}]


def test_fetch_round_cases_rejects_unknown_round() -> None:
    with pytest.raises(ValueError, match="Unknown simulation round"):
        api_client.fetch_round_cases("day-999")


def test_fetch_all_round_cases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested = []

    def fake_fetch_round_cases(round_id: str) -> list[dict]:
        requested.append(round_id)
        return [{"round_id": round_id}]

    monkeypatch.setattr(
        api_client,
        "fetch_round_cases",
        fake_fetch_round_cases,
    )

    cases = api_client.fetch_all_round_cases()

    assert requested == [
        "day-000",
        "day-030",
        "day-060",
    ]
    assert len(cases) == 3


def test_fetch_round_email_jobs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_get_json(
        path: str,
        params: dict[str, str] | None = None,
    ) -> dict:
        assert path == "/retention/round-email-jobs"
        assert params is None
        return {"jobs": [{"status": "simulated"}]}

    monkeypatch.setattr(
        api_client,
        "get_json",
        fake_get_json,
    )

    assert api_client.fetch_round_email_jobs() == [{"status": "simulated"}]


def test_fetch_churn_customer_encodes_customer_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested = []

    def fake_get_json(
        path: str,
        params: dict[str, str] | None = None,
    ) -> dict:
        requested.append(path)
        return {"customer_id": "synthetic/0001"}

    monkeypatch.setattr(
        api_client,
        "get_json",
        fake_get_json,
    )

    customer = api_client.fetch_churn_customer("synthetic/0001")

    assert requested == ["/retention/churn-simulation/customers/synthetic%2F0001"]
    assert customer["customer_id"] == "synthetic/0001"


def test_get_json_uses_configured_api_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "RETENTION_API_URL",
        "http://localhost:9999/",
    )

    payload = {"cases": [{"case_id": "test-case"}]}

    with patch.object(
        api_client,
        "urlopen",
        return_value=BytesIO(json.dumps(payload).encode()),
    ) as mocked_urlopen:
        result = api_client.get_json(
            "/retention/round-cases",
            {"round_id": "day-000"},
        )

    assert result == payload
    mocked_urlopen.assert_called_once_with(
        "http://localhost:9999/retention/round-cases?round_id=day-000",
        timeout=15,
    )


def test_get_json_wraps_connection_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failing_urlopen(url: str, timeout: int) -> None:
        raise OSError("Connection refused")

    monkeypatch.setattr(
        api_client,
        "urlopen",
        failing_urlopen,
    )

    with pytest.raises(
        api_client.RetentionAPIError,
        match="Connection refused",
    ):
        api_client.get_json("/retention/round-cases")
