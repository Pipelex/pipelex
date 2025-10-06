from datetime import datetime

from pydantic import BaseModel, Field

from pipelex.pipeline.pipeline_models import SpecialPipelineId
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


class JobMetadata(BaseModel):
    job_name: str | None = None
    pipeline_run_id: str = Field(default=SpecialPipelineId.UNTITLED)
    pipe_job_ids: list[str] | None = None

    content_generation_job_id: str | None = None
    unit_job_id: str | None = None
    job_category: JobCategory | None = None

    started_at: datetime | None = Field(default_factory=lambda: datetime.now())
    completed_at: datetime | None = None

    @property
    def duration(self) -> float | None:
        if self.started_at is not None and self.completed_at is not None:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    def update(self, updated_metadata: "JobMetadata"):
        if updated_metadata.job_category:
            self.job_category = updated_metadata.job_category
        if updated_metadata.pipe_job_ids:
            self.pipe_job_ids = self.pipe_job_ids or []
            self.pipe_job_ids.extend(updated_metadata.pipe_job_ids)
        if updated_metadata.content_generation_job_id:
            self.content_generation_job_id = updated_metadata.content_generation_job_id
        if updated_metadata.unit_job_id:
            self.unit_job_id = updated_metadata.unit_job_id
        if updated_metadata.started_at:
            self.started_at = updated_metadata.started_at
        if updated_metadata.completed_at:
            self.completed_at = updated_metadata.completed_at

    def copy_with_update(self, updated_metadata: "JobMetadata") -> "JobMetadata":
        new_metadata = self.model_copy()
        new_metadata.update(updated_metadata=updated_metadata)
        return new_metadata
