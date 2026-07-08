from typing import TYPE_CHECKING, Protocol

from pydantic import BaseModel, ConfigDict

from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.pipeline.job_metadata import JobMetadata

if TYPE_CHECKING:
    # Guarded to avoid a cycle: the transport module imports PipeFuncExecutionResult from here.
    from pipelex.pipe_operators.func.pipe_func_execution_transport import PipeFuncExecutionRequest, PipeFuncExecutionResponse


class PipeFuncExecutionResult(BaseModel):
    """The outcome of running one PipeFunc, produced by a PipeFuncExecutor.

    Carries the already-coerced output content (str/list results are normalized to StuffContent by
    the executor, so the operator sees one shape regardless of where the function ran) plus the
    trace metadata the operator records for the graph. The operator no longer holds the callable in
    sandbox-hosted mode, so the module/qualname must ride back on this result rather than being read
    off the function object at the call site.

    Serialization-safe on purpose: in sandbox-hosted mode this crosses the Temporal activity
    boundary back from the worker to the workflow (the StuffContent field round-trips via kajson).
    """

    model_config = ConfigDict(frozen=True)

    content: StuffContent
    function_module: str | None = None
    function_qualname: str | None = None


class PipeFuncExecutorProtocol(Protocol):
    """The execution seam for PipeFunc — the direct mirror of ``ContentGeneratorProtocol``.

    The default in-process implementation runs the customer function in this process. Under a
    Temporal-enabled hub a sandbox-hosted implementation dispatches to an activity that runs the
    function in an isolated sandbox instead. Either way the operator (``_live_run_operator_pipe``)
    stays identical: it calls ``run_pipe_func`` and then builds the output stuff, mutates working
    memory, and records the trace — none of which touches customer code.
    """

    async def run_pipe_func(
        self,
        *,
        job_metadata: JobMetadata,
        pipe_code: str,
        function_name: str,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
    ) -> PipeFuncExecutionResult: ...

    async def run_pipe_func_transported(self, *, request: "PipeFuncExecutionRequest") -> "PipeFuncExecutionResponse":
        """Run one PipeFunc from a *serialized* request and return a *serialized* response.

        The transported sibling of ``run_pipe_func``: it takes a ``PipeFuncExecutionRequest`` (crate +
        transported working memory) instead of live objects, and returns a ``PipeFuncExecutionResponse``
        (the output as a transported working memory, preserving dynamic-class identity). This is the
        seam a serialized boundary crosses — a Temporal activity (``act_pipe_func``) resolves an
        executor by ``execution_mode`` and calls this, so it never needs live objects. ``direct`` runs
        it in-process (also what a sandbox box runs internally); a sandbox executor forwards the
        request to its box and returns the box's response.
        """
        ...
