from pydantic import BaseModel, Field

from pipelex.cogt.llm.llm_report import LLMTokensUsage

########################################################################
### Inputs
########################################################################


class LLMJobParams(BaseModel):
    temperature: float = Field(..., ge=0, le=1)
    max_tokens: int | None = Field(None, gt=0)
    seed: int | None = Field(None, ge=0)


class LLMJobConfig(BaseModel):
    is_streaming_enabled: bool
    max_retries: int = Field(..., ge=1, le=10)


########################################################################
### Outputs
########################################################################


class LLMJobReport(BaseModel):
    llm_tokens_usage: LLMTokensUsage | None = None
