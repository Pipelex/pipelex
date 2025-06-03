from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from pipelex.pipeline.pipeline_models import SpecialPipelineId
from pipelex.types import StrEnum


class JobCategory(StrEnum):
    MOCK_JOB = "mock_job"
    LLM_JOB = "llm_job"
    IMGG_JOB = "imgg_job"
    PROMPTING_JOB = "prompting_job"
    JINJA2_JOB = "jinja2_job"
    OCR_JOB = "ocr_job"


class UnitJobId(StrEnum):
    LLM_GEN_TEXT = "llm_gen_text"
    LLM_GEN_OBJECT = "llm_gen_object"
    IMGG_TEXT_TO_IMAGE = "imgg_text_to_image"
    OCR_EXTRACT_PAGES = "ocr_extract_pages"


class JobMetadata(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    pipeline_run_id: str = Field(default=SpecialPipelineId.UNTITLED)
    top_job_id: Optional[str] = None
    pipe_job_ids: Optional[List[str]] = None
    content_generation_job_id: Optional[str] = None
    job_category: Optional[JobCategory] = None
    unit_job_id: Optional[str] = None

    started_at: Optional[datetime] = Field(default_factory=lambda: datetime.now())
    completed_at: Optional[datetime] = None

    @property
    def duration(self) -> Optional[float]:
        if self.started_at is not None and self.completed_at is not None:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    def update(self, updated_metadata: "JobMetadata"):
        if updated_metadata.job_category:
            self.job_category = updated_metadata.job_category
        if updated_metadata.top_job_id:
            self.top_job_id = updated_metadata.top_job_id
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
