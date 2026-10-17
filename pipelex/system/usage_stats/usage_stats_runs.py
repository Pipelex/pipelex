"""What a run's inference calls did, tallied as they end, for the run's `run_completed` and `model_used` events.

The run's events carry its pipes and its token usage, but not who must act on a call that failed, which backend
served a model, or how many images and pages a call produced. The inference call's own summary event knows all of it
when the call ends, so it notes it here, in the tally of the run the call belongs to: a context variable `PipeRun`
sets for the duration of a run, which the run's tasks inherit. With no run tallying (statistics off, or a call made
outside any run), noting costs one context-variable read.

The tally is in-process: a run whose calls execute in other processes, a Temporal worker's, is tallied there or not at
all. The hosted plane sets `DO_NOT_TRACK=1`, so no such run reports.
"""

import re
import threading
from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar

from mthds.protocol.exceptions import PipelineRequestError
from mthds.protocol.problem.models import Problem
from mthds.protocol.problem.registry import CoreCode, ProblemDomain

from pipelex.base_exceptions import PipelexError
from pipelex.errors.problem import ProblemView
from pipelex.system.usage_stats.usage_stats_contract import (
    ERROR_CODE_MAX_LENGTH,
    ERROR_CODE_PATTERN,
    UsageStatsError,
    UsageStatsErrorDomain,
    UsageStatsMethodSource,
)

#: A failure that is no Pipelex error, which every surface reads as the registry's catch-all.
UNEXPECTED_USAGE_STATS_ERROR = UsageStatsError(code=CoreCode.RUNTIME_UNEXPECTED, domain=UsageStatsErrorDomain.RUNTIME)


class ModelCallTally:
    """The calls a run made to one model through one backend, as their summary events saw them end."""

    def __init__(self, *, backend_name: str) -> None:
        self.backend_name = backend_name
        self.calls = 0
        self.failures = 0
        self.failures_by_domain: dict[UsageStatsErrorDomain, int] = dict.fromkeys(UsageStatsErrorDomain, 0)
        self.images_generated = 0
        self.pages_extracted = 0


