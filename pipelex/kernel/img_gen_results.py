"""What a kernel image-generation call hands back.

Thinner than the LLM envelope on purpose: everything the interpreter's execution-graph tracer records
for an image step — the resolved model, the rendered prompts, the aspect ratio, the image count — is
either an input the caller already holds or something it resolved through the ops functions before
calling. So this carries the produced content and, above all, the memory: **the returned `memory` is
the result**, and no caller may rely on the argument having been mutated.

The serialization note on `pipelex.kernel.llm_results` applies here too — `content` is annotated with
the base `StuffContent`, so use `kajson` rather than a plain `model_dump()`.
"""

from pydantic import BaseModel, ConfigDict

from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.stuff_content import StuffContent


class ImgGenResult(BaseModel):
    """The outcome of a kernel image-generation call.

    `content` is the generated image, or a `ListContent` of them when several were requested.
    """

    model_config = ConfigDict(frozen=True)

    memory: WorkingMemory
    content: StuffContent
