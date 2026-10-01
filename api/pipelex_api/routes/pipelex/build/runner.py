from typing import Annotated, Literal, Union

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from mthds.package.manifest.schema import MTHDS_STANDARD_VERSION
from pipelex.base_exceptions import PipelexUnexpectedError
from pipelex.builder.runner_code import generate_runner_code
from pipelex.codegen.emission import build_stamped_projection
from pipelex.codegen.emitters.naming import runtime_to_emitted_class_names
from pipelex.codegen.emitters.target import CodegenKind, CodegenTarget
from pipelex.codegen.emitters.types_emitter import emit_types
from pipelex.codegen.lock import CODEGEN_LOCK_FILENAME
from pipelex.codegen.resolved_concepts import resolve_concepts_from_crate
from pipelex.core.pipes.variable_multiplicity import parse_concept_with_multiplicity
from pipelex.interpreter_hub import get_current_library_id_or_none, get_library_manager
from pipelex.libraries.crate_normalization import normalize_crate
from pipelex.libraries.pipe.exceptions import EntryPipeNotFoundError, PipeNotFoundError
from pipelex.mthds_parsing.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.pipeline.bundle_validator import DryRunOutput, DryRunStatus
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.validate_bundle import validate_bundle
from pipelex.system.caller_identity import CallerIdentity
from pipelex.tools.misc.package_utils import get_package_version
from pipelex.tools.typing.pydantic_utils import empty_list_factory_of
from pydantic import BaseModel, Field

from pipelex_api.errors import raise_validation_error
from pipelex_api.openapi_responses import PROBLEM_404_METHOD_PACKAGE, PROBLEM_501_METHOD_REF
from pipelex_api.routes.pipelex.crate_ops import (
    CrateInvalidReport,
    GeneratedArtifact,
    invalid_crate_report_response,
    resolve_requested_pipe,
    selected_files,
    teardown_current_library,
)
from pipelex_api.routes.pipelex.pipeline import get_request_user_id
from pipelex_api.schemas.models import ALLOW_SIGNATURES_DESCRIPTION, CallerAnalyticsGroupsMixin, MthdsPipeRequest

router = APIRouter(tags=["build"])


class BuildRunnerRequest(MthdsPipeRequest, CallerAnalyticsGroupsMixin):
    """The runner-script request: the shared closure + pipe selectors, plus the sweep's `allow_signatures`.

    Alone among the `/build/*` projections this route keeps `allow_signatures`, because alone among
    them it still runs the dry-run sweep — the flag only ever parameterized that sweep.
    """

    allow_signatures: bool = Field(default=False, description=ALLOW_SIGNATURES_DESCRIPTION)


class RunnerStructures(BaseModel):
    """The typed-structures projection the runner script imports from (`from structures.structures import ...`).

    The same stamped `python-structures` artifacts + `codegen.lock` a local `pipelex build runner`
    scaffolds into `<output>/structures/` — write `artifacts` and the lock under `directory` and
    the returned `python_code` runs against them, with the offline `codegen check` passing there.
    """

    directory: str = Field(default="structures", description="Directory (relative to the runner script) to write the artifacts and lock into.")
    artifacts: list[GeneratedArtifact] = Field(
        default_factory=empty_list_factory_of(GeneratedArtifact),
        description="The stamped generated files (paths relative to `directory`).",
    )
    lock: str = Field(..., description="The lock content (TOML) tracking the artifact set — write verbatim inside `directory`.")
    lock_filename: str = Field(default=CODEGEN_LOCK_FILENAME, description="Filename the lock content must be written as.")


class BuildRunnerValidReport(BaseModel):
    """The 200 **valid** arm: the runner script plus the structures projection it imports from."""

    is_valid: Literal[True] = True
    pipe_ref: str = Field(..., description="The qualified pipe the runner was generated for — the resolved selector.")
    requested_pipe_ref: str | None = Field(
        default=None,
        description=(
            "The `pipe_ref` as submitted. Absent when it was omitted and defaulted — to the fetched package manifest's "
            "`main_pipe` on a `method_ref` request, else to the closure's declared `main_pipe`."
        ),
    )
    python_code: str = Field(..., description="Generated Python script for running the pipeline, imports spelled with the emitted class names.")
    structures: RunnerStructures = Field(..., description="The typed-structures projection the script imports from.")
    message: str = Field(default="Runner code generated successfully", description="Status message")


