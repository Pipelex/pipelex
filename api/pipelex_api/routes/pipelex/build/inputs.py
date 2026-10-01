import json
from typing import Annotated, Any, Literal, Self, Union

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pipelex.core.pipes.inputs.exceptions import NoInputsRequiredError
from pipelex.pipe_machinery.rendering.input_renderer import InputsTemplateFormat, render_inputs, render_inputs_toml
from pipelex.pipeline.exceptions import ValidateBundleError
from pydantic import BaseModel, Field, model_validator

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

INPUTS_GENERATED_MESSAGE = "Inputs template generated successfully"
NO_INPUTS_MESSAGE = "This pipe declares no inputs — the template is empty."


class BuildInputsRequest(MthdsPipeRequest):
    """The inputs-template request: the shared closure + pipe selectors, plus the two rendering axes.

    Both axes mirror `pipelex codegen inputs` exactly — `--format` and `--explicit` — and every
    combination of them is served, as on the CLI.
    """

    format: InputsTemplateFormat = Field(
        default=InputsTemplateFormat.JSON,
        description="Template encoding. `json` returns the parsed template in `inputs`; `toml` returns the raw text in `inputs_toml`.",
    )
    explicit: bool = Field(
        default=False,
        description=(
            "When true, emit the ceremonial `{concept, content}` envelope for every input. Defaults to false — the light, "
            "signature-driven shape that smart inputs accepts (a bare string for a Text input, and so on)."
        ),
    )


class BuildInputsValidReport(BaseModel):
    """The 200 **valid** arm: the example inputs template for the requested pipe.

    The template rides **one of two fields, chosen by `format`** — `inputs` (parsed object) for
    `json`, `inputs_toml` (raw text) for `toml`. TOML cannot be carried as a parsed object without
    losing what makes it worth asking for (its concept comments and key order), and the JSON case
    must stay a real object, since that is what the deploy dialog and the SDKs consume. So the two
    are separate, honestly-typed fields, and the unused one is omitted from the body entirely.

    A pipe that declares no inputs is a *valid* verdict, not an error (the CLI likewise exits 0):
    the template is simply empty, and `message` says so.
    """

    is_valid: Literal[True] = True
    pipe_ref: str = Field(..., description="The qualified pipe the template was generated for — the resolved selector.")
    requested_pipe_ref: str | None = Field(
        default=None,
        description=(
            "The `pipe_ref` as submitted. Absent when it was omitted and defaulted — to the fetched package manifest's "
            "`main_pipe` on a `method_ref` request, else to the closure's declared `main_pipe`."
        ),
    )
    format: InputsTemplateFormat = Field(..., description="The template encoding (echo of the request).")
    explicit: bool = Field(..., description="Whether the ceremonial envelope shape was emitted (echo of the request).")
    inputs: dict[str, Any] | None = Field(
        default=None,
        description="The parsed inputs template — present exactly when `format` is `json`.",
    )
    inputs_toml: str | None = Field(
        default=None,
        description="The inputs template as TOML text — present exactly when `format` is `toml`.",
    )
    message: str = Field(default=INPUTS_GENERATED_MESSAGE, description="Status message")

    @model_validator(mode="after")
    def _template_field_matches_format(self) -> Self:
        # The invariant the two-field shape exists to keep: the caller can read the field its own
        # `format` names, without probing. A route bug that set the other one would be a silent
        # contract break, so it fails loudly here instead.
        match self.format:
            case InputsTemplateFormat.JSON:
                if self.inputs is None or self.inputs_toml is not None:
                    msg = "format='json' must carry `inputs` and no `inputs_toml`"
                    raise ValueError(msg)
            case InputsTemplateFormat.TOML:
                if self.inputs_toml is None or self.inputs is not None:
                    msg = "format='toml' must carry `inputs_toml` and no `inputs`"
                    raise ValueError(msg)
        return self


# Discriminated 200 response union: the `/validate` discipline — the verdict rides `is_valid`, never
# the HTTP status.
BuildInputsResponse = Annotated[Union[BuildInputsValidReport, CrateInvalidReport], Field(discriminator="is_valid")]


