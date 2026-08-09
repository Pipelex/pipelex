"""What a kernel function call hands back.

Two envelopes rather than one, because two different things end: `FuncCallResult` is the outcome of
running the customer's function itself, and `FuncResult` is the outcome of a whole func step — the
call plus the memory write-back. The split is not decorative: the interpreter's pluggable executors
run the *call* somewhere else entirely (a sandbox, a Temporal activity) and hand back exactly the
first shape, so it has to exist on its own.

Both carry the function's module and qualified name. They are not cosmetic either: the execution
tracer records them, and a caller that dispatched the call out-of-process no longer holds the
function object to read them off — so they ride back on the result or they are lost.

The serialization note on `pipelex.kernel.llm_results` applies here too — `content` is annotated with
the base `StuffContent`, so use `kajson` rather than a plain `model_dump()`.
"""

from pydantic import BaseModel, ConfigDict

from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.stuff_content import StuffContent


class FuncCallResult(BaseModel):
    """The outcome of running one registered function, with its return value already coerced."""

    model_config = ConfigDict(frozen=True)

    content: StuffContent
    function_module: str | None = None
    function_qualname: str | None = None


class FuncResult(BaseModel):
    """The outcome of a kernel func call: the call's result, plus the memory it was written into.

    The memory contract holds as everywhere else: **the returned `memory` is the result.**
    """

    model_config = ConfigDict(frozen=True)

    memory: WorkingMemory
    content: StuffContent
    function_module: str | None = None
    function_qualname: str | None = None
