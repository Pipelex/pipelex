"""What a kernel LLM call hands back.

More than the produced value, because the interpreter's execution-graph tracer consumes the
intermediates — the rendered prompts, the resolved model setting, the structuring path — and
recomputing them outside the kernel would mean a second assembly path, which is the drift this
extraction exists to kill.

The memory contract, restated where callers meet it: **the returned `memory` is the result.** A
kernel call may mutate the memory it was passed, and today inline execution aliases the two — but a
serialization boundary will not, so no caller may rely on the argument having been updated.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_setting import LLMSetting
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.stuff_content import StuffContent


class StructuringPath(StrEnum):
    """How the output was produced — the tracer's vocabulary, owned here rather than at each caller."""

    TEXT = "text"
    OBJECT_DIRECT = "object_direct"
    OBJECT_LIST = "object_list"


class LlmTextResult(BaseModel):
    """The outcome of a kernel LLM call with a text output."""

    model_config = ConfigDict(frozen=True)

    memory: WorkingMemory
    text: str
    rendered_prompt: LLMPrompt
    llm_setting: LLMSetting
    structuring_path: StructuringPath


class LlmObjectResult(BaseModel):
    """The outcome of a kernel LLM call with a structured output.

    `content` is the generated object, or a `ListContent` of them when several were requested.
    """

    model_config = ConfigDict(frozen=True)

    memory: WorkingMemory
    content: StuffContent
    rendered_prompt: LLMPrompt
    llm_setting: LLMSetting
    structuring_path: StructuringPath