def _render_report(*, requested: BuildInputsRequest, requested_pipe: RequestedPipe) -> BuildInputsValidReport:
    """Render the requested pipe's declared inputs into the valid arm, on the `format` axis.

    A pipe with no inputs raises `NoInputsRequiredError` out of the engine renderers. That is not a
    failure — it is the honest answer "run this with nothing" — so it lands on the valid arm as an
    empty template, mirroring the CLI's exit-0.
    """
    inputs: dict[str, Any] | None = None
    inputs_toml: str | None = None
    message: str = INPUTS_GENERATED_MESSAGE
    match requested.format:
        case InputsTemplateFormat.JSON:
            try:
                inputs = json.loads(render_inputs(requested_pipe.pipe, explicit=requested.explicit))
            except NoInputsRequiredError:
                inputs = {}
                message = NO_INPUTS_MESSAGE
        case InputsTemplateFormat.TOML:
            try:
                inputs_toml = render_inputs_toml(requested_pipe.pipe, explicit=requested.explicit)
            except NoInputsRequiredError:
                inputs_toml = ""
                message = NO_INPUTS_MESSAGE
    return BuildInputsValidReport(
        pipe_ref=requested_pipe.ref,
        requested_pipe_ref=requested.pipe_ref,
        format=requested.format,
        explicit=requested.explicit,
        inputs=inputs,
        inputs_toml=inputs_toml,
        message=message,
    )


@router.post(
    "/build/inputs",
    response_model=BuildInputsResponse,
    # On top of the composite router's shared 401/413/422/500: the `method_ref` closure selector the
    # envelope accepts but no server-side method registry resolves yet (shared with /resolve, /codegen).
    responses={404: PROBLEM_404_METHOD_PACKAGE, 501: PROBLEM_501_METHOD_REF},
)
async def build_inputs(request_data: BuildInputsRequest) -> JSONResponse:
    """Generate an example inputs template for a pipe (the inputs projection, per pipe).

    Rides the **same static core** as `POST /resolve` and `POST /codegen`: the closure is resolved to
    its normalized crate, the requested pipe is read live from the library that leaves loaded, and its
    *declared* inputs are rendered — the exact projection `pipelex codegen inputs` writes, on both of
    its axes (`format`, `explicit`).

    Static is the point: a template is a read of the pipe's declared IO, so there is **no dry-run
    sweep** here (that is `/validate`'s vocabulary, and `/build/runner`'s need). A valid verdict says
    the closure is structurally sound and the template matches what the pipe declares — it is *not* a
    promise the pipe runs. Ask `/validate` for that.

    This projection is deliberately **not** a `/codegen` kind: the templates are user-editable
    scaffolds, never stamped or locked, so they cannot ride the trust chain `/codegen`'s valid arm
    promises (see `CodegenRouteKind`).

    Response contract (the `/validate` discipline):

    - **Valid verdict (200, `is_valid: true`):** the template, in `inputs` or `inputs_toml` per `format`.
    - **Invalid verdict (200, `is_valid: false`):** the closure could not be parsed, loaded, or
      validated — `validation_errors[]` from pipelex's one shared builder; no template exists.
    - **No verdict (non-2xx):** a selection refusal — an unknown pipe ref, or an omitted `pipe_ref` that
      nothing defaults (no fetched-manifest `main_pipe`, and a closure declaring no — or several —
      `main_pipe`) — is an input 422 whose `error_type` is `EntryPipeNotFoundError` or
      `EntryPipeAmbiguousError`; a malformed closure selector is a request-shape 422 problem+json; a
      registry-form `method_ref` is a 501 until server-side method-registry resolution exists.

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
        # exclude_none drops the template field the `format` did not select (and an absent
        # `requested_pipe_ref`), so exactly the fields the caller's own request implies are present.
        return JSONResponse(content=report.model_dump(mode="json", by_alias=True, exclude_none=True))
    finally:
        teardown_current_library()
