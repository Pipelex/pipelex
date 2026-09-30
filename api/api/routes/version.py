"""`GET /version` — the MTHDS Protocol version handshake.

Replaces the former `GET /pipelex_version` and `GET /api_version` routes with
the single protocol route. ALWAYS PUBLIC: `api.main` mounts this router under
`/v1` WITHOUT the auth dependency (exactly like `/health`), because clients use
it for handshake / feature detection before they have credentials.
"""

from importlib.metadata import PackageNotFoundError, version

from fastapi import APIRouter
from mthds.protocol.protocol import PROTOCOL_VERSION
from pipelex.pipeline.runner import PipelexVersionInfo

from api.error_types import ErrorType
from api.errors import raise_internal_server_error
from api.openapi_responses import PROBLEM_500

router = APIRouter(tags=["discovery"])

IMPLEMENTATION_NAME = "pipelex-api"


@router.get(
    "/version",
    # This router mounts OUTSIDE the composite `/v1` router (public handshake — see the module
    # docstring), so it inherits none of that router's shared problem responses. It takes no
    # request body and no parameters, so there is nothing to reject: 500 (absent package
    # metadata) is the only failure it can produce, and it never answers 401.
    responses={500: PROBLEM_500},
    openapi_extra={"x-mthds-protocol": True},
)
async def get_version() -> PipelexVersionInfo:
    """Protocol and implementation versions (MTHDS Protocol `GET /version`).

    The handshake clients use for feature detection: `implementation`
    identifies this runner, `implementation_version` is this server package's
    version, and `runtime_version` is the underlying pipelex runtime version.
    """
    try:
        implementation_version = version(IMPLEMENTATION_NAME)
        runtime_version = version("pipelex")
    except PackageNotFoundError as exc:
        raise_internal_server_error(f"Package metadata is not available: {exc}", error_type=ErrorType.PACKAGE_NOT_FOUND)
    return PipelexVersionInfo(
        protocol_version=PROTOCOL_VERSION,
        runner_version=implementation_version,
        implementation=IMPLEMENTATION_NAME,
        implementation_version=implementation_version,
        runtime_version=runtime_version,
    )
