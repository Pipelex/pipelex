"""What the execution graph records of the error that ended a node: its problem, in the caller's view."""

from mthds.protocol.problem.registry import CoreCode

from pipelex import log
from pipelex.base_exceptions import PipelexError
from pipelex.errors.problem import PipelexProblem, ProblemView, make_location, make_problem
from pipelex.pipe_run.located_failure import find_root_fault, located_problem
from pipelex.tools.log.error_fields import error_fields

NODE_PROBLEM_FAULT_MESSAGE = "The problem of a failed pipe could not be built for its trace"
"""The error logged when a failed pipe's problem raises while its node's failure is traced."""


def make_node_problem(*, error: BaseException, pipe_code: str, pipe_path: list[str]) -> PipelexProblem:
    """The problem a node ended by `error` records, located at the node's own pipe.

    The graph is read by whoever reads the run, so the problem is the caller's view: the code's sentences, rendered from
    the parameters a caller may read, and never the error's own message. Its location names the node's pipe and its
    path from the entry pipe, whatever pipe below it the failure happened in. An exception that is not a Pipelex error
    is a fault of ours, `runtime.unexpected`.

    The problem is the error's own (`PipelexError.to_problem`), whose code is the one its cause chain resolves to, the
    code the run fails with. One shape needs more: when the fault deciding that code is a carrier, below the error, of a
    problem recovered across a transport boundary, a step run on a far worker or in a sandbox, the error's own problem
    would stop at the carrier's class code, `runtime.unexpected`. The node then reports the carrier's recovered problem
    as the pipe router does (`pipelex.pipe_run.located_failure.located_problem`), so it reads the code the run fails
    with. The fault is the one `find_root_fault` finds from the error itself, not from below it, so an error that implies
    its code, such as an inference error built with a category, keeps that code rather than its cause's fallback.

    Tracing never changes how a run fails. This runs while the pipe's own error is being handled, on its way to the
    caller, so building the problem must not raise in its place: a problem that cannot be built is logged as an error,
    and the node records `runtime.unexpected`.

    Args:
        error: The error that ended the node.
        pipe_code: The node's pipe.
        pipe_path: The pipe codes from the entry pipe down to the node's pipe, which ends it.

    Returns:
        The node's problem.
    """
    location = make_location(pipe=pipe_code, path=pipe_path or [pipe_code])
    if isinstance(error, PipelexError):
        try:
            root_fault = find_root_fault(error=error)
            if root_fault is not None and root_fault is not error and root_fault.recovered_problem() is not None:
                return located_problem(
                    wrapper=error, root_fault=root_fault, view=ProblemView.CALLER, request_id=None, pipeline_run_id=None, failure_location=location
                )
            return error.to_problem(view=ProblemView.CALLER, failure_location=location)
        except Exception as problem_fault:  # ruff: ignore[blind-except]
            # Unbounded code: `to_problem` reads hooks overridden across the whole error hierarchy, the errors plugins
            # define included, and walks the error's cause chain, so what it raises cannot be enumerated. The pipe's own
            # error is the one the run fails with, so the fault is logged and the node records a fault of ours.
            log.error(
                NODE_PROBLEM_FAULT_MESSAGE,
                fields={"failed_error_type": type(error).__name__, **error_fields(exc=problem_fault)},
            )
    return make_problem(code=CoreCode.RUNTIME_UNEXPECTED, view=ProblemView.CALLER, location=location)
