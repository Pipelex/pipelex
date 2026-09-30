import json
from typing import Annotated, Any, Literal, Self, Union

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pipelex.core.concepts.concept_representation_generator import ConceptRepresentationFormat
from pipelex.pipe_machinery.rendering.output_renderer import render_output
from pipelex.pipeline.exceptions import ValidateBundleError
from pydantic import BaseModel, Field, model_validator

from pipelex_api.errors import raise_validation_error
from pipelex_api.openapi_responses import PROBLEM_404_METHOD_PACKAGE, PROBLEM_501_METHOD_REF
from pipelex_api.routes.pipelex.crate_ops import (
    CrateInvalidReport,
    RequestedPipe,
    invalid_crate_report_response,
    resolve_requested_crate,
    resolve_requested_pipe,
    teardown_current_library,
)
from pipelex_api.schemas.models import MthdsPipeRequest

router = APIRouter(tags=["build"])


class BuildOutputRequest(MthdsPipeRequest):
    """The output-representation request: the shared closure + pipe selectors, plus the format axis."""

    format: ConceptRepresentationFormat = Field(
        default=ConceptRepresentationFormat.SCHEMA,
        description=(
            "Representation to render. `schema` (JSON Schema) and `json` (example value) return a parsed object in "
            "`output`; `python` returns Python source in `output_python`."
        ),
    )


class BuildOutputValidReport(BaseModel):
    """The 200 **valid** arm: the example output representation for the requested pipe.

    The representation rides **one of two fields, chosen by `format`**, for the same reason
    `/build/inputs` splits `inputs` / `inputs_toml`: `schema` and `json` are objects, `python` is
    source text. (Before this split the route parsed *every* format as JSON, so `format=python` was a
    hard 500 — it fed Python source to `json.loads`.)
    """

    is_valid: Literal[True] = True
    pipe_ref: str = Field(..., description="The qualified pipe the representation was generated for — the resolved selector.")
    requested_pipe_ref: str | None = Field(
        default=None,
        description=(
            "The `pipe_ref` as submitted. Absent when it was omitted and defaulted — to the fetched package manifest's "
            "`main_pipe` on a `method_ref` request, else to the closure's declared `main_pipe`."
        ),
    )
    format: ConceptRepresentationFormat = Field(..., description="The representation format (echo of the request).")
    output: dict[str, Any] | None = Field(
        default=None,
        description="The parsed output representation — present exactly when `format` is `schema` or `json`.",
    )
    output_python: str | None = Field(
        default=None,
        description="The output representation as Python source — present exactly when `format` is `python`.",
    )
    message: str = Field(default="Output representation generated successfully", description="Status message")

    @model_validator(mode="after")
    def _representation_field_matches_format(self) -> Self:
        # Same invariant as `/build/inputs`: the caller reads the field its own `format` names.
        match self.format:
            case ConceptRepresentationFormat.SCHEMA | ConceptRepresentationFormat.JSON:
                if self.output is None or self.output_python is not None:
                    msg = "format='schema'/'json' must carry `output` and no `output_python`"
                    raise ValueError(msg)
            case ConceptRepresentationFormat.PYTHON:
                if self.output_python is None or self.output is not None:
                    msg = "format='python' must carry `output_python` and no `output`"
                    raise ValueError(msg)
        return self


# Discriminated 200 response union: the `/validate` discipline — the verdict rides `is_valid`, never
# the HTTP status.
BuildOutputResponse = Annotated[Union[BuildOutputValidReport, CrateInvalidReport], Field(discriminator="is_valid")]


def _render_report(*, requested: BuildOutputRequest, requested_pipe: RequestedPipe) -> BuildOutputValidReport:
    """Render the requested pipe's declared output into the valid arm, on the `format` axis.

    `render_output` raises a bare `ValueError` (documented in its docstring) when the pipe's output is
    `native.Anything` and no concrete option can be determined — a fact about the *requested pipe*,
    not about the closure, so it is a no-verdict 422 rather than an invalid-crate verdict.
    """
    output: dict[str, Any] | None = None
    output_python: str | None = None
    try:
        rendered = render_output(requested_pipe.pipe, output_format=requested.format)
    except ValueError as exc:
        raise_validation_error(f"Cannot render the output representation of pipe '{requested_pipe.ref}': {exc}")
    match requested.format:
        case ConceptRepresentationFormat.SCHEMA | ConceptRepresentationFormat.JSON:
            output = json.loads(rendered)
        case ConceptRepresentationFormat.PYTHON:
            output_python = rendered
    return BuildOutputValidReport(
        pipe_ref=requested_pipe.ref,
        requested_pipe_ref=requested.pipe_ref,
        format=requested.format,
        output=output,
        output_python=output_python,
    )


@router.post(
    "/build/output",
    response_model=BuildOutputResponse,
    # On top of the composite router's shared 401/413/422/500: the `method_ref` closure selector the
    # envelope accepts but no server-side method registry resolves yet (shared with /resolve, /codegen).
    responses={404: PROBLEM_404_METHOD_PACKAGE, 501: PROBLEM_501_METHOD_REF},
)
async def build_output(request_data: BuildOutputRequest) -> JSONResponse:
    """Generate an example output representation for a pipe (the output projection, per pipe).

    Rides the **same static core** as `POST /resolve`, `POST /codegen` and `POST /build/inputs`: the
    closure is resolved to its normalized crate, the requested pipe is read live from the library that
    leaves loaded, and its *declared* output is rendered.

    Static is the point: the representation is a read of the pipe's declared IO, so there is **no
    dry-run sweep** here. A valid verdict says the closure is structurally sound and the shape matches
    what the pipe declares — it is *not* a promise the pipe runs. Ask `/validate` for that.

    Response contract (the `/validate` discipline):

    - **Valid verdict (200, `is_valid: true`):** the representation, in `output` or `output_python` per `format`.
    - **Invalid verdict (200, `is_valid: false`):** the closure could not be parsed, loaded, or
      validated — `validation_errors[]`; no representation exists.
    - **No verdict (non-2xx):** a selection refusal — an unknown pipe ref, or an omitted `pipe_ref` that
      nothing defaults (no fetched-manifest `main_pipe`, and a closure declaring no — or several —
      `main_pipe`) — is an input 422 whose `error_type` is `EntryPipeNotFoundError` or
      `EntryPipeAmbiguousError`; a pipe whose `native.Anything` output has no determinable shape, or a
      malformed closure selector, is a request-shape 422 problem+json; a registry-form `method_ref` is a 501 until server-side
      method-registry resolution exists.

    An omitted `pipe_ref` defaults the way a run by address does: to the fetched package manifest's
    `main_pipe` on a `method_ref` request, else to the closure's own declared `main_pipe`.
    """
    try:
        resolved = resolve_requested_crate(request_data)
    except ValidateBundleError as validate_error:
        return invalid_crate_report_response(validate_error.to_error_report())
    try:
        requested_pipe = resolve_requested_pipe(
            resolved.crate,
            pipe_ref=request_data.pipe_ref,
            manifest_main_pipe=resolved.manifest_main_pipe,
        )
        report = _render_report(requested=request_data, requested_pipe=requested_pipe)
        # exclude_none drops the representation field the `format` did not select (and an absent
        # `requested_pipe_ref`), so exactly the fields the caller's own request implies are present.
        return JSONResponse(content=report.model_dump(mode="json", by_alias=True, exclude_none=True))
    finally:
        teardown_current_library()
