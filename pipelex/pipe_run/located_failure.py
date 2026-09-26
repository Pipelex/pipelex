"""A run failure, reported as its root fault at the pipe where it happened.

When a pipe fails during a run, the error that reaches a surface sits under several wrappers: the
pipe router's `PipeRouterError`, which knows the failing pipe and its stack, maybe a runtime bridge's
`PipelexBridgeDispatchError`, and the runner's `PipelineExecutionError`. None of them is what went
wrong. The report of such a failure is therefore built from its **root fault**, the innermost
`PipelexError` of the cause chain, and only located by the wrappers:

- the root fault stops at a foreign exception, whose stand-in is the fault, and an error raised from
  one of its own class counts as the outer, more contextual one (see `find_root_fault`);
- the identity (`error_type`, `title`, `type_uri`) is the root fault's, and so are its caller-facing
  flag, its `validation_errors` and its `migration`;
- the message names the failing pipe and its path from the entry pipe, then gives the root fault's
  own message unaltered. Pipe codes are the caller's own names, so the message is caller-facing
  exactly when the root fault's is;
- the classification is the cause-chain enrichment's, floored at `runtime`, and when nothing on the
  chain carries a user action, the fallback names the failing pipe.

`ErrorReport` has no location field, so the location rides the message until the error contract
gives it one. A root fault whose report was recovered across a transport boundary (a report
carried by a `PipelexError`, the way a distributed worker's submitter carries it) is taken as it is:
at the runner, with no location on the chain, it is reported unchanged, and a host router packs
the root fault's own report with its location rather than a located report (see
`PipeRouterProtocol._as_pipelex_failure`), so nothing is located twice.
"""

from pydantic import ValidationError

from pipelex.base_exceptions import ErrorDomain, ErrorReport, PipelexError, PipelexUnexpectedError, iter_cause_chain
from pipelex.cogt.inference.error_classification import UserAction, UserActionKind
from pipelex.tools.typing.pydantic_utils import format_pydantic_validation_error

# Joins the pipe codes of a failure's path from the entry pipe down to the pipe that failed.
PIPE_PATH_SEPARATOR = " → "


def find_root_fault(*, error: BaseException) -> PipelexError | None:
    """Return the innermost `PipelexError` on `error`'s cause chain, `error` itself included.

    That is the error that knows what went wrong: every `PipelexError` above it on the chain is a
    wrapper that located it or carried it across a boundary. Two exceptions to "innermost": the walk
    stops at the first exception that is not a `PipelexError`, since what caused a foreign exception
    is that code's own affair and the `PipelexUnexpectedError` standing in for it is the fault; and
    a `PipelexError` raised from one of its own class restates that fault with more context (an
    item index, a remedy), so the outer one is kept. `None` when the chain starts with no
    `PipelexError`.
    """
    root_fault: PipelexError | None = None
    for node in iter_cause_chain(error):
        if not isinstance(node, PipelexError):
            break
        if root_fault is not None and type(node) is type(root_fault):
            continue
        root_fault = node
    return root_fault


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
    """The message a located wrapper of `failure` carries: its root fault's own message, located."""
    root_fault = find_root_fault(error=failure) or failure
    return compose_located_message(pipe_code=pipe_code, pipe_stack=pipe_stack, message=root_fault.to_error_report().message)


def make_unexpected_failure(*, error: Exception) -> PipelexUnexpectedError:
    """Stand a `PipelexUnexpectedError` in for an exception that is not a `PipelexError`.

    Its message names the original class, and it is chained to the original so its traceback
    survives. It is never caller-facing: a foreign exception's text can carry anything, a server
    path or a secret included. A pydantic `ValidationError` keeps the readable rendering the runner
    gives one.
    """
    detail = format_pydantic_validation_error(error) if isinstance(error, ValidationError) else (str(error) or repr(error))
    unexpected_error = PipelexUnexpectedError(f"{type(error).__name__}: {detail}")
    unexpected_error.__cause__ = error
    unexpected_error.__suppress_context__ = True
    return unexpected_error


def _fallback_user_action(*, pipe_code: str, pipe_stack: list[str]) -> UserAction:
    if pipe_stack:
        detail = f"The run failed in pipe '{pipe_code}': the message gives the cause."
    else:
        detail = f"The run of '{pipe_code}' failed: the message gives the cause."
    return UserAction(kind=UserActionKind.UNKNOWN, detail=detail)


def _find_root_fault_below(*, wrapper: PipelexError) -> PipelexError | None:
    """The root fault under `wrapper`, or `None` when it wraps no `PipelexError` or its chain loops back to it."""
    cause = wrapper.__cause__
    if cause is None:
        return None
    # A cyclic chain that reaches the wrapper again would make the root fault's report recurse
    # into the wrapper's: report the wrapper as itself instead, as the base enrichment does.
    if any(node is wrapper for node in iter_cause_chain(cause)):
        return None
    return find_root_fault(error=cause)


def build_located_failure_report(
    *,
    wrapper: PipelexError,
    own_report: ErrorReport,
    pipe_code: str,
    pipe_stack: list[str],
) -> ErrorReport:
    """Build the report of a located run failure from its root fault.

    Args:
        wrapper: The located wrapper whose report this is (a `PipeRouterError` or a
            `PipelineExecutionError`).
        own_report: The wrapper's own report, as `PipelexError.to_error_report` builds it: its own
            identity, and the classification enriched from its cause chain.
        pipe_code: The pipe that failed.
        pipe_stack: That pipe's path from the entry pipe, ending with it. Empty when the location is
            unknown, in which case the message is the root fault's, unlocated.

    Returns:
        The root fault's report, with the located message and the chain's classification.
    """
    root_fault = _find_root_fault_below(wrapper=wrapper)
    identity_report = root_fault.to_error_report() if root_fault is not None else own_report
    return identity_report.model_copy(
        update={
            "message": compose_located_message(pipe_code=pipe_code, pipe_stack=pipe_stack, message=identity_report.message),
            "error_category": own_report.error_category,
            "error_domain": own_report.error_domain or ErrorDomain.RUNTIME,
            "retryable": own_report.retryable,
            "user_action": own_report.user_action or _fallback_user_action(pipe_code=pipe_code, pipe_stack=pipe_stack),
            "model": own_report.model,
            "provider": own_report.provider,
            "provider_metadata": own_report.provider_metadata,
        }
    )
