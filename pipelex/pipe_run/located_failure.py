"""A run failure, reported as its root fault at the pipe where it happened.

When a pipe fails during a run, the error that reaches a surface sits under several wrappers: the
pipe router's `PipeRouterError`, which knows the failing pipe and its stack, maybe a runtime bridge's
`PipelexBridgeDispatchError`, and the runner's `PipelineExecutionError`. None of them is what went
wrong, and each takes its cause's code. The problem of such a failure is therefore built from its
**root fault**, the error whose code the failure resolves to, and only located by the wrappers:

- the root fault is the first `PipelexError` down the cause chain that carries a code of its own, the
  same walk `PipelexError.resolve_error_code` makes, so a wrapper that adds the fact deciding the code
  is the root fault over a coded cause; when none carries one, it is the innermost `PipelexError`. The
  walk stops at a foreign exception, whose stand-in is the fault (see `find_root_fault`);
- the problem is the root fault's, its code, parameters and diagnostics included;
- its `location` names the failing pipe and its path from the entry pipe, as members rather than a prefix of
  any sentence, and a code that declares a `pipe` parameter is given the failing pipe.

A root fault whose problem was recovered across a transport boundary (a problem carried by a `PipelexError`,
the way a distributed worker's submitter carries it) is taken as it is: at the runner, with no location on the
chain, it is reported unchanged, and a host router packs the root fault's own problem with its location rather
than a located problem (see `PipeRouterProtocol._as_pipelex_failure`), so nothing is located twice.
"""

from mthds.protocol.problem.models import ProblemLocation
from pydantic import ValidationError

from pipelex.base_exceptions import PipelexError, PipelexUnexpectedError, iter_cause_chain
from pipelex.errors.problem import PipelexProblem, ProblemView, make_location
from pipelex.tools.typing.pydantic_utils import format_pydantic_validation_error

# Joins the pipe codes of a failure's path from the entry pipe down to the pipe that failed.
PIPE_PATH_SEPARATOR = " → "


def find_root_fault(*, error: BaseException) -> PipelexError | None:
    """Return the `PipelexError` on `error`'s cause chain whose code the failure reports, `error` itself included.

    That is the first `PipelexError` down the chain that carries a code of its own
    (`PipelexError.own_error_code`), the error `resolve_error_code` stops at: every `PipelexError`
    above it takes its cause's code, being a wrapper that located it or carried it across a boundary.
    When no error on the chain carries a code of its own, it is the deepest error implying one
    (`PipelexError.implied_error_code`), whose code the failure reports, and else the innermost
    `PipelexError`, whose fallback the failure reports. The walk stops at the first exception that is not a `PipelexError`,
    since what caused a foreign exception is that code's own affair and the `PipelexUnexpectedError`
    standing in for it is the fault; and among wrappers that carry no code, one raised from its own
    class restates that fault with more context, so the outer one is kept. `None` when the chain
    starts with no `PipelexError`.
    """
    root_fault: PipelexError | None = None
    implying_fault: PipelexError | None = None
    for node in iter_cause_chain(error):
        if not isinstance(node, PipelexError):
            break
        if node.own_error_code is not None:
            return node
        if node.implied_error_code is not None:
            implying_fault = node
        if root_fault is not None and type(node) is type(root_fault):
            continue
        root_fault = node
    return implying_fault or root_fault


def find_foreign_fault(*, error: BaseException) -> BaseException | None:
    """Return the non-Pipelex exception a run failure stands in for, or `None`.

    That is the cause of a root fault that is a `PipelexUnexpectedError` standing in for a foreign
    exception, the way the pipe router wraps one. A surface that sorts failures into its own domain
    failures and programming bugs uses it to let the bugs propagate rather than report them as
    the caller's.
    """
    root_fault = find_root_fault(error=error)
    if not isinstance(root_fault, PipelexUnexpectedError):
        return None
    foreign_fault = root_fault.__cause__
    if foreign_fault is None or isinstance(foreign_fault, PipelexError):
        return None
    return foreign_fault


