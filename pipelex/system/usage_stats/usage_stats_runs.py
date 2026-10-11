"""What a run's inference calls did, tallied as they end, for the run's `run_completed` and `model_used` events.

The run's events carry its pipes and its token usage, but not what a call that failed was refused for, which backend
served a model, or how many images and pages a call produced. The inference call's own summary event knows all of it
when the call ends, so it notes it here, in the tally of the run the call belongs to: a context variable `PipeRun`
sets for the duration of a run, which the run's tasks inherit. With no run tallying (statistics off, or a call made
outside any run), noting costs one context-variable read.

The tally is in-process: a run whose calls execute in other processes, a Temporal worker's, is tallied there or not at
all. The hosted plane sets `DO_NOT_TRACK=1`, so no such run reports.
"""

import threading
from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar

from pipelex.base_exceptions import ErrorDomain, PipelexError
from pipelex.system.usage_stats.usage_stats_contract import UsageStatsErrorDomain, UsageStatsMethodSource

#: The failure categories a `model_used` event counts, the runtime's own `InferenceErrorCategory` values.
FAILURE_CATEGORIES: tuple[str, ...] = ("transient", "configuration", "content", "capacity", "ambiguous", "unknown")
#: The category a failure is counted under when the runtime could not classify it.
UNCLASSIFIED_FAILURE_CATEGORY = "unknown"


class ModelCallTally:
    """The calls a run made to one model, as their summary events saw them end."""

    def __init__(self, *, backend_name: str) -> None:
        self.backend_name = backend_name
        self.calls = 0
        self.failures = 0
        self.failures_by_category: dict[str, int] = dict.fromkeys(FAILURE_CATEGORIES, 0)
        self.images_generated = 0
        self.pages_extracted = 0


class RunInferenceTally:
    """The inference calls of one run, by model handle; calls whose model never resolved count only in the totals."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.calls = 0
        self.failures = 0
        self.models: dict[str, ModelCallTally] = {}

    def note_call(
        self,
        *,
        model_handle: str,
        backend_name: str | None,
        failed: bool,
        failure_category: str | None,
        images_generated: int,
        pages_extracted: int,
    ) -> None:
        with self._lock:
            self.calls += 1
            if failed:
                self.failures += 1
            if backend_name is None:
                return
            model_tally = self.models.get(model_handle)
            if model_tally is None:
                model_tally = ModelCallTally(backend_name=backend_name)
                self.models[model_handle] = model_tally
            model_tally.calls += 1
            model_tally.images_generated += images_generated
            model_tally.pages_extracted += pages_extracted
            if failed:
                model_tally.failures += 1
                category = failure_category if failure_category in model_tally.failures_by_category else UNCLASSIFIED_FAILURE_CATEGORY
                model_tally.failures_by_category[category] += 1


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


def usage_stats_error_domain(*, error: BaseException | None) -> UsageStatsErrorDomain:
    """Who can fix a failure, by the runtime's own error report: `input`, `config`, `runtime`, or `other` when it cannot say."""
    if not isinstance(error, PipelexError):
        return UsageStatsErrorDomain.OTHER
    return usage_stats_error_domain_of(domain=error.to_error_report().error_domain)


def usage_stats_error_domain_of(*, domain: ErrorDomain | str | None) -> UsageStatsErrorDomain:
    """The statistics' error domain of a runtime domain, given as the enum or as its value; `other` for none or another."""
    if domain is None:
        return UsageStatsErrorDomain.OTHER
    try:
        runtime_domain = ErrorDomain(domain)
    except ValueError:
        return UsageStatsErrorDomain.OTHER
    match runtime_domain:
        case ErrorDomain.INPUT:
            return UsageStatsErrorDomain.INPUT
        case ErrorDomain.CONFIG:
            return UsageStatsErrorDomain.CONFIG
        case ErrorDomain.RUNTIME:
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
