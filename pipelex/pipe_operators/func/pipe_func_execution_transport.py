from mthds.protocol.problem.registry import CoreCode
from packaging.version import InvalidVersion, Version
from pydantic import ValidationError

from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.stored_value_loader import load_stored_values
from pipelex.core.stuffs.stored_value_storer import store_large_values
from pipelex.core.stuffs.stored_value_walker import find_unloaded_stored_values
from pipelex.errors.problem import DiagnosticCause, PipelexProblem, ProblemDiagnostics, ProblemView, cap_problem_text, make_problem
from pipelex.interpreter_hub import get_current_library, get_library_manager
from pipelex.libraries.concepts_libraries import typed_by_crate_concepts
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
from pipelex.runtime_hub import get_storage_provider
from pipelex.system.job_metadata import JobMetadata
from pipelex.system.storage_scope import GENERATED_CONTENT_LEAF

# The transport DTOs (``PipeFuncExecutionRequest`` / ``PipeFuncExecutionResponse``) live in the leaf
# ``pipe_func_execution_dtos`` module so the executor protocol can reference them without a hub cycle;
# they are re-exported here (and genuinely used by the builders below), so existing
# ``from ...pipe_func_execution_transport import PipeFuncExecutionRequest`` imports keep working.

MAX_REPORTED_CAUSES = 10
"""The most causes the diagnostics of a function's report keep: the first ones, nearest the error the function raised.

A report's causes are the cause chain of what the function raised, which Python built and which is a handful of errors
deep in practice, but the report is a file the function can write itself, with any number of causes in it, and none of
them may travel whole into a stored run report. The first cause is the class of what the function raised, which the
problem's message names too.
"""


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


async def inline_stored_values_for_sandbox(*, request: PipeFuncExecutionRequest) -> PipeFuncExecutionRequest:
    """The request with every stored value its memory holds read from the run's storage and held inline: what a sandbox can read.

    A sandbox reaches no storage, so a stored `Text`, `Markdown`, `Html` or `JSON` value would reach the function there as
    a reference it cannot read. A host dispatching a call to a sandbox calls this where it reaches the run's storage, in
    the activity running the call on a host runtime, before handing the request over, and
    `store_large_values_of_sandbox_response` on the response once the sandbox returns it. The function receives its
    whole memory, so every stored value of it is loaded, under the run's read scope, a bounded number at a time. The
    inline request goes to the sandbox by upload, never through a workflow's history.

    The memory is typed by the run's own library when this process holds it, such as in a local run, and otherwise by
    a library loaded from the crate's concepts (`typed_by_crate_concepts`).

    Args:
        request: The call's request, as `build_pipe_func_execution_request` built it.

    Returns:
        A copy of the request whose memory holds every value inline; the request itself when it holds no stored value.

    Raises:
        UriReadRefusedError: A stored value's URL is outside the run's read scope.
        UriTextTooLargeError: A stored value is past `[runtime.network] max_fetch_bytes`.
        UriTextNotUtf8Error: The stored bytes of a value are not UTF-8.
        StoredValueUnreadableError: A stored text is not a value of its content's kind.
    """
    with typed_by_crate_concepts(crate=request.crate):
        working_memory = hydrate_working_memory(request.working_memory_raw)
        stored_values = find_unloaded_stored_values(roots={stuff_name: stuff.content for stuff_name, stuff in working_memory.root.items()})
        if not stored_values:
            return request
        await load_stored_values(
            stored_values=stored_values,
            read_scope=request.job_metadata.run_metadata.read_scope,
            storage_provider=get_storage_provider(),
        )
        for stored_value in stored_values:
            stored_value.content.hold_value_inline()
        return request.model_copy(update={"working_memory_raw": working_memory.dump_for_transport()})


async def store_large_values_of_sandbox_response(
    *, request: PipeFuncExecutionRequest, response: PipeFuncExecutionResponse
) -> PipeFuncExecutionResponse:
    """The sandbox's response with its output alone, each of its large values stored under the run's storage scope.

    The counterpart of `inline_stored_values_for_sandbox`, called by the host once the sandbox returned: the sandbox
    reaches no storage, so a large value the function returned comes back inline. It is stored here under
    `{storage_scope}/generated/`, as a function run in this process would have it, so the output crosses into a
    workflow's history as its reference. The response keeps the output alone, the memory's main stuff, which is all its
    reader takes (`pipe_func_execution_result_from_response`), since the rest is the memory the sandbox received, inline.
    A dry run's storage scope stores nothing.

    Args:
        request: The request the call was made with, whose crate types the output and whose run's scope stores it.
        response: The response the sandbox returned.

    Returns:
        The response whose output memory holds the output alone, its large values as references.
    """
    with typed_by_crate_concepts(crate=request.crate):
        output_stuff = hydrate_working_memory(response.output_memory_raw).get_main_stuff()
        await store_large_values(
            roots={"output": output_stuff.content},
            storage_provider=get_storage_provider(),
            storage_scope=request.job_metadata.run_metadata.storage_scope,
            leaf=GENERATED_CONTENT_LEAF,
        )
        output_memory = WorkingMemoryFactory.make_empty()
        output_memory.set_new_main_stuff(stuff=output_stuff)
        return response.model_copy(update={"output_memory_raw": output_memory.dump_for_transport()})


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
    the error, its message, the classes and codes of its first :data:`MAX_REPORTED_CAUSES` causes, every one of these
    texts capped at :data:`~pipelex.errors.problem.MAX_PROBLEM_TEXT_LENGTH` characters, and the runtime's version when
    it is a public version number (:func:`_reported_runtime_version`).

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
        causes: list[DiagnosticCause] = []
        for cause in (written.diagnostics.causes or [])[:MAX_REPORTED_CAUSES]:
            code = cap_problem_text(text=cause.code) if cause.code is not None else None
            causes.append(DiagnosticCause(error_class=cap_problem_text(text=cause.error_class), code=code))
        diagnostics = ProblemDiagnostics(
            error_class=cap_problem_text(text=written.diagnostics.error_class),
            message=cap_problem_text(text=written.diagnostics.message),
            causes=causes or None,
            runtime_version=_reported_runtime_version(written=written.diagnostics.runtime_version),
        )
    return make_problem(
        code=CoreCode.PIPE_FUNCTION_RAISED,
        view=ProblemView.OPERATOR,
        params=written.params.as_wire() if written.params is not None else None,
        diagnostics=diagnostics,
    )


def _reported_runtime_version(*, written: str | None) -> str | None:
    """The runtime version a function's report names, kept only when it is a public version number; `None` otherwise.

    The version rides the metadata view of the problem too (`problem_metadata`), which holds no sentence and no name a
    user wrote, while a report is a file the function can write itself. A version number, normalized and with no local
    label, is digits and a release marker at most, so it says nothing else; a text that is no such number, or that the
    cap at `MAX_PROBLEM_TEXT_LENGTH` characters cuts, is dropped rather than kept.
    """
    if written is None:
        return None
    try:
        version = Version(cap_problem_text(text=written))
    except InvalidVersion:
        return None
    if version.local is not None:
        return None
    return str(version)
