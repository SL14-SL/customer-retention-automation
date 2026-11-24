"""Batch evaluation of synthetic customers across simulation rounds."""

import argparse
import os
import sqlite3
from pathlib import Path

from customer_retention_automation.simulation.churn import (
    DEFAULT_CHURN_RATE,
    list_active_customers,
    simulate_churn_period,
)
from customer_retention_automation.simulation.evaluations import (
    create_evaluation_round,
    record_evaluation,
)
from customer_retention_automation.simulation.simulation import (
    simulate_evaluation,
)


def load_customers(
    database: Path,
) -> list[tuple[str, float]]:
    """Load synthetic customers from SQLite."""
    if not database.is_file():
        raise FileNotFoundError(f"Customer database not found: {database}")

    with sqlite3.connect(database) as connection:
        rows = connection.execute(
            """
            SELECT customerID, churn_probability
            FROM customers
            ORDER BY customerID
            """
        ).fetchall()

    if not rows:
        raise ValueError("Customer database contains no customers")

    customer_ids = [str(row[0]) for row in rows]

    if len(customer_ids) != len(set(customer_ids)):
        raise ValueError("Customer database contains duplicate IDs")

    return [(str(customer_id), float(probability)) for customer_id, probability in rows]


def evaluate_customer_batch(
    customer_database: Path,
    retention_database: Path,
    round_id: str,
    simulation_day: int,
    *,
    with_churn: bool = False,
    churn_rate: float = DEFAULT_CHURN_RATE,
) -> dict:
    """Evaluate customers and optionally simulate cancellations."""
    customers = load_customers(customer_database)

    if with_churn and (simulation_day < 0 or simulation_day % 30 != 0):
        raise ValueError("Churn-enabled evaluation requires days 0, 30, 60, ...")

    customer_ids = [customer_id for customer_id, _ in customers]

    churn_result = None
    active_ids = set(customer_ids)

    if with_churn:
        if simulation_day > 0:
            churn_result = simulate_churn_period(
                database=retention_database,
                customer_ids=customer_ids,
                simulation_day=simulation_day,
                churn_rate=churn_rate,
            )

        active_ids = set(
            list_active_customers(
                database=retention_database,
                customer_ids=customer_ids,
                simulation_day=simulation_day,
            )
        )

    evaluations = [
        simulate_evaluation(
            customer_id=customer_id,
            baseline_probability=probability,
            simulation_day=simulation_day,
        )
        for customer_id, probability in customers
        if customer_id in active_ids
    ]

    round_created = create_evaluation_round(
        retention_database,
        round_id=round_id,
        simulation_day=simulation_day,
    )

    created = 0
    skipped = 0

    for evaluation in evaluations:
        inserted = record_evaluation(
            retention_database,
            round_id=round_id,
            customer_id=evaluation["customer_id"],
            churn_probability=evaluation["churn_probability"],
            action=evaluation["action"],
        )

        if inserted:
            created += 1
        else:
            skipped += 1

    result = {
        "round_id": round_id,
        "simulation_day": simulation_day,
        "round_created": round_created,
        "customers_evaluated": len(evaluations),
        "created": created,
        "skipped_duplicates": skipped,
    }

    if with_churn:
        result["customers_active"] = len(active_ids)
        result["customers_churned"] = len(customer_ids) - len(active_ids)
        result["new_churn_events"] = (
            churn_result["new_churn_events"] if churn_result is not None else 0
        )

    return result


def main() -> None:
    """Run a synthetic evaluation round from the command line."""
    parser = argparse.ArgumentParser(
        description="Run a synthetic retention evaluation round."
    )

    parser.add_argument("--round-id", required=True)
    parser.add_argument(
        "--simulation-day",
        type=int,
        required=True,
    )
    parser.add_argument(
        "--customer-database",
        type=Path,
        default=Path(
            os.getenv(
                "CUSTOMER_DATABASE",
                "data/customers.sqlite",
            )
        ),
    )
    parser.add_argument(
        "--retention-database",
        type=Path,
        default=Path(
            os.getenv(
                "RETENTION_DATABASE",
                "data/retention_churn_sim.sqlite",
            )
        ),
    )
    parser.add_argument(
        "--with-churn",
        action="store_true",
    )
    parser.add_argument(
        "--churn-rate",
        type=float,
        default=DEFAULT_CHURN_RATE,
    )

    args = parser.parse_args()

    result = evaluate_customer_batch(
        customer_database=args.customer_database,
        retention_database=args.retention_database,
        round_id=args.round_id,
        simulation_day=args.simulation_day,
        with_churn=args.with_churn,
        churn_rate=args.churn_rate,
    )

    for key, value in result.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
