"""Process-local cached event log for activity-side usage emission.

Every usage emission that happens inside a Temporal activity goes through this
per-process event log — by design, whether the activity runs co-located with
the workflow router or on a separate worker pool. Activities do not re-execute
on replay, so routing their emissions into the workflow's in-sandbox buffer
would make the buffer content depend on whether activities actually ran
(replay-determinism breach, audit finding H1). The per-process log, stamped
with a stable `act_{pid}_{uuid8}` writer_id, emits into the same backend
partition as the rest of the run.

The cache-and-writer-id construction is guarded by `threading.Lock` with
double-checked locking so concurrent first-emitters from N activity threads
agree on a single writer_id and reuse the same backend instance.
"""

import atexit
import os
import threading
from typing import ClassVar
from uuid import uuid4

from pipelex import log
from pipelex.system.configuration.configs import TracingConfig
from pipelex.tracing.event_log_factory import make_event_log
from pipelex.tracing.event_log_protocol import EventLogProtocol


class ActivityEventLogCache:
    """Process-local cache holding the runner-side activity event log.

    All state is stored as ``ClassVar`` so the cache is naturally shared across
    every activity thread inside the worker process, with no module-level
    globals. ``_lock`` guards cache construction and the one-shot WARNING flag.
    """

    _lock: ClassVar[threading.Lock] = threading.Lock()
    _cached_event_log: ClassVar[EventLogProtocol | None] = None
    _writer_id: ClassVar[str | None] = None
    _fallback_logged: ClassVar[bool] = False
    _atexit_registered: ClassVar[bool] = False

    @classmethod
    def get_or_create(cls, tracing_config: TracingConfig) -> EventLogProtocol | None:
        """Return the per-process event log for runner-side emission.

        Returns None when tracing is disabled — callers must skip emit. On the
        first successful call, generates a stable per-process writer_id of the
        form ``act_{pid}_{uuid8}`` and constructs the backend via
        :func:`pipelex.tracing.event_log_factory.make_event_log`. Subsequent
        calls reuse the cached instance.

        Thread-safety: cache check + creation is wrapped in a class-level
        :class:`threading.Lock` (double-checked) so concurrent first-callers
        from N activity threads observe the same writer_id and the same
        backend instance.

        The caller is responsible for catching specific exceptions that
        ``make_event_log`` may raise (``OSError``, ``MissingDependencyError``,
        ``PipelexConfigError``); this method does not swallow them so the
        runner-side emit site can log a single WARNING with the right context.
        """
        if not tracing_config.is_enabled:
            return None
        if cls._cached_event_log is not None:
            return cls._cached_event_log
        with cls._lock:
            if cls._cached_event_log is not None:
                return cls._cached_event_log
            new_writer_id = f"act_{os.getpid()}_{uuid4().hex[:8]}"
            new_event_log = make_event_log(tracing_config, writer_id=new_writer_id)
            cls._writer_id = new_writer_id
            cls._cached_event_log = new_event_log
            if not cls._atexit_registered:
                atexit.register(cls._close_atexit)
                cls._atexit_registered = True
            return cls._cached_event_log

    @classmethod
    def log_once_runner_fallback_engaged(cls, *, workflow_id: str, writer_id: str) -> None:
        """Log a single INFO the first time activity-side emission engages.

        The log is per-process; subsequent emissions from the same process are
        silent. This is the normal path for every activity-side usage emission
        (co-located or split deployment alike) — INFO level, one line, so
        operators can see the writer_id in the worker logs without log spam at
        high activity throughput.
        """
        if cls._fallback_logged:
            return
        with cls._lock:
            if cls._fallback_logged:
                return
            cls._fallback_logged = True
        log.info(
            f"Activity-side usage event emission engaged "
            f"(workflow_id={workflow_id}, writer_id={writer_id}). "
            "Activities always emit through the per-process activity event log, by design: "
            "activity emissions must never land in the workflow's replay-rebuilt buffer "
            "(replay determinism), whether the activity runs co-located with the workflow "
            "router or on a separate worker pool."
        )

    @classmethod
    def reset_for_tests(cls) -> None:
        """Reset cache state. For test fixtures only — never call from production code.

        Closes any cached event log, clears the writer_id, and resets the one-shot
        log flag so subsequent tests observe a fresh process-like state. The
        atexit registration flag is intentionally left alone — the registration
        is process-global and the handler is a no-op once the cache is cleared.
        """
        if cls._cached_event_log is not None:
            try:
                cls._cached_event_log.close()
            except OSError:
                pass
        cls._cached_event_log = None
        cls._writer_id = None
        cls._fallback_logged = False

    @classmethod
    def _close_atexit(cls) -> None:
        """Best-effort close of the cached event log at interpreter shutdown."""
        if cls._cached_event_log is None:
            return
        try:
            cls._cached_event_log.close()
        except OSError:
            # Interpreter shutdown — file handles may already be torn down. Drop quietly.
            pass
