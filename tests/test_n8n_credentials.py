"""Tests for automated n8n credential provisioning."""

import json
from pathlib import Path
from runpy import run_path

import pytest

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "create_n8n_credential.py"
)

credential_module = run_path(str(SCRIPT_PATH))

CREDENTIAL_ID = credential_module["CREDENTIAL_ID"]
build_credential = credential_module["build_credential"]
main = credential_module["main"]


def test_credential_has_expected_structure():
    credential = build_credential("test-secret")

    assert credential == {
        "id": "1OoEC812MPns7ct1",
        "name": "Retention API",
        "type": "httpHeaderAuth",
        "data": {
            "name": "X-API-Key",
            "value": "test-secret",
        },
    }


def test_empty_api_key_is_rejected():
    with pytest.raises(ValueError, match="must not be empty"):
        build_credential("")


def test_missing_environment_variable_is_rejected(
    monkeypatch,
    capsys,
):
    monkeypatch.delenv("RETENTION_API_KEY", raising=False)

    with pytest.raises(SystemExit) as exc:
        main()

    assert exc.value.code == 1
    assert "not configured" in capsys.readouterr().err


def test_generator_uses_environment_variable(
    monkeypatch,
    capsys,
):
    monkeypatch.setenv(
        "RETENTION_API_KEY",
        "test-secret",
    )

    main()

    payload = json.loads(capsys.readouterr().out)

    assert len(payload) == 1
    assert payload[0] == build_credential("test-secret")


def test_workflow_exports_reference_expected_credential():
    workflow_directory = Path("n8n/workflows")

    expected_nodes = {
        "customer-retention-automation.json": {
            "Create Retention Case",
            "Mark Dispatch Failed",
            "Create Outreach Case",
            "Create Contact Email",
            "Simulate Contact Email",
            "Record No Action",
        },
        "retention-approval.json": {
            "Save Approval",
            "Save Rejection",
            "Register Approval Link",
            "Create Email Job",
            "Simulate Email",
        },
    }

    for filename, node_names in expected_nodes.items():
        workflow = json.loads(
            (workflow_directory / filename).read_text(encoding="utf-8")
        )

        nodes = {node["name"]: node for node in workflow["nodes"]}

        for name in node_names:
            credential = nodes[name]["credentials"]["httpHeaderAuth"]

            assert credential["id"] == CREDENTIAL_ID
            assert credential["name"] == "Retention API"
