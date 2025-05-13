# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from typing import Optional

from pydantic import BaseModel, Field

from pipelex.cogt.llm.llm_report import LLMTokensUsage

########################################################################
### Inputs
########################################################################


class LLMJobParams(BaseModel):
    temperature: float = Field(..., ge=0, le=1)
    max_tokens: Optional[int] = Field(None, gt=0)
    seed: Optional[int] = Field(None, ge=0)


class LLMJobConfig(BaseModel):
    is_streaming_enabled: bool
    max_retries: int = Field(..., ge=1, le=10)


########################################################################
### Outputs
########################################################################


class LLMJobReport(BaseModel):
    llm_tokens_usage: Optional[LLMTokensUsage] = None