def compose_located_message(*, pipe_code: str, pipe_stack: list[str], message: str) -> str:
    """Prefix `message` with the pipe that failed and, when it is nested, its path from the entry pipe.

    An empty `pipe_stack` means the location is unknown, and the message is returned as it is.
    """
    if not pipe_stack:
        return message
    if len(pipe_stack) == 1:
        return f"Pipe '{pipe_code}' failed: {message}"
    return f"Pipe '{pipe_code}' failed ({PIPE_PATH_SEPARATOR.join(pipe_stack)}): {message}"


def locate_failure_message(*, failure: PipelexError, pipe_code: str, pipe_stack: list[str]) -> str:
    """The message a located wrapper of `failure` carries, for its logs and its operator: its root fault's own message, located."""
    root_fault = find_root_fault(error=failure) or failure
    return compose_located_message(pipe_code=pipe_code, pipe_stack=pipe_stack, message=root_fault.message)


def failure_location_of(*, pipe_code: str, pipe_stack: list[str]) -> ProblemLocation | None:
    """The location of a failure at `pipe_code`, whose path from the entry pipe is `pipe_stack`.

    `None` when the stack is empty, since the location is then unknown.
    """
    if not pipe_stack:
        return None
    return make_location(pipe=pipe_code, path=pipe_stack)


def make_unexpected_failure(*, error: Exception) -> PipelexUnexpectedError:
    """Stand a `PipelexUnexpectedError` in for an exception that is not a `PipelexError`.

    Its message names the original class, and it is chained to the original so its traceback
    survives. Its message only ever reaches an operator, since a foreign exception's text can carry
    anything, a server path or a secret included. A pydantic `ValidationError` keeps the readable
    rendering the runner gives one.
    """
    detail = format_pydantic_validation_error(error) if isinstance(error, ValidationError) else (str(error) or repr(error))
    unexpected_error = PipelexUnexpectedError(f"{type(error).__name__}: {detail}")
    unexpected_error.__cause__ = error
    unexpected_error.__suppress_context__ = True
    return unexpected_error


def _find_root_fault_below(*, wrapper: PipelexError) -> PipelexError | None:
    """The root fault under `wrapper`, or `None` when it wraps no `PipelexError` or its chain loops back to it."""
    cause = wrapper.__cause__
    if cause is None:
        return None
    # A cyclic chain that reaches the wrapper again would make the root fault's problem recurse
    # into the wrapper's: report the wrapper as itself instead.
    if any(node is wrapper for node in iter_cause_chain(cause)):
        return None
    return find_root_fault(error=cause)


def located_root_fault(*, wrapper: PipelexError) -> PipelexError | None:
    """The root fault a located wrapper reports.

    `None` when the wrapper is its own root fault: it chose its code, wraps no `PipelexError`, or loops back to itself.
    """
    # A wrapper whose raise site chose its code is the root fault itself, as `resolve_error_code` reads it.
    if wrapper.own_error_code is not None:
        return None
    return _find_root_fault_below(wrapper=wrapper)


def located_problem(
    *,
    wrapper: PipelexError,
    root_fault: PipelexError,
    view: ProblemView,
    request_id: str | None,
    pipeline_run_id: str | None,
    failure_location: ProblemLocation | None,
) -> PipelexProblem:
    """The problem a located wrapper reports: its root fault's, located at the failing pipe.

    A root fault that builds its own problem, by overriding `to_problem` as a carrier of a problem recovered across a
    transport boundary does, reports that problem as it is, located at `failure_location`. Any other root fault's
    problem is built as the wrapper reports it (`PipelexError.problem_reported_by`), so the facts and the location the
    errors between the two hold, such as the model and the backend a worker attributed a failure to on a wrapper that
    takes its cause's code, reach the problem.

    Args:
        wrapper: The located wrapper, a `PipeRouterError` or a `PipelineExecutionError`.
        root_fault: The root fault below it (`located_root_fault`).
        view: The view of the reader the problem is built for.
        request_id: The request that carried the failure, when known.
        pipeline_run_id: The run the failure belongs to, when one exists.
        failure_location: Where the failing pipe is, when the failure was located at a pipe.

    Returns:
        The problem.
    """
    if type(root_fault).to_problem is not PipelexError.to_problem:
        return root_fault.to_problem(view=view, request_id=request_id, pipeline_run_id=pipeline_run_id, failure_location=failure_location)
    return root_fault.problem_reported_by(
        reporter=wrapper, view=view, request_id=request_id, pipeline_run_id=pipeline_run_id, failure_location=failure_location
    )
