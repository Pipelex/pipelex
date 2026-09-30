from typing import TYPE_CHECKING, Annotated, Any, Literal, Union

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pipelex.interpreter_hub import get_own_pipes, get_pipe_library
from pipelex.pipeline.build_pipe_io_artifacts import build_pipe_io_artifacts
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.input_form import InputForm, OutputForm
from pipelex.pipeline.pipe_io_contracts import PipeIOContracts
from pipelex.pipeline.validate_bundle import build_pending_signatures
from pipelex.tools.typing.pydantic_utils import empty_list_factory_of
from pydantic import BaseModel, Field

from api.openapi_responses import PROBLEM_404_METHOD_PACKAGE, PROBLEM_501_METHOD_REF
from api.routes.pipelex.crate_ops import (
    CrateInvalidReport,
    RequestedPipe,
    invalid_crate_report_response,
    resolve_requested_crate,
    resolve_requested_pipe,
    select_default_pipe,
    teardown_current_library,
)
from api.schemas.models import MthdsFileItem, MthdsPipeRequest

if TYPE_CHECKING:
    from pipelex.pipe_machinery.pipe_abstract import PipeAbstract

router = APIRouter(tags=["pipe-io"])


class PipeIORequest(MthdsPipeRequest):
    """The pipe I/O request: the crate routes' closure selector and pipe selector, plus the whole-method and echo opt-ins.

    The hosted catalog selector is replaced by `files` before the request reaches the runner, so this
    request has no field for it. It takes no `views` either, since the valid arm always carries all
    three artifacts.
    """

    # This docstring is published as the schema's description, so it must never name the hosted
    # selector field: the runner's OpenAPI declares no such field, not even in prose, and
    # `test_openapi_contract.py` pins the whole document free of that name.

    all_pipes: bool = Field(
        default=False,
        description=(
            "Describe every pipe the closure loads instead of the selected one. The artifact maps are then keyed by every "
            "pipe, and the route never refuses for want of an entry pipe: `pipe_ref` on the valid arm is the requested ref, "
            "else the method's own entry pipe, else `null`."
        ),
    )
    include_files: bool = Field(
        default=False,
        description=(
            "Echo the resolved closure's `.mthds` files on the valid arm, in the request's own `files[]` shape: the request's "
            "files for inline `files[]`, the fetched package's `.mthds` files under their package-relative paths for a "
            "`method_ref`. Absent from the response unless true."
        ),
    )


class PipeIOValidReport(BaseModel):
    """The 200 **valid** arm: the method's three I/O artifacts, with the selection and the runnability facts beside them.

    The three maps share one key set: the resolved `pipe_ref` alone by default, every pipe the
    closure loads under `all_pipes`. Each map is the standard's artifact under its neutral name, and
    for a closure `/validate` also accepts it equals `/validate`'s same-named field restricted to the
    same keys — both routes call the one builder, and both dump without dropping null members.
    `is_valid: true` means what it means on `/resolve`: the closure parsed, loaded and passed static
    validation. No dry run ran; that verdict stays `/validate`'s.
    """

    is_valid: Literal[True] = True
    pipe_ref: str | None = Field(
        ...,
        description=(
            "The qualified `domain.pipe_code` the selection resolved, read back off the resolved pipe and never echoed from "
            "the request. `null` only under `all_pipes` when no pipe was requested and the method declares no single entry pipe."
        ),
    )
    pipe_io_contracts: PipeIOContracts = Field(..., description="The standard's pipe I/O contracts, keyed by qualified `pipe_ref`.")
    input_form: InputForm = Field(..., description="The standard's input-form descriptors, keyed by qualified `pipe_ref`.")
    output_form: OutputForm = Field(..., description="The standard's output-form descriptors, keyed by qualified `pipe_ref`.")
    default_pipe_ref: str | None = Field(
        ...,
        description=(
            "The method's own entry pipe: the selection chain without the request's `pipe_ref` — the fetched package "
            "manifest's `main_pipe`, else the closure's single `main_pipe` declaration. A stated `null` when that chain finds "
            "none or several. Not `/validate`'s field of the same name, which is the run default."
        ),
    )
    pending_signatures: list[str] = Field(
        ...,
        description="The qualified refs of every pipe of the closure still declared as a signature, exactly as on `/validate`.",
    )
    is_runnable: bool = Field(..., description="`not pending_signatures`, exactly as on `/validate`. No dry run backs it.")
    # Never serialized from the model: the route attaches the echo itself, and only when asked, so the
    # field is absent — not empty, not null — otherwise. Declared here so the published schema names it.
    files: list[MthdsFileItem] = Field(
        default_factory=empty_list_factory_of(MthdsFileItem),
        description="The resolved closure's `.mthds` files, in the request's `files[]` shape. Present only with `include_files: true`.",
    )


