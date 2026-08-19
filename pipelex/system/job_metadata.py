from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator

from pipelex.system.storage_scope import validate_storage_scope
from pipelex.system.telemetry.otel_context import OtelContext
from pipelex.system.trace_context import TraceContext


class SpecialPipelineId(StrEnum):
    """The reserved `pipeline_run_id` values, for runs that have no id of their own.

    Lives beside `JobMetadata` because `pipeline_run_id` is its field: this enum is that field's
    vocabulary, and `PipeOutput.pipeline_run_id` defaults to `UNTITLED` from here.
    """

    UNTITLED = "untitled"
    DRY_RUN_UNTITLED = "dry_run_untitled"


class JobCategory(StrEnum):
    MOCK_JOB = "mock_job"
    LLM_JOB = "llm_job"
    IMG_GEN_JOB = "img_gen_job"
    JINJA2_JOB = "jinja2_job"
    EXTRACT_JOB = "extract_job"
    SEARCH_JOB = "search_job"


class UnitJobId(StrEnum):
    LLM_GEN_TEXT = "llm_gen_text"
    LLM_GEN_OBJECT = "llm_gen_object"
    IMG_GEN_TEXT_TO_IMAGE = "img_gen_text_to_image"
    EXTRACT_PAGES = "extract_pages"
    SEARCH_SOURCED_ANSWER = "search_sourced_answer"
    SEARCH_STRUCTURED = "search_structured"

    @property
    def model_kind(self) -> str:
        match self:
            case UnitJobId.LLM_GEN_TEXT | UnitJobId.LLM_GEN_OBJECT:
                return "LLM"
            case UnitJobId.IMG_GEN_TEXT_TO_IMAGE:
                return "ImgGen"
            case UnitJobId.EXTRACT_PAGES:
                return "Extract"
            case UnitJobId.SEARCH_SOURCED_ANSWER | UnitJobId.SEARCH_STRUCTURED:
                return "Search"


class JobMetadata(BaseModel):
    user_id: str
    pipeline_run_id: str

    # Where every byte this run writes must land. Opaque to the runtime, which
    # composes `assets/`, `results/` and `payloads/` onto it and never parses it
    # — see `pipelex.system.storage_scope` for why the host's own concepts
    # (tenant, organization, method) deliberately do not cross this boundary.
    #
    # REQUIRED, with no default. It used to be derived from `user_id`, which
    # tied where the bytes live to who uploaded them — fine until two people
    # share the work, at which point the second one cannot read the first one's
    # files. A default here would let that coupling grow back silently, so a
    # caller with nothing to store must say so explicitly with
    # `DRY_RUN_STORAGE_SCOPE`.
    storage_scope: str

    pipe_code: str | None = None

    # Per-process Pipelex session id (``Config.session_id``) captured at the
    # submitter dispatch boundary. Inheriting it through ``JobMetadata`` lets
    # the Temporal observability helpers stay pure functions of the workflow
    # input — replay on a different worker no longer changes the value and
    # so cannot cause a non-determinism mismatch on child-workflow starts.
    session_id: str | None = None

    # The API-inbound ``X-Request-ID`` (set by the dispatcher when an external
    # HTTP request enters Pipelex). Rides on ``JobMetadata`` so it crosses the
    # Temporal serialization boundary — every activity / workflow can correlate
    # logs and the resulting ``ErrorReport`` back to the originating request.
    # Distinct from :class:`pipelex.cogt.inference.error_classification.ProviderErrorMetadata.request_id`,
    # which is the *provider*-side request id (OpenAI ``x-request-id`` etc.) —
    # both can appear together when the API surfaces a provider failure.
    # Constrained at the wire-format boundary (printable ASCII only, max 128
    # chars) so an unsanitized upstream value cannot inject newlines or control
    # characters into the log lines or ``ErrorReport`` envelopes that quote it.
    request_id: str | None = Field(default=None, max_length=128, pattern=r"^[\x20-\x7E]+$")

    # Business ID for the current pipe execution (16-char hex string).
    # Always set during pipe runs for tracking purposes.
    pipe_run_id: str | None = None

    # OTel context with precomputed trace/span IDs. None when telemetry is disabled.
    otel_context: OtelContext | None = None

    # Per-execution trace context carrying the shared node tree for both the graph
    # (node/edge) and usage (cost) event streams. None when neither stream is enabled.
    trace_context: TraceContext | None = None

    content_generation_job_id: str | None = None
    unit_job_id: UnitJobId | None = None
    job_category: JobCategory | None = None

    started_at: datetime | None = Field(default_factory=datetime.now)
    completed_at: datetime | None = None

    @field_validator("storage_scope")
    @classmethod
    def _validate_storage_scope(cls, value: str) -> str:
        """Refuse a scope that would escape its namespace, at construction.

        On the TYPE rather than at the call sites: the value becomes a storage
        key prefix, so a `..` or a leading slash in it is a traversal into
        another tenant's data. Validating here means every key the runtime
        derives is safe by construction. `model_copy` does NOT re-run
        validators, which is fine — `copy_with_update` only ever carries an
        already-validated scope forward, and nothing constructs a scope from
        request data after this point.
        """
        return validate_storage_scope(value=value)

    @property
    def duration(self) -> float | None:
        if self.started_at is not None and self.completed_at is not None:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    def copy_with_update(
        self,
        *,
        otel_context: OtelContext | None,
        trace_context: TraceContext | None = None,
        **updates: Any,
    ) -> "JobMetadata":
        """Create a copy of this metadata with updates applied.

        Args:
            otel_context: OTel context to set on the copy. Always set explicitly
                because it's computed fresh per pipe run and should replace the parent's context
                (even when None, e.g. in dry mode or when tracing is disabled).
            trace_context: Per-execution trace context (graph + usage streams) to set on
                the copy. If None, inherits from the current context (unlike otel_context).
            **updates: Fields to update on the copy.
        """
        # trace_context defaults to current value if not provided (inheritance)
        effective_trace_context = trace_context if trace_context is not None else self.trace_context
        return self.model_copy(
            deep=True,
            update={
                "otel_context": otel_context,
                "trace_context": effective_trace_context,
                **updates,
            },
        )
