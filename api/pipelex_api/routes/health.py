from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Body of `GET /health`."""

    status: str = Field(..., description="Always `ok` — the endpoint answers only when the process is serving.")
    message: str = Field(..., description="Human-readable confirmation that the server is up.")


@router.get("/health", summary="Liveness probe")
async def get_health() -> HealthResponse:
    """Report that this server process is up and serving. No auth required.

    A pure liveness probe for load balancers and orchestrators: it touches no
    dependency (no pipelex library load, no storage, no inference provider), so
    a 200 means "the process is serving", never "the deployment is correctly
    configured". It is mounted outside the `/v1` base path and outside the auth
    dependency, and cannot fail.
    """
    return HealthResponse(status="ok", message="Pipelex API is running")
