import json
from typing import Annotated, Any, Literal, Union

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pipelex.codegen.crate_encoding import encode_crate_json
from pipelex.pipeline.exceptions import ValidateBundleError
from pydantic import BaseModel, Field

from pipelex_api.json_body import JsonBodyRoute
from pipelex_api.openapi_responses import PROBLEM_404_METHOD_PACKAGE
from pipelex_api.problem_view import problem_view_of
from pipelex_api.routes.pipelex.crate_ops import (
    CrateInvalidReport,
    invalid_crate_report_response,
    resolve_requested_crate,
    teardown_current_library,
)
from pipelex_api.schemas.models import MthdsFilesRequest

router = APIRouter(tags=["resolve"], route_class=JsonBodyRoute)


class ResolveValidReport(BaseModel):
    """The 200 **valid** arm: the normalized library crate, ready for any consumer's emitter.

    The crate rides as the canonical JSON encoding's object form (top-level maps key-sorted,
    non-semantic provenance dropped) — the same bytes `pipelex resolve --format json` prints, so a
    fingerprint computed from either surface agrees. Its `fingerprint` and `mthds_version` members
    ride inside the crate payload itself.
    """

    is_valid: Literal[True] = True
    crate: dict[str, Any] = Field(..., description="The normalized library crate (canonical JSON encoding, `fingerprint` included).")
    message: str = Field(default="MTHDS library resolved successfully", description="Status message")


# Discriminated 200 response union: a consumer pattern-matches the one mandatory `is_valid`
# field to learn the verdict — the same discipline as `POST /validate`.
ResolveResponse = Annotated[Union[ResolveValidReport, CrateInvalidReport], Field(discriminator="is_valid")]


@router.post(
    "/resolve",
    response_model=ResolveResponse,
    # On top of the composite router's shared 401/413/422/500: the `method_ref` package-not-found 404.
    responses={404: PROBLEM_404_METHOD_PACKAGE},
    # NOT tagged `x-mthds-protocol`: the MTHDS Protocol is the five operations `execute`, `start`,
    # `validate`, `models`, `version`. `/resolve` is a Pipelex API extension. The *artifact* it
    # emits — the normalized library crate — IS standard-owned (the MTHDS Library Crate Format), so
    # its wire fields stay brand-neutral; the route that serves it over HTTP is ours.
)
async def resolve_mthds(request: Request, request_data: MthdsFilesRequest) -> JSONResponse:
    """Resolve a library closure into its normalized crate (Pipelex API extension).

    Resolution is a first-class language operation alongside validation: assemble the closure from
    the inline `files[]`, load + statically validate the library, and emit the **normalized
    library crate** (fully qualified refs, refinement flattened, natives materialized, fingerprint
    set) — the artifact shape the MTHDS standard specifies as the Library Crate Format. It runs no
    dry-run sweep — runnability is `/validate`'s vocabulary.

    Response contract (the `/validate` discipline):

    - **Valid verdict (200, `is_valid: true`):** the crate on the valid arm.
    - **Invalid verdict (200, `is_valid: false`):** the library could not be parsed, loaded, or
      validated — `errors[]`, one problem item per error.
    - **No verdict (non-2xx):** a malformed request body (neither/both closure selectors, an
      over-limit file) is a request-shape 422; a registry-form `method_ref` is a 422
      `request.unsupported` until server-side method registry resolution exists; auth is 401/403;
      server fault is 5xx. All `application/problem+json` documents with a registry `code`, via the
      global handlers.
    """
    try:
        # Whole-closure route: no pipe is selected here, so the manifest's `main_pipe` beside the crate is unused.
        crate = (await resolve_requested_crate(request_data)).crate
    except ValidateBundleError as validate_error:
        return invalid_crate_report_response(validate_error, view=problem_view_of(request))
    try:
        report = ResolveValidReport(crate=json.loads(encode_crate_json(crate)))
        return JSONResponse(content=report.model_dump(mode="json", by_alias=True))
    finally:
        teardown_current_library()
