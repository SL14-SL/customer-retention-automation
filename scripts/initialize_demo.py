"""Initialize reproducible synthetic customer retention demo data."""

import argparse
import subprocess
import sys
from pathlib import Path

ROUNDS = (
    ("day-000", 0),
    ("day-030", 30),
    ("day-060", 60),
)


def initialize_demo(data_dir: Path, customers: int = 300) -> None:
    """Create customers and run the three evaluation rounds."""
    data_dir.mkdir(parents=True, exist_ok=True)

    customer_database = data_dir / "customers.sqlite"
    retention_database = data_dir / "retention_churn_sim.sqlite"

    if not customer_database.exists():
        print("Generating synthetic customers...", flush=True)
        subprocess.run(
            [
                sys.executable,
                "scripts/create_demo_customers.py",
                "--database",
                str(customer_database),
                "--customers",
                str(customers),
            ],
            check=True,
        )
    else:
        print("Existing customer database found.", flush=True)

    for round_id, simulation_day in ROUNDS:
        print(f"\nInitializing {round_id}...", flush=True)

        subprocess.run(
            [
                sys.executable,
                "-m",
                "customer_retention_automation.simulation.batch",
                "--customer-database",
                str(customer_database),
                "--retention-database",
                str(retention_database),
                "--round-id",
                round_id,
                "--simulation-day",
                str(simulation_day),
                "--with-churn",
            ],
            check=True,
        )

    print("\nDemo initialization completed.", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data"),
    )
    parser.add_argument(
        "--customers",
        type=int,
        default=300,
    )

    args = parser.parse_args()

    initialize_demo(
        data_dir=args.data_dir,
        customers=args.customers,
    )


if __name__ == "__main__":
    main()
