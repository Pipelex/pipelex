from typing import TYPE_CHECKING, Annotated, Any, Literal, Union

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pipelex.interpreter_hub import get_own_pipes, get_pipe_library
from pipelex.pipeline.build_pipe_io_artifacts import build_pipe_io_artifacts
from pipelex.pipeline.exceptions import MethodEntryError, ValidateBundleError
from pipelex.pipeline.input_form import InputForm, OutputForm
from pipelex.pipeline.pipe_io_contracts import PipeIOContracts
from pipelex.pipeline.validate_bundle import build_pending_signatures
from pydantic import BaseModel, Field

from pipelex_api.json_body import JsonBodyRoute
from pipelex_api.openapi_responses import PROBLEM_403_READ_SCOPE, PROBLEM_404_METHOD_PACKAGE, PROBLEM_500_HELD_BLOBS, PROBLEM_501_RUN_POLICY
from pipelex_api.problem_view import problem_view_of
from pipelex_api.routes.pipelex.crate_ops import (
    CrateInvalidReport,
    RequestedPipe,
    ResolvedMethod,
    invalid_crate_report_response,
    project_resolved_method,
    resolve_requested_pipe,
    select_default_pipe,
)
from pipelex_api.schemas.models import MethodTreePipeRequest

if TYPE_CHECKING:
    from pipelex.pipe_machinery.pipe_abstract import PipeAbstract

router = APIRouter(tags=["pipe-io"], route_class=JsonBodyRoute)


class PipeIORequest(MethodTreePipeRequest):
    """The pipe I/O request: the crate routes' method selector and pipe selector, plus the whole-method and echo opt-ins.

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
            "Echo the method's `.mthds` bundles on the valid arm, as a map of file entries in the request's own `files` shape, "
            "each bundle's tree path to its text: the bundles of the tree sent in `files`, whatever entry carried them, or "
            "those of the fetched package's tree for a `method_ref`. Its other files and its dependencies are not echoed. "
            "Absent from the response unless true."
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
    files: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "The method's `.mthds` bundles, each tree path to its text, a map of file entries as the request's `files` is. "
            "Present only with `include_files: true`."
        ),
    )


# Discriminated 200 response union: a consumer pattern-matches the one mandatory `is_valid`
# field to learn the verdict — the same discipline as `POST /validate` and `POST /resolve`.
PipeIOResponse = Annotated[Union[PipeIOValidReport, CrateInvalidReport], Field(discriminator="is_valid")]


@router.post(
    "/pipe-io",
    response_model=PipeIOResponse,
    # On top of the composite router's shared 401/413/422/500: the refusals of the method's tree it shares with
    # `/resolve` and `/codegen`, a `read_scope` outside the caller's own, the `method_ref` package-not-found 404, a
    # damaged blob a hash entry names, and the Python policy's 501.
    responses={403: PROBLEM_403_READ_SCOPE, 404: PROBLEM_404_METHOD_PACKAGE, 500: PROBLEM_500_HELD_BLOBS, 501: PROBLEM_501_RUN_POLICY},
    # NOT tagged `x-mthds-protocol`: it carries the standard's artifacts under their neutral names,
    # but the route is a Pipelex API extension, and the flag marks the standard's five operations alone.
)
async def pipe_io(request: Request, request_data: PipeIORequest) -> JSONResponse:
    """Return a method's pipe I/O contracts, input form and output form, with no dry run (Pipelex API extension).

    The method is read as `/validate` reads a method tree and resolves through the static core
    `/resolve` rides, a pipe is selected the way the per-pipe routes select one, and the three
    artifacts are derived with `build_pipe_io_artifacts`, the builder `/validate` and every run call —
    so a call costs one load and one derivation where `/validate` dry-runs every pipe.

    Response contract (the `/validate` discipline):

    - **Valid verdict (200, `is_valid: true`):** the three artifact maps keyed by qualified `pipe_ref`,
      beside `pipe_ref`, `default_pipe_ref`, `pending_signatures`, `is_runnable`, and `files` when
      `include_files` is true.
    - **Invalid verdict (200, `is_valid: false`):** the closure could not be parsed, loaded, or
      statically validated — the crate verdict, carrying no artifact, no selection and no files.
    - **No verdict (non-2xx):** a malformed body and neither or both method selectors are
      request-shape 422s (`request.invalid`); a `files` map that is not a method tree is a 422
      `method.package_invalid`, and hash entries this runner does not hold a 422
      `request.blobs_missing`, as on `/validate`; custom Python on a deployment that is not
      sandbox-hosted is a 501 `pipelex.deployment.custom_code_requires_sandbox`, and a Python
      structure class a 422 `pipelex.deployment.python_structures_refused`; a selection refusal is an
      input 422 named for its failure, `request.pipe_not_found` for an unknown `pipe_ref` or a
      single-pipe request whose chain finds no entry pipe, `request.pipe_ambiguous` for an ambiguous
      one or a chain that finds several; the `method_ref` fetch outcomes are those of `/resolve` (404,
      422); an artifact that cannot be derived (`PipeIOContractError`) is a 500. All
      `application/problem+json` documents with a registry `code`, via the global handlers.
    """
    outcome = await project_resolved_method(
        request=request,
        request_data=request_data,
        project=lambda resolution: _pipe_io_response(resolution=resolution, request_data=request_data),
    )
    if isinstance(outcome, ValidateBundleError):
        return invalid_crate_report_response(outcome, view=problem_view_of(request))
    return outcome


def _manifest_main_pipe_if_readable(*, resolution: ResolvedMethod) -> tuple[str | None, bool]:
    """The manifest's `main_pipe`, and whether the manifest could be read, for a request that named its pipe.

    Such a request selects its pipe without the manifest, so a `METHODS.toml` that cannot be read refuses nothing: it
    only leaves the method's own default unstated.
    """
    try:
        return resolution.manifest_main_pipe, True
    except MethodEntryError:
        return None, False


def _pipe_io_response(*, resolution: ResolvedMethod, request_data: PipeIORequest) -> JSONResponse:
    """The valid arm for a resolved method, built in the worker thread that holds its library loaded and current."""
    # The manifest is read strictly only when the selection depends on it, which is when the request names no pipe.
    manifest_readable = True
    if request_data.pipe_ref is None:
        manifest_main_pipe = resolution.manifest_main_pipe
    else:
        manifest_main_pipe, manifest_readable = _manifest_main_pipe_if_readable(resolution=resolution)
    default_pipe_ref: str | None = None
    if manifest_readable:
        default_pipe = select_default_pipe(resolution.crate, manifest_main_pipe=manifest_main_pipe)
        default_pipe_ref = default_pipe.ref if isinstance(default_pipe, RequestedPipe) else None
    pipe_ref: str | None
    described_pipes: list[PipeAbstract]
    if request_data.all_pipes:
        # A whole-method answer needs no selection: a requested ref is still resolved (and refused
        # when it names nothing), but a method with no single entry pipe is described all the same.
        if request_data.pipe_ref is not None:
            pipe_ref = resolve_requested_pipe(resolution.crate, pipe_ref=request_data.pipe_ref, manifest_main_pipe=None).ref
        else:
            pipe_ref = default_pipe_ref
        # The closure's own pipes in load order, the order `/validate`'s report walks.
        described_pipes = get_own_pipes()
    else:
        requested = resolve_requested_pipe(resolution.crate, pipe_ref=request_data.pipe_ref, manifest_main_pipe=manifest_main_pipe)
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
        # Decoded strictly: every bundle loaded, so every bundle is UTF-8 text.
        content["files"] = resolution.request_method.tree.bundle_texts
    return JSONResponse(content=content)
