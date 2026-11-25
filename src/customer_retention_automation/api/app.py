"""FastAPI application for synthetic customer retention automation."""

from fastapi import FastAPI

from customer_retention_automation.api.routes.cases import (
    router as cases_router,
)
from customer_retention_automation.api.routes.emails import (
    router as emails_router,
)
from customer_retention_automation.api.routes.health import (
    router as health_router,
)
from customer_retention_automation.api.routes.simulation import (
    router as simulation_router,
)

app = FastAPI(
    title="Customer Retention Automation API",
    description=(
        "Synthetic churn simulation, round-specific retention "
        "cases, human approvals and simulated emails."
    ),
)

app.include_router(health_router)
app.include_router(simulation_router)
app.include_router(cases_router)
app.include_router(emails_router)
