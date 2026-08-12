"""What a kernel compose call hands back.

The rendered text rides along because the kernel is where it is produced and the interpreter's
execution-graph tracer records it. The memory contract holds as everywhere else in the kernel:
**the returned `memory` is the result**, and no caller may rely on the argument having been mutated.

The serialization note on `pipelex.kernel.llm_results` applies here too — `content` is annotated with
the base `StuffContent`, so use `kajson` rather than a plain `model_dump()`.
"""

from pydantic import BaseModel, ConfigDict

from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.stuff_content import StuffContent


class ComposeResult(BaseModel):
    """The outcome of a kernel compose call over a template."""

    model_config = ConfigDict(frozen=True)

    memory: WorkingMemory
    content: StuffContent
    rendered_text: str
