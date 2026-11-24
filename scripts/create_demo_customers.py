"""Generate reproducible synthetic customers for the retention demo."""

import argparse
import random
import sqlite3
from pathlib import Path

DEFAULT_CUSTOMER_COUNT = 300
DEFAULT_SEED = 42


def generate_customers(
    count: int = DEFAULT_CUSTOMER_COUNT,
    seed: int = DEFAULT_SEED,
) -> list[tuple[str, float]]:
    """Generate deterministic customer IDs and synthetic risk scores."""
    if count < 1:
        raise ValueError("Customer count must be positive")

    rng = random.Random(seed)

    return [
        (
            f"synthetic-{index:04d}",
            round(rng.uniform(0, 1), 4),
        )
        for index in range(1, count + 1)
    ]


def create_database(
    database: Path,
    *,
    count: int = DEFAULT_CUSTOMER_COUNT,
    seed: int = DEFAULT_SEED,
) -> None:
    """Create a new SQLite customer database without overwriting data."""
    if database.exists():
        raise FileExistsError(f"Database already exists: {database}")

    customers = generate_customers(count=count, seed=seed)

    database.parent.mkdir(parents=True, exist_ok=True)

    try:
        with sqlite3.connect(database) as connection:
            connection.execute(
                """
                CREATE TABLE customers (
                    customerID TEXT PRIMARY KEY,
                    churn_probability REAL NOT NULL
                        CHECK (
                            churn_probability >= 0
                            AND churn_probability <= 1
                        )
                )
                """
            )

            connection.executemany(
                """
                INSERT INTO customers (
                    customerID,
                    churn_probability
                )
                VALUES (?, ?)
                """,
                customers,
            )
    except Exception:
        database.unlink(missing_ok=True)
        raise

    print(f"Created {database}")
    print(f"Customers: {len(customers)}")
    print(f"Random seed: {seed}")
    print("All customers and churn probabilities are synthetic.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database",
        type=Path,
        default=Path("data/customers.sqlite"),
    )
    parser.add_argument(
        "--customers",
        type=int,
        default=DEFAULT_CUSTOMER_COUNT,
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
    )

    args = parser.parse_args()

    create_database(
        args.database,
        count=args.customers,
        seed=args.seed,
    )


if __name__ == "__main__":
    main()
