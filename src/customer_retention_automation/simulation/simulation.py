"""Deterministic synthetic churn-risk simulation."""

import hashlib
import math


def determine_action(churn_probability: float) -> str:
    """Select a demo retention action from a synthetic risk score."""
    if not math.isfinite(churn_probability) or not 0 <= churn_probability <= 1:
        raise ValueError("Churn probability must be between 0 and 1")

    if churn_probability >= 0.8:
        return "offer_discount"
    if churn_probability >= 0.5:
        return "send_email"
    return "no_action"


def simulate_evaluation(
    customer_id: str,
    baseline_probability: float,
    simulation_day: int,
) -> dict:
    """Generate a reproducible evaluation for a simulated day."""
    if not customer_id.strip():
        raise ValueError("Customer ID must not be empty")

    if not math.isfinite(baseline_probability) or not 0 <= baseline_probability <= 1:
        raise ValueError("Baseline probability must be between 0 and 1")

    if simulation_day < 0:
        raise ValueError("Simulation day must be non-negative")

    if simulation_day == 0:
        probability = baseline_probability
    else:
        # Stable across processes, machines and Python hash seeds.
        key = f"retention-demo-v1:{customer_id}:{simulation_day}"
        digest = hashlib.sha256(key.encode("utf-8")).digest()

        fraction = int.from_bytes(digest[:8], "big") / (2**64 - 1)

        # Synthetic movement between -0.20 and +0.20.
        change = (fraction * 2 - 1) * 0.20
        probability = max(
            0.0,
            min(1.0, baseline_probability + change),
        )

    probability = round(probability, 4)

    return {
        "customer_id": customer_id,
        "simulation_day": simulation_day,
        "churn_probability": probability,
        "action": determine_action(probability),
    }
