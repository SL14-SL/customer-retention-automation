"""Configuration helpers for the retention API."""

import os
from pathlib import Path


def churn_simulation_database() -> Path:
    """Return the SQLite database used for the retention simulation."""
    return Path(
        os.getenv(
            "CHURN_SIM_DATABASE",
            "data/retention_churn_sim.sqlite",
        )
    )
