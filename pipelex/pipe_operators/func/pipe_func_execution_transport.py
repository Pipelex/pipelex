from mthds.protocol.problem.registry import CoreCode
from pydantic import ValidationError

from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.errors.problem import DiagnosticCause, PipelexProblem, ProblemDiagnostics, ProblemView, cap_problem_text, make_problem
from pipelex.interpreter_hub import get_current_library, get_library_manager
from pipelex.pipe_operators.func.exceptions import PipeFuncRaisedError, PipeFuncTransportError
from pipelex.pipe_operators.func.pipe_func_execution_dtos import (
    DEFAULT_PIPE_FUNC_TIMEOUT_SECONDS,
    PipeFuncExecutionRequest,
    PipeFuncExecutionResponse,
    PipeFuncRaisedReport,
)
from pipelex.pipe_operators.func.pipe_func_executor_protocol import PipeFuncExecutionResult
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.runtime_bridge.primitives.hydration import hydrate_working_memory
from pipelex.system.job_metadata import JobMetadata

# The transport DTOs (``PipeFuncExecutionRequest`` / ``PipeFuncExecutionResponse``) live in the leaf
# ``pipe_func_execution_dtos`` module so the executor protocol can reference them without a hub cycle;
# they are re-exported here (and genuinely used by the builders below), so existing
# ``from ...pipe_func_execution_transport import PipeFuncExecutionRequest`` imports keep working.


def build_pipe_func_execution_request(
    *,
    job_metadata: JobMetadata,
    pipe_code: str,
    function_name: str,
    working_memory: WorkingMemory,
    pipe_run_params: PipeRunParams,
    timeout_seconds: float = DEFAULT_PIPE_FUNC_TIMEOUT_SECONDS,
) -> PipeFuncExecutionRequest:
    """Package one PipeFunc call for out-of-process execution: the current library's crate, the call's tree, and the transported inputs.

    Shared by every out-of-process executor — the in-process sandbox one and the Temporal in-workflow
    one — so the request shape is defined once. Reads the crate from the current library via the
    library manager; both the ``load_libraries`` (hosted dir-load) and the ``load_from_crate``
    (transported, workflow) paths make it available through ``get_crate``. Building the request is
    pure/deterministic, so it is safe to call inside a Temporal workflow before dispatching.

    ``timeout_seconds`` is the PipeFunc kill-timeout that rides on the request. **The timeout is
    plugin-configured**: core has no key for it — ``[interpreter.pipe_func]`` holds ``execution_mode``
    and nothing else — and each out-of-process executor reads it from its own plugin configuration
    root (our Daytona plugin's ``pipe_func_timeout_seconds``, for one). Callers that have one pass it;
    it falls back to the module default otherwise.
    """
    library_id = get_current_library()
    crate = get_library_manager().get_crate(library_id=library_id)
    if crate is None:
        msg = f"Cannot run PipeFunc '{function_name}' out-of-process: no crate is available for the current library '{library_id}'."
        raise PipeFuncTransportError(msg)

    # The call names its own Python root by digest: the method tree its step was read from, or the tree of the files
    # submitted beside the bundles parsed from content strings. No file's bytes travel with it.
    tree_bundle_ref = crate.tree_bundles.get(pipe_code)
    return PipeFuncExecutionRequest(
        crate=crate,
        tree_digest=tree_bundle_ref.tree_digest if tree_bundle_ref is not None else None,
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
    hydrating it here resolves the stuff's concept ref through the current library and rebinds the
    class from that concept's ``structure_class_name`` (present for native and inline-structure
    concepts; a customer output class shipped only as .py is a known, deferred limitation).
    """
    output_memory = hydrate_working_memory(response.output_memory_raw)
    content = output_memory.get_main_stuff().content
    return PipeFuncExecutionResult(
        content=content,
        function_module=response.function_module,
        function_qualname=response.function_qualname,
    )


def pipe_func_raised_report(*, error: PipeFuncRaisedError) -> PipeFuncRaisedReport:
    """The report a transported call writes to its result file when the function it calls raised `error`.

    The problem is `error`'s in the operator's view, built where the function ran: its code is `pipe.function_raised`,
    its parameters name the function and the step, and its diagnostics name the class of what the function raised and
    never its text, which can quote the run's inputs.
    """
    return PipeFuncRaisedReport(problem=error.to_problem(view=ProblemView.OPERATOR).to_wire())


def read_pipe_func_raised_report(*, result_json: str | bytes) -> PipelexProblem | None:
    """The problem of a function that raised in a transported call, read from the call's result file; `None` when it holds none.

    An out-of-process executor reads the result file of a call whose sandbox exited non-zero with it: a report means the
    function itself raised, and the executor raises a Pipelex error carrying the problem, which the step then reports
    as `pipe.function_raised`; no report means the sandbox failed another way, and the failure keeps a code of its own.

    The file was written where the function ran, and the function can write it too, so only what `pipe.function_raised`
    lets it say is kept: a report of another code is no report, the sentences, the domain, the verdict and the step
    are rendered again from the registry with the parameters the code declares, and the diagnostics keep the class of
    the error, its message, capped, the classes and codes of its causes and the runtime's version.

    Args:
        result_json: The content of the result file.

    Returns:
        The problem in the operator's view, or `None` when the file holds no report of the function's failure.
    """
    try:
        report = PipeFuncRaisedReport.model_validate_json(result_json)
        written = PipelexProblem.model_validate(report.problem)
    except ValidationError:
        return None
    if written.code != CoreCode.PIPE_FUNCTION_RAISED:
        return None
    diagnostics: ProblemDiagnostics | None = None
    if written.diagnostics is not None:
        causes = [DiagnosticCause(error_class=cause.error_class, code=cause.code) for cause in written.diagnostics.causes or []]
        diagnostics = ProblemDiagnostics(
            error_class=written.diagnostics.error_class,
            message=cap_problem_text(text=written.diagnostics.message),
            causes=causes or None,
            runtime_version=written.diagnostics.runtime_version,
        )
    return make_problem(
        code=CoreCode.PIPE_FUNCTION_RAISED,
        view=ProblemView.OPERATOR,
        params=written.params.as_wire() if written.params is not None else None,
        diagnostics=diagnostics,
    )