class RunInferenceTally:
    """The inference calls of one run, by model handle and backend; calls whose model never resolved count only in the totals.

    A handle can be served by more than one backend in one run, as when a call falls back to another, so each pair is
    tallied on its own and each call is attributed to the backend that made it. The run's usage reports name that backend
    themselves, since two backends can call a model by the same identifier.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.calls = 0
        self.failures = 0
        self.models: dict[tuple[str, str], ModelCallTally] = {}

    def note_call(
        self,
        *,
        model_handle: str,
        backend_name: str | None,
        failure_domain: UsageStatsErrorDomain | None,
        images_generated: int,
        pages_extracted: int,
    ) -> None:
        with self._lock:
            self.calls += 1
            if failure_domain is not None:
                self.failures += 1
            if backend_name is None:
                return
            model_tally = self.models.get((model_handle, backend_name))
            if model_tally is None:
                model_tally = ModelCallTally(backend_name=backend_name)
                self.models[model_handle, backend_name] = model_tally
            model_tally.calls += 1
            model_tally.images_generated += images_generated
            model_tally.pages_extracted += pages_extracted
            if failure_domain is not None:
                model_tally.failures += 1
                model_tally.failures_by_domain[failure_domain] += 1


_RUN_TALLY: ContextVar[RunInferenceTally | None] = ContextVar("pipelex_usage_stats_run_tally", default=None)


def current_run_tally() -> RunInferenceTally | None:
    """The tally of the run this code runs in, or `None` when no run is tallying."""
    return _RUN_TALLY.get()


@contextmanager
def tallying_inference_calls(*, tally: RunInferenceTally | None) -> Generator[None, None, None]:
    """Tally the inference calls made inside the block in `tally`, the run's tasks included, which inherit the context.

    With no tally, the run reports no statistics, and the block runs as it would without this.
    """
    if tally is None:
        yield
        return
    token = _RUN_TALLY.set(tally)
    try:
        yield
    finally:
        _RUN_TALLY.reset(token)


def usage_stats_error(*, error: BaseException | None) -> UsageStatsError:
    """The code of a failure and its domain, as its problem gives them; `runtime.unexpected` for an error that carries none.

    A Pipelex error's code is its problem's, which a cause reporting a problem of its own, such as one recovered across
    a transport boundary, decides, as every other surface reads it. A request error of the MTHDS client carries the
    problem it read, which is read as it is. Any other error, and a failure with no error to read, is the catch-all,
    since every failure has a code.
    """
    if isinstance(error, PipelexError):
        return usage_stats_error_of_problem(problem=error.to_problem(view=ProblemView.CALLER))
    if isinstance(error, PipelineRequestError):
        return usage_stats_error_of_problem(problem=error.problem)
    return UNEXPECTED_USAGE_STATS_ERROR


def usage_stats_failure_domain(*, error: BaseException) -> UsageStatsErrorDomain:
    """Who must act on a failure, read off its code alone, without building its problem.

    The cheap reading a hot path takes, such as a failed inference call's: the code the error resolves to, and the
    domain the registry gives it, the same domain :func:`usage_stats_error` reads off the problem.
    """
    if isinstance(error, PipelexError):
        recovered = error.recovered_problem()
        domain = recovered.effective_domain if recovered is not None else error.resolve_domain()
        return usage_stats_error_domain_of(domain=domain)
    if isinstance(error, PipelineRequestError):
        return usage_stats_error_domain_of(domain=error.problem.effective_domain)
    return UNEXPECTED_USAGE_STATS_ERROR.domain


def is_reportable_error_code(*, code: str) -> bool:
    """Whether a code fits the contract's pattern and length, as every registry's does."""
    return len(code) <= ERROR_CODE_MAX_LENGTH and re.fullmatch(ERROR_CODE_PATTERN, code) is not None


def usage_stats_error_of_problem(*, problem: Problem) -> UsageStatsError:
    """The code and the domain of a problem a surface reports.

    A code the contract's pattern refuses, which no registry gives, reads as the catch-all rather than losing the event.
    """
    if not is_reportable_error_code(code=problem.code):
        return UNEXPECTED_USAGE_STATS_ERROR
    return UsageStatsError(code=problem.code, domain=usage_stats_error_domain_of(domain=problem.effective_domain))


def usage_stats_error_domain_of(*, domain: ProblemDomain) -> UsageStatsErrorDomain:
    """The statistics' error domain of a problem's domain: the same closed list, under the contract's own enum."""
    match domain:
        case ProblemDomain.INPUT:
            return UsageStatsErrorDomain.INPUT
        case ProblemDomain.METHOD:
            return UsageStatsErrorDomain.METHOD
        case ProblemDomain.ACCOUNT:
            return UsageStatsErrorDomain.ACCOUNT
        case ProblemDomain.OPERATOR:
            return UsageStatsErrorDomain.OPERATOR
        case ProblemDomain.RUNTIME:
            return UsageStatsErrorDomain.RUNTIME


_METHOD_SOURCE: ContextVar[UsageStatsMethodSource | None] = ContextVar("pipelex_usage_stats_method_source", default=None)


def declare_method_source(*, source: UsageStatsMethodSource) -> None:
    """Declare where the method about to run came from, by kind only, for its `run_completed`.

    Called where the kind is known for sure, a CLI resolving a method by name, address or path, before the runner
    sees only the files it was handed; a declaration stands for the rest of the context it was made in.
    """
    _METHOD_SOURCE.set(source)


@contextmanager
def method_source_scope(*, source: UsageStatsMethodSource) -> Generator[None, None, None]:
    """Declare the method's source for the block, unless the caller already declared a more precise one."""
    if _METHOD_SOURCE.get() is not None:
        yield
        return
    token = _METHOD_SOURCE.set(source)
    try:
        yield
    finally:
        _METHOD_SOURCE.reset(token)


def current_method_source() -> UsageStatsMethodSource:
    """Where the method running now came from, `other` when nothing declared it."""
    return _METHOD_SOURCE.get() or UsageStatsMethodSource.OTHER
