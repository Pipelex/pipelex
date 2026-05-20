from pydantic import BaseModel, Field, model_validator

from pipelex.cogt.image.prompt_image import PromptImageDetail
from pipelex.cogt.llm.llm_report import LLMTokensUsage
from pipelex.types import Self, StrEnum


class ReasoningEffort(StrEnum):
    NONE = "none"
    MINIMAL = "minimal"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    XHIGH = "xhigh"
    MAX = "max"


########################################################################
# Inputs
########################################################################


class LLMJobParams(BaseModel):
    temperature: float = Field(..., ge=0, le=1)
    max_tokens: int | None = Field(default=None, gt=0)
    image_detail: PromptImageDetail | None = None
    seed: int | None = Field(default=None, ge=0)
    reasoning_effort: ReasoningEffort | None = Field(default=None, strict=False)
    reasoning_budget: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_reasoning_effort_or_budget(self) -> Self:
        if self.reasoning_effort is not None and self.reasoning_budget is not None:
            msg = (
                "LLMJobParams cannot have both 'reasoning_effort' and 'reasoning_budget' specified. "
                f"Use one or the other. reasoning_effort: {self.reasoning_effort}, reasoning_budget: {self.reasoning_budget}"
            )
            raise ValueError(msg)
        return self


class LLMJobConfig(BaseModel):
    # instructor's schema re-ask budget for one LLM job — total attempts (initial + re-asks).
    # Default sourced from cogt.llm_config.schema_reask_max_attempts.
    schema_reask_max_attempts: int = Field(..., ge=1, le=10)


########################################################################
# Outputs
########################################################################


class LLMJobReport(BaseModel):
    llm_tokens_usage: LLMTokensUsage | None = None
