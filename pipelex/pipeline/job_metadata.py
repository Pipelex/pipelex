from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from pipelex.graph.graph_context import GraphContext
from pipelex.system.telemetry.otel_context import OtelContext
from pipelex.types import StrEnum


class JobCategory(StrEnum):
    MOCK_JOB = "mock_job"
    LLM_JOB = "llm_job"
    IMG_GEN_JOB = "img_gen_job"
    JINJA2_JOB = "jinja2_job"
    EXTRACT_JOB = "extract_job"


class UnitJobId(StrEnum):
    LLM_GEN_TEXT = "llm_gen_text"
    LLM_GEN_OBJECT = "llm_gen_object"
    IMG_GEN_TEXT_TO_IMAGE = "img_gen_text_to_image"
    EXTRACT_PAGES = "extract_pages"

    @property
    def model_kind(self) -> str:
        match self:
            case UnitJobId.LLM_GEN_TEXT:
                return "LLM"
            case UnitJobId.LLM_GEN_OBJECT:
                return "LLM"
            case UnitJobId.IMG_GEN_TEXT_TO_IMAGE:
                return "ImgGen"
            case UnitJobId.EXTRACT_PAGES:
                return "Extract"


class JobMetadata(BaseModel):
    user_id: str
    pipeline_run_id: str
    pipe_code: str | None = None

    # Business ID for the current pipe execution (16-char hex string).
    # Always set during pipe runs for tracking purposes.
    pipe_run_id: str | None = None

    # OTel context with precomputed trace/span IDs. None when telemetry is disabled.
    otel_context: OtelContext | None = None

    # GraphSpec tracing context. None when graph tracing is disabled.
    graph_context: GraphContext | None = None

    content_generation_job_id: str | None = None
    unit_job_id: UnitJobId | None = None
    job_category: JobCategory | None = None

    started_at: datetime | None = Field(default_factory=datetime.now)
    completed_at: datetime | None = None

    @property
    def duration(self) -> float | None:
        if self.started_at is not None and self.completed_at is not None:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    def copy_with_update(
        self,
        otel_context: OtelContext | None,
        graph_context: GraphContext | None = None,
        **updates: Any,
    ) -> "JobMetadata":
        """Create a copy of this metadata with updates applied.

        Args:
            otel_context: OTel context to set on the copy. Always set explicitly
                because it's computed fresh per pipe run and should replace the parent's context
                (even when None, e.g. in dry mode or when tracing is disabled).
            graph_context: GraphSpec tracing context to set on the copy. If None,
                inherits from the current context (unlike otel_context).
            **updates: Fields to update on the copy.
        """
        # graph_context defaults to current value if not provided (inheritance)
        effective_graph_context = graph_context if graph_context is not None else self.graph_context
        return self.model_copy(
            deep=True,
            update={
                "otel_context": otel_context,
                "graph_context": effective_graph_context,
                **updates,
            },
        )