# Discriminated 200 response union: the `/validate` discipline — the verdict rides `is_valid`,
# never the HTTP status (breaking change from the previous `success`-bool body + 422-on-invalid).
BuildRunnerResponse = Annotated[Union[BuildRunnerValidReport, CrateInvalidReport], Field(discriminator="is_valid")]


def _reject_if_requested_pipe_skipped(sweep_result: dict[str, DryRunOutput], *, pipe_ref: str) -> None:
    """Reject when the *requested* pipe was SKIPPED (its cross-package dependency is unresolved).

    `validate_pipes` records a pipe SKIPPED — rather than failing the whole sweep — when a controller
    references a sub-pipe in a package not included in the request (the cross-package tolerance shared
    with `/validate`). For a code-generation endpoint that is a footgun: `generate_runner_code` reads
    only the pipe's own inputs/output and never resolves sub-pipes, so it would happily emit runner
    code for a pipeline that cannot actually run. A SKIPPED requested pipe is a no-verdict condition
    (its dependency closure is absent from the request, so nothing could be diagnosed) → request-shape
    422; unrelated SKIPPED pipes elsewhere in the bundle stay tolerated.
    """
    for output in sweep_result.values():
        if pipe_ref != output.pipe_ref:
            continue
        match output.status:
            case DryRunStatus.SKIPPED:
                detail = output.error_message or "its dependencies could not be resolved"
                raise_validation_error(f"Cannot generate runner code for pipe '{pipe_ref}': {detail}")
            case DryRunStatus.SUCCESS | DryRunStatus.FAILURE:
                return


def _output_is_list(blueprints: list[PipelexBundleBlueprint], *, pipe_ref: str) -> bool:
    """Whether the requested pipe's declared output carries a list multiplicity marker (mirrors the CLI).

    Matched on the **qualified** ref. A blueprint's `pipe` map is keyed by bare code, so scanning by
    bare code alone would return the first blueprint declaring that code — which in a multi-domain
    closure can be a *different* pipe that merely shares the name, and whose multiplicity may differ.
    The runner would then be generated with the wrong output handling. Compare the owning domain too.
    """
    domain_code, _, pipe_code = pipe_ref.rpartition(".")
    for blueprint in blueprints:
        if blueprint.domain != domain_code or not blueprint.pipe or pipe_code not in blueprint.pipe:
            continue
        output_parse = parse_concept_with_multiplicity(blueprint.pipe[pipe_code].output)
        return output_parse.multiplicity is not None
    return False


