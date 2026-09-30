from enum import StrEnum
from typing import Annotated, Literal, Self, Union

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pipelex.codegen.emission import build_stamped_projection
from pipelex.codegen.emitters.target import CodegenKind, CodegenTarget
from pipelex.codegen.emitters.types_emitter import emit_types
from pipelex.codegen.lock import CODEGEN_LOCK_FILENAME
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.tools.misc.package_utils import get_package_version
from pipelex.tools.typing.pydantic_utils import empty_list_factory_of
from pydantic import BaseModel, Field, model_validator

from api.openapi_responses import PROBLEM_404_METHOD_PACKAGE, PROBLEM_501_METHOD_REF
from api.routes.pipelex.crate_ops import (
    CrateInvalidReport,
    GeneratedArtifact,
    invalid_crate_report_response,
    resolve_requested_crate,
    teardown_current_library,
)
from api.schemas.models import MthdsFilesRequest

router = APIRouter(tags=["codegen"])


class CodegenRouteKind(StrEnum):
    """The projection kinds this route serves — the `kind` axis of the codegen request.

    Membership follows the **trust chain**: a kind is served here exactly when its artifacts are
    stamped and locked, so a client can write them verbatim and pass the offline `codegen check` —
    the promise this route's valid arm makes by carrying a `lock`. Input templates are user-editable
    scaffolds, never stamped or locked, so they cannot make that promise; they ride
    `POST /build/inputs` instead and `inputs` is therefore not a kind here. Future per-pipe kinds
    (`docs`, `tools`, `tests`) do emit tracked artifacts, so they join this enum and select their
    pipe via `pipe_ref`. An unknown kind is a request-shape 422 listing the served set.
    """

    TYPES = "types"

    @property
    def engine_kind(self) -> CodegenKind:
        """The engine-side `CodegenKind` this route kind projects."""
        match self:
            case CodegenRouteKind.TYPES:
                return CodegenKind.TYPES


class CodegenRequest(MthdsFilesRequest):
    """The codegen request: the shared closure selector plus the two explicit projection axes."""

    kind: CodegenRouteKind = Field(..., description="What to project. `types` projects the crate's concept set into typed models.")
    target: CodegenTarget = Field(
        ...,
        description=(
            "For whom: `ts-zod` (zod schemas + inferred types), `python-pydantic` (self-contained BaseModels), or "
            "`python-structures` (runtime StructuredContent classes, for a Pipelex host)."
        ),
    )
    pipe_ref: str | None = Field(
        default=None,
        max_length=512,
        description="Pipe selector for per-pipe projection kinds. Not accepted for `types` (a concept-set-wide projection).",
    )

    @model_validator(mode="after")
    def _pipe_ref_only_for_per_pipe_kinds(self) -> Self:
        # `types` is concept-set-wide: silently ignoring a pipe_ref would mislead the caller into
        # believing the artifacts were narrowed to one pipe. Request-shape error → 422. A future
        # per-pipe kind adds its arm here and accepts the selector. The `return self` is
        # unconditional so a non-raising future arm can never make pydantic take None as the model.
        match self.kind:
            case CodegenRouteKind.TYPES:
                if self.pipe_ref is not None:
                    msg = "pipe_ref is not accepted for kind='types' (a concept-set-wide projection)"
                    raise ValueError(msg)
        return self


class CodegenValidReport(BaseModel):
    """The 200 **valid** arm: the stamped artifact set plus its lock.

    A client that writes each artifact and the lock verbatim reproduces a local
    `pipelex codegen types` run byte-for-byte — the same stamps, the same `codegen.lock` — so the
    offline `codegen check` passes on the written tree exactly as it would locally.
    """

    is_valid: Literal[True] = True
    kind: CodegenRouteKind = Field(..., description="The projected kind (echo of the request).")
    target: CodegenTarget = Field(..., description="The projection target (echo of the request).")
    crate_fingerprint: str = Field(..., description="Fingerprint of the normalized crate the artifacts were generated from.")
    engine_version: str = Field(..., description="The pipelex engine version that generated the artifacts.")
    artifacts: list[GeneratedArtifact] = Field(
        default_factory=empty_list_factory_of(GeneratedArtifact),
        description="The stamped generated files.",
    )
    lock: str = Field(
        ..., description=f"The `{CODEGEN_LOCK_FILENAME}` content (TOML) tracking the artifact set — write verbatim beside the artifacts."
    )
    lock_filename: str = Field(default=CODEGEN_LOCK_FILENAME, description="Filename the lock content must be written as.")
    message: str = Field(default="Codegen artifacts generated successfully", description="Status message")


# Discriminated 200 response union: the `/validate` discipline (see `POST /resolve`).
CodegenResponse = Annotated[Union[CodegenValidReport, CrateInvalidReport], Field(discriminator="is_valid")]


@router.post(
    "/codegen",
    response_model=CodegenResponse,
    # On top of the composite router's shared 401/413/422/500: the `method_ref` closure selector
    # the envelope accepts but no server-side method registry resolves yet (shared with `/resolve`).
    responses={404: PROBLEM_404_METHOD_PACKAGE, 501: PROBLEM_501_METHOD_REF},
    # NOT tagged `x-mthds-protocol` — a Pipelex API extension, like `/resolve`. The MTHDS standard
    # specifies the crate this reads (the Library Crate Format); it specifies no type projection, so
    # every `target` here — `ts-zod` and `python-pydantic` no less than `python-structures` — is ours.
)
async def codegen_mthds(request_data: CodegenRequest) -> JSONResponse:
    """Generate typed artifacts from a library closure (Pipelex API extension).

    Resolves the closure to its normalized crate (exactly like `POST /resolve`), then projects it
    through the requested `kind`/`target` axes and returns the **stamped** artifact set plus its
    `codegen.lock` — everything a client needs to materialize a byte-identical local projection
    and run the offline drift check. There is deliberately **no** server-side check route: the
    check is offline by design.

    Response contract (the `/validate` discipline):

    - **Valid verdict (200, `is_valid: true`):** the artifacts + lock on the valid arm.
    - **Invalid verdict (200, `is_valid: false`):** the library could not be parsed, loaded, or
      validated — `validation_errors[]` from pipelex's one shared builder; no artifacts exist.
    - **No verdict (non-2xx):** an unknown projection `kind`/`target`, a `pipe_ref` on a
      concept-set-wide kind, or a malformed closure selector is a request-shape 422 problem+json;
      `method_ref` is a 501 until server-side method registry resolution exists; auth is 401/403;
      server fault is 5xx.
    """
    try:
        # `types` is concept-set-wide: no pipe is selected, so the manifest's `main_pipe` beside the crate is unused.
        # A future per-pipe kind takes it from the `ResolvedClosure` and hands it to `resolve_requested_pipe`.
        crate = resolve_requested_crate(request_data).crate
    except ValidateBundleError as validate_error:
        return invalid_crate_report_response(validate_error.to_error_report())
    try:
        emitted = emit_types(crate, target=request_data.target)
        projection = build_stamped_projection(
            emitted,
            crate_fingerprint=crate.fingerprint,
            engine_version=get_package_version(),
            kind=request_data.kind.engine_kind,
            target=request_data.target,
        )
        report = CodegenValidReport(
            kind=request_data.kind,
            target=request_data.target,
            crate_fingerprint=crate.fingerprint,
            engine_version=get_package_version(),
            artifacts=[GeneratedArtifact(path=stamped.filename, content=stamped.content) for stamped in projection.files],
            lock=projection.lock_content,
        )
        return JSONResponse(content=report.model_dump(mode="json", by_alias=True))
    finally:
        teardown_current_library()
