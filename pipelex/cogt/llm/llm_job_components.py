from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field

from pipelex.cogt.llm.llm_report import LLMTokensUsage

########################################################################
### Inputs
########################################################################


class LLMJobParams(BaseModel):
    temperature: float = Field(..., ge=0, le=1)
    max_tokens: int | None = Field(None, gt=0)
    seed: int | None = Field(None, ge=0)
    # OpenAI tools / connectors (Responses or Chat Completions tools)
    openai_use_responses_api: bool = False
    openai_tools: Optional[List[Dict[str, Any]]] = None
    openai_tool_choice: Optional[Union[str, Dict[str, Any]]] = None
    openai_parallel_tool_calls: Optional[bool] = None
    openai_response_format: Optional[Dict[str, Any]] = None
    openai_web_search_options: Optional[Dict[str, Any]] = None


class LLMJobConfig(BaseModel):
    is_streaming_enabled: bool
    max_retries: int = Field(..., ge=1, le=10)


########################################################################
### Outputs
########################################################################


class LLMJobReport(BaseModel):
    llm_tokens_usage: LLMTokensUsage | None = None
