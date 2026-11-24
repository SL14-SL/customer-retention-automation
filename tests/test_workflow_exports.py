"""Validate the exported n8n workflows and their references."""

import json
from pathlib import Path

WORKFLOW_DIRECTORY = Path(__file__).resolve().parents[1] / "n8n" / "workflows"


def load_workflow(filename: str) -> dict:
    """Read one exported n8n workflow."""
    path = WORKFLOW_DIRECTORY / filename
    return json.loads(path.read_text(encoding="utf-8"))


def test_workflow_names_and_ids() -> None:
    main = load_workflow("customer-retention-automation.json")
    approval = load_workflow("retention-approval.json")

    assert main["name"] == "Customer Retention Automation"
    assert approval["name"] == "Retention Approval"

    assert main["id"]
    assert approval["id"]
    assert main["id"] != approval["id"]


def test_subworkflow_references() -> None:
    main = load_workflow("customer-retention-automation.json")
    approval = load_workflow("retention-approval.json")

    nodes = [
        node
        for node in main["nodes"]
        if node["type"] == "n8n-nodes-base.executeWorkflow"
    ]

    assert len(nodes) == 1

    reference = nodes[0]["parameters"]["workflowId"]

    assert reference["value"] == approval["id"]


def test_workflow_node_ids_are_unique() -> None:
    for filename in (
        "customer-retention-automation.json",
        "retention-approval.json",
    ):
        workflow = load_workflow(filename)
        node_ids = [node["id"] for node in workflow["nodes"]]

        assert len(node_ids) == len(set(node_ids))


def test_no_deactivated_retry_nodes() -> None:
    main = load_workflow("customer-retention-automation.json")

    forbidden_names = {
        "Retry Failed Dispatch",
        "Retry Allowed?",
        "Start Retention Approval1",
    }

    actual_names = {node["name"] for node in main["nodes"]}

    assert not forbidden_names.intersection(actual_names)
