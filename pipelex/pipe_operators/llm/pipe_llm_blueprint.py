from typing import Literal

from pipelex.cogt.llm.llm_setting import LLMModelChoice
from pipelex.core.pipes.pipe_blueprint import PipeBlueprint
from pipelex.types import StrEnum


class StructuringMethod(StrEnum):
    DIRECT = "direct"
    PRELIMINARY_TEXT = "preliminary_text"


class PipeLLMBlueprint(PipeBlueprint):
    type: Literal["PipeLLM"] = "PipeLLM"
    pipe_category: Literal["PipeOperator"] = "PipeOperator"

    model: LLMModelChoice | None = None
    model_to_structure: LLMModelChoice | None = None

    system_prompt: str | None = None
    prompt: str | None = None

    structuring_method: StructuringMethod | None = None
