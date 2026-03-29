"""Type aliases for reporting token usage across inference backends."""

from typing import Annotated

from pydantic import Field

from pipelex.cogt.extract.extract_report import ExtractTokensUsage
from pipelex.cogt.img_gen.img_gen_report import ImgGenTokensUsage
from pipelex.cogt.llm.llm_report import LLMTokensUsage
from pipelex.cogt.search.search_report import SearchTokensUsage

AnyTokensUsage = Annotated[
    LLMTokensUsage | ImgGenTokensUsage | ExtractTokensUsage | SearchTokensUsage,
    Field(discriminator="model_type"),
]
TokensUsage = AnyTokensUsage
