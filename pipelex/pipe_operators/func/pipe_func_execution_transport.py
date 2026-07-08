from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.hub import get_current_library, get_library_manager
from pipelex.libraries.library_crate import LibraryCrate
from pipelex.pipe_operators.func.exceptions import PipeFuncTransportError
from pipelex.pipe_operators.func.pipe_func_executor_protocol import PipeFuncExecutionResult
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.runtime_bridge.primitives.hydration import hydrate_working_memory

# Runaway-code guard: how long a single PipeFunc may run out-of-process before it is killed. Lives on
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
        description="Max wall-clock seconds the PipeFunc may run before it is killed (plan-dependent).",
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


def build_pipe_func_execution_request(
    *,
    job_metadata: JobMetadata,
    pipe_code: str,
    function_name: str,
    working_memory: WorkingMemory,
    pipe_run_params: PipeRunParams,
    timeout_seconds: float = DEFAULT_PIPE_FUNC_TIMEOUT_SECONDS,
) -> PipeFuncExecutionRequest:
    """Package one PipeFunc call for out-of-process execution: the current library's crate (with sources) + the transported inputs.

    Shared by every out-of-process executor — the in-process sandbox one and the Temporal in-workflow
    one — so the request shape is defined once. Reads the crate from the current library via the
    library manager; both the ``load_libraries`` (hosted dir-load) and the ``load_from_crate``
    (transported, workflow) paths make it available through ``get_crate``. Building the request is
    pure/deterministic, so it is safe to call inside a Temporal workflow before dispatching.
    """
    library_id = get_current_library()
    crate = get_library_manager().get_crate(library_id=library_id)
    if crate is None:
        msg = (
            f"Cannot run PipeFunc '{function_name}' out-of-process: no crate is available for the current library "
            f"'{library_id}'. The library must be loaded in sandbox-hosted mode so the customer sources travel on the crate."
        )
        raise PipeFuncTransportError(msg)

    return PipeFuncExecutionRequest(
        crate=crate,
        working_memory_raw=working_memory.dump_for_transport(),
        pipe_code=pipe_code,
        function_name=function_name,
        job_metadata=job_metadata,
        pipe_run_params=pipe_run_params,
        timeout_seconds=timeout_seconds,
    )


def pipe_func_execution_result_from_response(response: PipeFuncExecutionResponse) -> PipeFuncExecutionResult:
    """Rebind a transported response into a PipeFuncExecutionResult against THIS process's registry.

    The output rode back as a transported working memory whose main stuff is the PipeFunc output;
    hydrating it here rebinds the class from the concept's ``structure_class_name`` (present for
    native and inline-structure concepts; a customer output class shipped only as .py is a known,
    deferred limitation).
    """
    output_memory = hydrate_working_memory(response.output_memory_raw)
    content = output_memory.get_main_stuff().content
    return PipeFuncExecutionResult(
        content=content,
        function_module=response.function_module,
        function_qualname=response.function_qualname,
    )
