"""Tests for API-key authentication."""

from fastapi.testclient import TestClient

from customer_retention_automation.api.app import app

client = TestClient(app)

WRITE_ENDPOINT = "/retention/round-cases"


def test_demo_mode_allows_requests_without_api_key(monkeypatch):
    monkeypatch.delenv("RETENTION_API_KEY", raising=False)

    response = client.post(
        WRITE_ENDPOINT,
        json={},
    )

    # Authentication is disabled, so validation handles the request.
    assert response.status_code == 422


def test_missing_api_key_is_rejected(monkeypatch):
    monkeypatch.setenv("RETENTION_API_KEY", "test-secret")

    response = client.post(
        WRITE_ENDPOINT,
        json={},
    )

    assert response.status_code == 401


def test_invalid_api_key_is_rejected(monkeypatch):
    monkeypatch.setenv("RETENTION_API_KEY", "test-secret")

    response = client.post(
        WRITE_ENDPOINT,
        headers={"X-API-Key": "wrong-secret"},
        json={},
    )

    assert response.status_code == 401


def test_valid_api_key_is_accepted(monkeypatch):
    monkeypatch.setenv("RETENTION_API_KEY", "test-secret")

    response = client.post(
        WRITE_ENDPOINT,
        headers={"X-API-Key": "test-secret"},
        json={},
    )

    # Request passes authentication and reaches payload validation.
    assert response.status_code == 422


def test_healthcheck_does_not_require_api_key(monkeypatch):
    monkeypatch.setenv("RETENTION_API_KEY", "test-secret")

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_read_only_endpoints_remain_public(monkeypatch):
    monkeypatch.setenv("RETENTION_API_KEY", "test-secret")

    response = client.get("/retention/round-cases")

    assert response.status_code == 200
