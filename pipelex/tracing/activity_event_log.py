"""Process-local cached event log for runner-side activity emission.

When activities run on a separate worker pool from the workflow router,
the router's `set_event_log` never registers a context on the runner's
ReportingManager — the runner-side `_event_log_contexts` dict is permanently
empty for every workflow that runs there. This module provides the per-process
backstop: a lazily-constructed event log, stamped with a stable
`act_{pid}_{uuid8}` writer_id, that emits into the same backend partition as
the rest of the run.

The cache-and-writer-id construction is guarded by `threading.Lock` with
double-checked locking so concurrent first-emitters from N activity threads
agree on a single writer_id and reuse the same backend instance.
"""

import atexit
import os
import threading
from uuid import uuid4

from pipelex import log
from pipelex.system.configuration.configs import TracingConfig
from pipelex.tracing.event_log_factory import make_event_log
from pipelex.tracing.event_log_protocol import EventLogProtocol

_lock = threading.Lock()
_cached_event_log: EventLogProtocol | None = None
_writer_id: str | None = None
_warning_emitted: bool = False


def get_or_create_activity_event_log(tracing_config: TracingConfig) -> EventLogProtocol | None:
    """Return the per-process event log for runner-side emission.

    Returns None when tracing is disabled — callers must skip emit. On the
    first successful call, generates a stable per-process writer_id of the
    form ``act_{pid}_{uuid8}`` and constructs the backend via
    :func:`pipelex.tracing.event_log_factory.make_event_log`. Subsequent
    calls reuse the cached instance.

    Thread-safety: cache check + creation is wrapped in a module-level
    :class:`threading.Lock` (double-checked) so concurrent first-callers
    from N activity threads observe the same writer_id and the same
    backend instance.

    The caller is responsible for catching specific exceptions that
    ``make_event_log`` may raise (``OSError``, ``MissingDependencyError``,
    ``PipelexConfigError``); this function does not swallow them so the
    runner-side emit site can log a single WARNING with the right context.
    """
    global _cached_event_log, _writer_id  # noqa: PLW0603
    if not tracing_config.is_enabled:
        return None
    if _cached_event_log is not None:
        return _cached_event_log
    with _lock:
        if _cached_event_log is not None:
            return _cached_event_log
        new_writer_id = f"act_{os.getpid()}_{uuid4().hex[:8]}"
        new_event_log = make_event_log(tracing_config, writer_id=new_writer_id)
        _writer_id = new_writer_id
        _cached_event_log = new_event_log
        atexit.register(_close_event_log_atexit)
        return _cached_event_log


def warn_once_runner_fallback_engaged(workflow_id: str, writer_id: str) -> None:
    """Log a single WARNING the first time the runner fallback engages.

    The warning is per-process; subsequent fallback emissions from the same
    process are silent. Operators see one unmistakable signal in the worker
    logs that runner-side emission is in use, without WARNING spam at high
    activity throughput.
    """
    global _warning_emitted  # noqa: PLW0603
    if _warning_emitted:
        return
    with _lock:
        if _warning_emitted:
            return
        _warning_emitted = True
    log.warning(
        f"Runner-side usage event emission engaged "
        f"(workflow_id={workflow_id}, writer_id={writer_id}). "
        "Activity is emitting into the per-process activity event log because "
        "no _event_log_contexts entry was registered in this process. "
        "This is expected when activities run on a separate worker pool from the workflow router."
    )


def _close_event_log_atexit() -> None:
    """Best-effort close of the cached event log at interpreter shutdown."""
    if _cached_event_log is None:
        return
    try:
        _cached_event_log.close()
    except OSError:
        # Interpreter shutdown — file handles may already be torn down. Drop quietly.
        pass


def _reset_for_tests() -> None:  # pyright: ignore[reportUnusedFunction]
    """Reset module-level state. For test fixtures only — never call from production code.

    Closes any cached event log, clears the writer_id, and resets the one-shot
    warning flag so subsequent tests observe a fresh process-like state.
    """
    global _cached_event_log, _writer_id, _warning_emitted  # noqa: PLW0603
    if _cached_event_log is not None:
        try:
            _cached_event_log.close()
        except OSError:
            pass
    _cached_event_log = None
    _writer_id = None
    _warning_emitted = False
