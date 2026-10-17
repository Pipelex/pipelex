"""The problem of a failure a local command caught, whatever raised it, and the identifiers its log line carries.

A local CLI reports what a command raised in the operator's view, the view of whoever runs the runtime: a Pipelex
error's own problem, which its code decides, or, for an exception that is no Pipelex error, the registry's catch-all
``runtime.unexpected``, with the exception's class, its message capped and its causes' classes in the diagnostics. Both
CLIs read it from here, ``pipelex-agent`` to print it on its error stream and ``pipelex`` to print its panel, so the two
report one failure the same way.

The log line a command root writes about a failure carries identifiers only: the problem's code, the exception's class
and the classes along its cause chain. An exception's text, and the text of every exception chained to it, can quote a
run's data — a foreign ``ValidationError`` quotes the values it refused, a method function's exception says what the
function was given — and a log record reaches stores and readers a run's data must not. The capped message belongs to
the operator view the terminal prints, and the traceback, which prints every chained exception's text, rides the record
only when the person running the command asked for it.
"""

from typing import Any

from mthds.protocol.problem.models import ProblemLocation
from mthds.protocol.problem.registry import CoreCode

from pipelex.base_exceptions import PipelexError, iter_cause_chain
from pipelex.errors.problem import (
    DiagnosticCause,
    PipelexProblem,
    ProblemDiagnostics,
    ProblemView,
    cap_problem_text,
    make_problem,
    runtime_version,
)
from pipelex.tools.log.error_fields import ERROR_TYPE_FIELD

#: The registry code of the failure's problem, which a line about a failure gives in place of its text.
ERROR_CODE_FIELD = "error.code"

#: The classes along the failure's cause chain, the failure's own first, which a line gives in place of their texts.
ERROR_CHAIN_FIELD = "error.chain"


def foreign_failure_diagnostics(*, error: BaseException) -> ProblemDiagnostics:
    """The operator's diagnostics of an error that is no Pipelex error: its class, its message capped and its causes."""
    causes = [DiagnosticCause(error_class=type(node).__name__) for node in iter_cause_chain(error) if node is not error]
    return ProblemDiagnostics(
        error_class=type(error).__name__,
        message=cap_problem_text(text=str(error) or repr(error)),
        causes=causes or None,
        runtime_version=runtime_version(),
    )


def failure_diagnostics(*, cause: BaseException | None) -> ProblemDiagnostics | None:
    """The operator's diagnostics of the error a refusal was raised from, ``None`` when it was raised from none."""
    if cause is None:
        return None
    if isinstance(cause, PipelexError):
        return cause.to_problem(view=ProblemView.OPERATOR).diagnostics
    return foreign_failure_diagnostics(error=cause)


def failure_problem(*, error: BaseException) -> PipelexProblem:
    """The problem of a failure a local command caught, in the operator's view.

    Args:
        error: What the command caught.

    Returns:
        The Pipelex error's own problem, else ``runtime.unexpected`` with the foreign error's diagnostics.
    """
    if isinstance(error, PipelexError):
        return error.to_problem(view=ProblemView.OPERATOR)
    return make_problem(code=CoreCode.RUNTIME_UNEXPECTED, view=ProblemView.OPERATOR, diagnostics=foreign_failure_diagnostics(error=error))


def failure_log_fields(*, error: BaseException, problem: PipelexProblem) -> dict[str, Any]:
    """The fields a command root's log line about a failure carries: identifiers, never an exception's text.

    Args:
        error: What the command caught.
        problem: The failure's problem, whose code the line names.

    Returns:
        ``error.code``, the problem's code, ``error.type``, the failure's class, and ``error.chain``, the classes along
        its cause chain, its own first.
    """
    return {
        ERROR_CODE_FIELD: problem.code,
        ERROR_TYPE_FIELD: type(error).__name__,
        ERROR_CHAIN_FIELD: [type(node).__name__ for node in iter_cause_chain(error)],
    }


def format_problem_location(*, location: ProblemLocation | None) -> str:
    """Where a fault happened, in words: ``pipe 'summarize', path main > summarize, file 'contracts.mthds', line 12``."""
    if location is None:
        return ""
    parts: list[str] = []
    if location.pipe is not None:
        parts.append(f"pipe '{location.pipe}'")
    if location.path:
        parts.append(f"path {' > '.join(location.path)}")
    if location.input is not None:
        parts.append(f"input '{location.input}'")
    if location.field is not None:
        parts.append(f"field '{location.field}'")
    if location.item is not None:
        parts.append(f"item {location.item}")
    if location.attempt is not None:
        parts.append(f"attempt {location.attempt}")
    if location.file is not None:
        parts.append(f"file '{location.file}'")
    if location.line is not None:
        parts.append(f"line {location.line}")
    if location.column is not None:
        parts.append(f"column {location.column}")
    return ", ".join(parts)


def format_problem_verdict(*, problem: PipelexProblem) -> str:
    """The problem's verdict in words: ``domain runtime, retry yes, after 30 seconds``."""
    verdict = [f"domain {problem.effective_domain}", f"retry {problem.effective_retry}"]
    if problem.retry_after is not None:
        verdict.append(f"after {problem.retry_after:g} seconds")
    return ", ".join(verdict)
