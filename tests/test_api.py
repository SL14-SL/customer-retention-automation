"""Integration tests for the customer retention HTTP API."""

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from customer_retention_automation.api.app import app
from customer_retention_automation.simulation.batch import (
    evaluate_customer_batch,
)


@pytest.fixture(autouse=True)
def disable_api_authentication(monkeypatch):
    """Run existing API tests independently of local API credentials."""
    monkeypatch.delenv("RETENTION_API_KEY", raising=False)


@pytest.fixture
def client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> TestClient:
    """Create an isolated customer and retention database."""
    customers = tmp_path / "customers.sqlite"
    retention = tmp_path / "retention.sqlite"

    with sqlite3.connect(customers) as connection:
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
            INSERT INTO customers VALUES (?, ?)
            """,
            [
                ("synthetic-0001", 0.9),
                ("synthetic-0002", 0.4),
            ],
        )

    evaluate_customer_batch(
        customer_database=customers,
        retention_database=retention,
        round_id="day-000",
        simulation_day=0,
        with_churn=True,
    )

    monkeypatch.setenv(
        "CHURN_SIM_DATABASE",
        str(retention),
    )

    return TestClient(app)


def test_health(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_simulation_overview(client: TestClient) -> None:
    response = client.get("/retention/churn-simulation/overview")

    assert response.status_code == 200

    data = response.json()

    assert data["population"] == 2
    assert data["active_customers"] == 2
    assert data["churned_customers"] == 0
    assert len(data["rounds"]) == 1


def test_round_customers(client: TestClient) -> None:
    response = client.get("/retention/churn-simulation/rounds/day-000/customers")

    assert response.status_code == 200
    assert response.json()["count"] == 2


def test_unknown_round(client: TestClient) -> None:
    response = client.get("/retention/churn-simulation/rounds/missing/customers")

    assert response.status_code == 404


def test_customer_history(client: TestClient) -> None:
    response = client.get("/retention/churn-simulation/customers/synthetic-0001")

    assert response.status_code == 200

    data = response.json()

    assert data["customer_id"] == "synthetic-0001"
    assert data["count"] == 1
    assert data["status"] == "active"


def test_unknown_customer(client: TestClient) -> None:
    response = client.get("/retention/churn-simulation/customers/missing")

    assert response.status_code == 404


def test_create_and_retrieve_case(client: TestClient) -> None:
    evaluations = client.get(
        "/retention/churn-simulation/rounds/day-000/customers"
    ).json()["customers"]

    customer = evaluations[0]

    payload = {
        "round_id": customer["round_id"],
        "customer_id": customer["customer_id"],
        "action": customer["action"],
    }

    response = client.post(
        "/retention/round-cases",
        json=payload,
    )

    assert response.status_code == 201

    case = response.json()
    case_id = case["case_id"]

    assert case["customer_id"] == customer["customer_id"]
    assert case["action"] == customer["action"]

    lookup = client.get(f"/retention/round-cases/{case_id}")

    assert lookup.status_code == 200
    assert lookup.json()["case_id"] == case_id


def test_duplicate_case_returns_409(client: TestClient) -> None:
    customer = client.get(
        "/retention/churn-simulation/rounds/day-000/customers"
    ).json()["customers"][0]

    payload = {
        "round_id": customer["round_id"],
        "customer_id": customer["customer_id"],
        "action": customer["action"],
    }

    first = client.post(
        "/retention/round-cases",
        json=payload,
    )
    second = client.post(
        "/retention/round-cases",
        json=payload,
    )

    assert first.status_code == 201
    assert second.status_code == 409


def test_unknown_case_returns_404(client: TestClient) -> None:
    response = client.get("/retention/round-cases/missing")

    assert response.status_code == 404


def test_invalid_case_action_returns_422(
    client: TestClient,
) -> None:
    response = client.post(
        "/retention/round-cases",
        json={
            "round_id": "day-000",
            "customer_id": "synthetic-0001",
            "action": "invalid_action",
        },
    )

    assert response.status_code == 422


def test_initial_email_outbox_empty(
    client: TestClient,
) -> None:
    response = client.get("/retention/round-email-jobs")

    assert response.status_code == 200
    assert response.json()["count"] == 0
