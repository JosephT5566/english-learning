"""HTTP health contracts for process liveness and dependency readiness."""

from typing import Literal

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel

from app.database import check_database_readiness


class LivenessResponse(BaseModel):
    """Response returned when the API process can handle requests."""

    status: Literal["ok"] = "ok"


class ReadinessChecks(BaseModel):
    """Public dependency states included in a readiness response."""

    database: Literal["ok", "unavailable"]


class ReadinessResponse(BaseModel):
    """Response describing whether the API is ready to receive traffic."""

    status: Literal["ready", "not_ready"]
    checks: ReadinessChecks


router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", response_model=LivenessResponse)
def get_liveness() -> LivenessResponse:
    """Report process liveness without querying PostgreSQL."""

    return LivenessResponse()


@router.get("/ready", response_model=ReadinessResponse)
def get_readiness(request: Request, response: Response) -> ReadinessResponse:
    """Report readiness from a fresh database probe.

    Args:
        request: Current request used to access the application-scoped engine.
        response: Mutable response used to return HTTP 503 when unavailable.

    Returns:
        A safe response containing only the public database state.
    """

    if check_database_readiness(request.app.state.database_engine):
        return ReadinessResponse(
            status="ready",
            checks=ReadinessChecks(database="ok"),
        )

    response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(
        status="not_ready",
        checks=ReadinessChecks(database="unavailable"),
    )
