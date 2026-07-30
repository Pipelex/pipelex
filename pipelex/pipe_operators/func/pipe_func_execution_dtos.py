from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from pipelex.libraries.library_crate import LibraryCrate
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.system.job_metadata import JobMetadata

# The serialization-only transport DTOs for out-of-process PipeFunc execution. Deliberately a LEAF
# module — it imports only pure data types (no hub, no protocol, no builder), so the executor protocol
# can reference these types for its transported seam without closing an import cycle through the hub.
# The hub-bound builders that produce/consume them live in ``pipe_func_execution_transport``.

# Runaway-code guard: how long a single PipeFunc may run out-of-process before it times out. The
# in-process guard is best-effort (it cannot interrupt a blocking sync function); the hard kill is
# the execution boundary's job — the sandbox destroys the box, the subprocess is terminated. Lives on
# the request (not a process-wide setting) so it can vary per run — e.g. by the user's plan. 5s
# default; the caller may raise it for a higher tier.
DEFAULT_PIPE_FUNC_TIMEOUT_SECONDS = 5.0


class PipeFuncExecutionRequest(BaseModel):
    """Everything needed to run ONE PipeFunc out-of-process, and nothing else.

    The generic transport primitive for out-of-process PipeFunc execution — sibling to the
    runtime-bridge serialization, carrying only open pipelex types. A backend (a sandbox box, a local
    subprocess) runs it and returns a ``PipeFuncExecutionResponse``; a host runtime (a Temporal
    activity) forwards it across its boundary. Carries the crate (which includes ``python_sources`` —
    the customer's .py to register wherever it runs), the transported working memory (the function's
    inputs), and the identity of the pipe/function to run. Deliberately carries NO secrets.
    """

    model_config = ConfigDict(extra="forbid")

    crate: LibraryCrate
    working_memory_raw: dict[str, Any]
    pipe_code: str
    function_name: str
    job_metadata: JobMetadata
    pipe_run_params: PipeRunParams
    timeout_seconds: float = Field(
        default=DEFAULT_PIPE_FUNC_TIMEOUT_SECONDS,
        gt=0,
        allow_inf_nan=False,
        description="Max wall-clock seconds the PipeFunc may run before it times out (plan-dependent).",
    )


class PipeFuncExecutionResponse(BaseModel):
    """The out-of-process outcome: the output as a transported working memory (main stuff = the output).

    Transporting the output *through a working memory* (rather than as a bare StuffContent) is what
    preserves the dynamic-class identity on the way back — the receiver rebinds the class from the
    concept's ``structure_class_name`` against its own registry, exactly like the worker hydration.
    """

    model_config = ConfigDict(extra="forbid")

    output_memory_raw: dict[str, Any]
    function_module: str | None = None
    function_qualname: str | None = None