@router.post(
    "/build/runner",
    response_model=BuildRunnerResponse,
    # On top of the composite router's shared 401/413/422/500: the `method_ref` closure selector the
    # envelope accepts but no server-side method registry resolves yet (shared with /resolve, /codegen).
    responses={404: PROBLEM_404_METHOD_PACKAGE, 501: PROBLEM_501_METHOD_REF},
)
async def build_runner(request: Request, request_data: BuildRunnerRequest) -> JSONResponse:
    """Generate a Python runner script for a pipe, riding the codegen types projection.

    The one `/build/*` projection that is **not** static: a runner script is a promise the pipe can
    actually run, so this route keeps the dry-run sweep its siblings dropped (and with it
    `allow_signatures`, which only ever parameterized that sweep). `validate_bundle` opens a single
    library, loads the closure, sweeps, and on success leaves the library loaded + current; on failure
    it tears it down itself. On the success path the crate is read from that library, the
    `python-structures` projection is emitted and stamped, and the runner script is generated with the
    **emitted** class names — the same flow as a local `pipelex build runner`.

    The sweep is scoped to the requested pipe, so unrelated broken siblings do not block a good pipe.
    When `pipe_ref` is omitted the scope is not settled before the closure loads, so the whole closure
    is swept and the pipe then defaults the way a run by address does — to the fetched package
    manifest's `main_pipe` on a `method_ref` request, else to the closure's own declared `main_pipe` —
    a stricter verdict, and the honest one for a caller who did not say which pipe they meant.

    Response contract (the `/validate` discipline): an invalid closure — including a failed dry-run of
    the requested pipe — is a produced verdict: a **200** `is_valid: false` with the structured
    `validation_errors[]`. Non-2xx is reserved for no-verdict conditions: a selection refusal (an
    unknown pipe ref, an omitted `pipe_ref` that nothing defaults — no fetched-manifest `main_pipe`,
    and a closure declaring no, or several, `main_pipe`), an input 422 whose `error_type` is
    `EntryPipeNotFoundError` or `EntryPipeAmbiguousError`; a request-shape 422 for a requested pipe
    whose cross-package dependencies are absent from the request; a 501 for a registry-form `method_ref`, auth, server
    fault — RFC 7807 via the global handlers.
    """
    library_manager = get_library_manager()
    selection = selected_files(request_data)

    try:
        # If this raises, validate_bundle has already torn down its own library — nothing to clean up here.
        validate_result = await validate_bundle(
            mthds_contents=[item.content for item in selection.files],
            mthds_sources=[item.source for item in selection.files],
            allow_signatures=request_data.allow_signatures,
            dry_run_pipe_codes=[request_data.pipe_ref] if request_data.pipe_ref else None,
            # The sweep is done for the caller, so its dry runs and `pipe_dry_run` event name them.
            caller_identity=CallerIdentity.make_from_host(user_id=get_request_user_id(request), extras=request_data.analytics_groups),
        )
    except ValidateBundleError as validate_error:
        return invalid_crate_report_response(validate_error.to_error_report())
    except PipeNotFoundError as exc:
        # The engine deliberately lets this one through untranslated (see `translate_to_validate_bundle_error`)
        # so the caller can own it: a pipe ref naming nothing in the closure is an input 422, not an
        # invalid-closure verdict — nothing about the closure is wrong. It is re-raised as the entry-lookup
        # class the slice miss already is, so its `error_type` matches `resolve_requested_pipe`'s refusals.
        msg = f"Pipe '{request_data.pipe_ref}' not found in the submitted closure: {exc}"
        raise EntryPipeNotFoundError(msg) from exc

    # Success: validate_bundle left its library loaded + current. Build everything from it, then own its teardown.
    library_id = get_current_library_id_or_none()
    try:
        crate = library_manager.get_crate(library_id) if library_id else None
        if crate is None:
            # Unreachable after a successful in-memory validate (the blueprints were accumulated),
            # so a None crate is an internal invariant break — a server fault (5xx), never a
            # caller-facing verdict (mirrors resolve_crate_from_contents's identical guard).
            msg = "library crate unavailable after a successful bundle load"
            raise PipelexUnexpectedError(msg)
        normalized_crate = normalize_crate(crate, mthds_version=MTHDS_STANDARD_VERSION)
        requested_pipe = resolve_requested_pipe(
            normalized_crate,
            pipe_ref=request_data.pipe_ref,
            manifest_main_pipe=selection.manifest_main_pipe,
        )

        # The sweep tolerates a cross-package unresolved dependency by recording the pipe SKIPPED
        # instead of failing. Don't hand back runner code for the *requested* pipe in that state.
        _reject_if_requested_pipe_skipped(validate_result.dry_run_result, pipe_ref=requested_pipe.ref)

        emitted = emit_types(normalized_crate, target=CodegenTarget.PYTHON_STRUCTURES)
        projection = build_stamped_projection(
            emitted,
            crate_fingerprint=normalized_crate.fingerprint,
            engine_version=get_package_version(),
            kind=CodegenKind.TYPES,
            target=CodegenTarget.PYTHON_STRUCTURES,
        )
        class_name_overrides = runtime_to_emitted_class_names(resolve_concepts_from_crate(normalized_crate))

        python_code = generate_runner_code(
            pipe=requested_pipe.pipe,
            output_multiplicity=_output_is_list(validate_result.blueprints, pipe_ref=requested_pipe.ref),
            class_name_overrides=class_name_overrides,
        )

        report = BuildRunnerValidReport(
            pipe_ref=requested_pipe.ref,
            requested_pipe_ref=request_data.pipe_ref,
            python_code=python_code,
            structures=RunnerStructures(
                artifacts=[GeneratedArtifact(path=stamped.filename, content=stamped.content) for stamped in projection.files],
                lock=projection.lock_content,
            ),
        )
        return JSONResponse(content=report.model_dump(mode="json", by_alias=True, exclude_none=True))
    finally:
        teardown_current_library()
