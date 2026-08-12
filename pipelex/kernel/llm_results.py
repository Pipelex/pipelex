"""What a kernel LLM call hands back.

More than the produced value, because the interpreter's execution-graph tracer consumes the
intermediates — the rendered prompts, the resolved model setting, the structuring path — and
recomputing them outside the kernel would mean a second assembly path, which is the drift this
extraction exists to kill.

The memory contract, restated where callers meet it: **the returned `memory` is the result.** A
kernel call may mutate the memory it was passed, and today inline execution aliases the two — but a
serialization boundary will not, so no caller may rely on the argument having been updated.

**Serializing a result: use `kajson`, not `model_dump()`.** `content` is annotated with the base
`StuffContent`, so a plain `model_dump()` drops the concrete subclass's fields — `NumberContent(number=3)`
dumps as `{}`. That is not specific to this model: `Stuff.content` is annotated the same way and behaves
the same way, and the project's answer at both sites is the same one — `kajson` records the class and
reconstructs it, and `model_dump(serialize_as_any=True)` is the escape hatch for a one-off dump. Nothing
serializes these results today (the interpreter unwraps them inline), so this is a note for the
programmatic caller, not a description of a live path.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_setting import LLMSetting
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.stuff_content import StuffContent


class StructuringPath(StrEnum):
    """Which kernel LLM path produced the output, owned here rather than restated at each caller.

    It names the *LLM* paths, not the whole `structuring_path` key the tracer consumes: `PipeStructure`
    writes a bare `"structure"` into that same key, and deliberately has no member here. It calls the
    kernel's pieces (`generate_object_content` and friends) rather than an entry point that returns one
    of these, so no kernel op can produce `"structure"` — adding the member would put a value into a
    "what the kernel op did" type that nothing here can return. The key is `dict[str, Any]` end to end
    and this is a `StrEnum`, so both forms are the same JSON string downstream.
    """

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
