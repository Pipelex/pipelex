from fastapi import APIRouter

from api.openapi_responses import COMMON_PROBLEM_RESPONSES

from .pipelex import router as pipelex_router

# NOTE: the version router is NOT composed here — `GET /version` is always
# public (protocol handshake), so `api.main` mounts it under `/v1` directly,
# WITHOUT the auth dependency this composite router gets wrapped in.
#
# `responses=` here merges into EVERY operation composed below (FastAPI's
# `include_router` folds the including router's `responses` into each route's
# own, route-level entries winning on a status collision). It documents the four
# failures every auth-wrapped `/v1` route shares — 401 from the router-level auth
# dependency `api.main` wraps this in, 413 from the body-size middleware, 422 for
# request-shape/input-domain rejections, 500 for the server-fault floor — so each
# route only has to declare the extra statuses it alone can produce. Declaring the
# 422 is also what suppresses FastAPI's automatic `HTTPValidationError` response,
# whose media type (`application/json`) and schema both contradict the RFC 7807
# document the global handlers actually emit.
router = APIRouter(responses=COMMON_PROBLEM_RESPONSES)

router.include_router(pipelex_router)