# Discriminated 200 response union: a consumer pattern-matches the one mandatory `is_valid`
# field to learn the verdict — the same discipline as `POST /validate` and `POST /resolve`.
PipeIOResponse = Annotated[Union[PipeIOValidReport, CrateInvalidReport], Field(discriminator="is_valid")]


@router.post(
    "/pipe-io",
    response_model=PipeIOResponse,
    # On top of the composite router's shared 401/413/422/500: the `method_ref` fetch outcomes it
    # shares with `/resolve`. No structures 403: the route reads only a package's `.mthds` files.
    responses={404: PROBLEM_404_METHOD_PACKAGE, 501: PROBLEM_501_METHOD_REF},
    # NOT tagged `x-mthds-protocol`: it carries the standard's artifacts under their neutral names,
    # but the route is a Pipelex API extension, and the flag marks the standard's five operations alone.
)
async def pipe_io(request_data: PipeIORequest) -> JSONResponse:
    """Return a method's pipe I/O contracts, input form and output form, with no dry run (Pipelex API extension).

    The closure resolves through the static core `/resolve` rides, a pipe is selected the way the
    per-pipe routes select one, and the three artifacts are derived with `build_pipe_io_artifacts`,
    the builder `/validate` and every run call — so a call costs one load and one derivation where
    `/validate` dry-runs every pipe.

    Response contract (the `/validate` discipline):

    - **Valid verdict (200, `is_valid: true`):** the three artifact maps keyed by qualified `pipe_ref`,
      beside `pipe_ref`, `default_pipe_ref`, `pending_signatures`, `is_runnable`, and `files` when
      `include_files` is true.
    - **Invalid verdict (200, `is_valid: false`):** the closure could not be parsed, loaded, or
      statically validated — the crate verdict, carrying no artifact, no selection and no files.
    - **No verdict (non-2xx):** a malformed body and neither or both closure selectors are
      request-shape 422s (`ValidationError`); a selection refusal is an input 422 named for its failure,
      `EntryPipeNotFoundError` for an unknown `pipe_ref` or a single-pipe request whose chain finds no
      entry pipe, `EntryPipeAmbiguousError` for an ambiguous one or a chain that finds several; the
      `method_ref` fetch outcomes are those of `/resolve` (404, 422, 501);
      an artifact that cannot be derived (`PipeIOContractError`) is a 500. All RFC 7807
      `application/problem+json` via the global handlers.
    """
    try:
        resolved = resolve_requested_crate(request_data)
    except ValidateBundleError as validate_error:
        return invalid_crate_report_response(validate_error.to_error_report())
    try:
        default_pipe = select_default_pipe(resolved.crate, manifest_main_pipe=resolved.manifest_main_pipe)
        default_pipe_ref = default_pipe.ref if isinstance(default_pipe, RequestedPipe) else None
        pipe_ref: str | None
        described_pipes: list[PipeAbstract]
        if request_data.all_pipes:
            # A whole-method answer needs no selection: a requested ref is still resolved (and refused
            # when it names nothing), but a method with no single entry pipe is described all the same.
            if request_data.pipe_ref is not None:
                pipe_ref = resolve_requested_pipe(resolved.crate, pipe_ref=request_data.pipe_ref, manifest_main_pipe=resolved.manifest_main_pipe).ref
            else:
                pipe_ref = default_pipe_ref
            # The closure's own pipes in load order, the order `/validate`'s report walks.
            described_pipes = get_own_pipes()
        else:
            requested = resolve_requested_pipe(resolved.crate, pipe_ref=request_data.pipe_ref, manifest_main_pipe=resolved.manifest_main_pipe)
            pipe_ref = requested.ref
            described_pipes = [requested.pipe]
        # Raises `PipeIOContractError` when a pipe's input or output JSON Schema cannot be rendered;
        # it reaches the global handler as a no-verdict 500, exactly as on `/validate`.
        artifacts = build_pipe_io_artifacts(described_pipes)
        pending_signatures = build_pending_signatures(get_pipe_library().get_pipes_dict())
        report = PipeIOValidReport(
            pipe_ref=pipe_ref,
            pipe_io_contracts=artifacts.pipe_io_contracts,
            input_form=artifacts.input_form,
            output_form=artifacts.output_form,
            default_pipe_ref=default_pipe_ref,
            pending_signatures=pending_signatures,
            is_runnable=not pending_signatures,
        )
        # Dumped as `/validate` dumps its valid arm, never with `exclude_none`: that would strip the
        # contracts' `item_count: null` and break the byte equality with `/validate`'s maps.
        content: dict[str, Any] = report.model_dump(mode="json", serialize_as_any=True, by_alias=True, exclude={"files"})
        if request_data.include_files:
            # Each file is echoed in the request's own shape: a `source` the request omitted stays omitted.
            content["files"] = [item.model_dump(mode="json", exclude_none=True) for item in resolved.files]
        return JSONResponse(content=content)
    finally:
        teardown_current_library()
