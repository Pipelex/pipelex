from datetime import UTC, datetime
from typing import NamedTuple, cast

from typing_extensions import override

from pipelex import log
from pipelex.base_exceptions import PipelexConfigError
from pipelex.cogt.extract.extract_job import ExtractJob
from pipelex.cogt.img_gen.img_gen_job import ImgGenJob
from pipelex.cogt.inference.inference_job_abstract import InferenceJobAbstract
from pipelex.cogt.judgment.judgment_job import JudgmentJob
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.search.search_job import SearchJob
from pipelex.config import get_config
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.reporting.reporting_types import AnyTokensUsage
from pipelex.runtime_hub import get_event_log_override, is_in_isolated_execution
from pipelex.system.exceptions import MissingDependencyError
from pipelex.system.trace_context import TraceContext
from pipelex.tools.log.error_fields import error_fields
from pipelex.tracing.activity_event_log import ActivityEventLogCache
from pipelex.tracing.event_log_protocol import EventLogProtocol
from pipelex.tracing.trace_events import UNATTRIBUTED_NODE_ID, UsageReportEvent

# DynamoDB PutItem failures come in two sibling botocore base classes (neither subclasses the other):
# ClientError (service-side throttle / auth) and BotoCoreError (transport / credential / timeout, e.g.
# EndpointConnectionError, ReadTimeoutError, NoCredentialsError). Both are imported together (present or
# absent together) and join the best-effort emit catch when boto3 is installed — matching s3_storage_provider.
try:
    from botocore.exceptions import BotoCoreError as _BotoCoreError  # type: ignore[import-untyped]
    from botocore.exceptions import ClientError as _BotoClientError  # type: ignore[import-untyped]
except ImportError:
    _BotoCoreError = None  # type: ignore[assignment, misc]
    _BotoClientError = None  # type: ignore[assignment, misc]


# Infra-level failures an event-log backend can raise from emit(). Usage/cost reporting is a side
# concern: by the time report_inference_job runs, the inference has already succeeded (and been
# billed), so a transient event-log write failure must never propagate and turn a successful
# inference into a failed pipeline. Every emit path — the scoped override, the registered-context
# fast path and the runner fallback — drops these with a WARNING. OSError covers the NDJSON backend
# (dir/file write errors); ClientError (service-side throttle / auth) and BotoCoreError (transport /
# credential / timeout, e.g. EndpointConnectionError, ReadTimeoutError, NoCredentialsError) cover the
# DynamoDB backend when boto3 is installed. ClientError and BotoCoreError are sibling botocore base classes
# (neither subclasses the other), so both must be listed.
# cast: botocore is untyped, so the imported classes are Unknown; we know they are BaseException types.
# Single assignment (no reassignment) so the uppercase constant satisfies reportConstantRedefinition.
_EMIT_BEST_EFFORT_EXCEPTIONS: tuple[type[BaseException], ...] = (
    (OSError, cast("type[BaseException]", _BotoClientError), cast("type[BaseException]", _BotoCoreError))
    if _BotoClientError is not None and _BotoCoreError is not None
    else (OSError,)
)


class _EventLogContext(NamedTuple):
    """Per-workflow/run event log state. Private to ReportingManager.

    It holds no workflow id: a usage event names its execution, its attempt and its lineage from the trace context it was
    reported under, whose chain the workflow's tracer opened, so the event's chain is always the one its context states.
    """

    event_log: EventLogProtocol
    pipeline_run_id: str


class ReportingManager(ReportingProtocol):
    def __init__(self):
        # Per-context event log state, keyed by trace_context.lookup_key.
        # Each concurrent workflow/run gets its own isolated context.
        self._event_log_contexts: dict[str, _EventLogContext] = {}

    ############################################################
    # Event log configuration
    ############################################################

    @override
    def set_event_log(
        self,
        *,
        context_key: str,
        event_log: EventLogProtocol,
        pipeline_run_id: str,
    ) -> None:
        """Configure event log for a specific workflow/run context.

        Args:
            context_key: Unique key for this context (trace_context.lookup_key).
            event_log: The event log backend for emitting UsageReportEvents.
            pipeline_run_id: Pipeline run ID for event correlation.
        """
        # The silent overwrite-on-existing-key below is intentional and load-bearing.
        # Shared contract: worker-local state keyed by a deterministic per-run id must be
        # self-healing on open/set, because a leaked entry from a prior interrupted
        # execution remains possible (deadlock-detector thread abandonment skips finally
        # entirely; worker kill between set and clear). The same idiom exists in
        # LibraryManager.open_fresh_library and GraphTracerManager.open_tracer (both
        # explicit, WARNING); here the bare dict assignment is the healing mechanism.
        # Adding "context already exists -> raise" collision detection would reintroduce
        # the eviction-poison class on the cost path (pre-M1 open_tracer did exactly that).
        self._event_log_contexts[context_key] = _EventLogContext(
            event_log=event_log,
            pipeline_run_id=pipeline_run_id,
        )

    @override
    def clear_event_log(self, *, context_key: str) -> None:
        """Remove event log configuration for a completed workflow/run."""
        self._event_log_contexts.pop(context_key, None)

    ############################################################
    # Manager lifecycle
    ############################################################

    @override
    def setup(self):
        self._event_log_contexts.clear()

    @override
    def teardown(self):
        self._event_log_contexts.clear()

    ############################################################
    # Private methods
    ############################################################

    def _report_llm_job(self, llm_job: LLMJob):
        llm_tokens_usage = llm_job.job_report.llm_tokens_usage

        if not llm_tokens_usage:
            self._warn_of_missing_usage(inference_job=llm_job)
            return

        self._emit_usage_event(llm_job, tokens_usage=llm_tokens_usage)

    def _report_img_gen_job(self, img_gen_job: ImgGenJob):
        img_gen_tokens_usage = img_gen_job.job_report.img_gen_tokens_usage

        if not img_gen_tokens_usage:
            self._warn_of_missing_usage(inference_job=img_gen_job)
            return

        self._emit_usage_event(img_gen_job, tokens_usage=img_gen_tokens_usage)

    def _report_extract_job(self, extract_job: ExtractJob):
        extract_tokens_usage = extract_job.job_report.extract_tokens_usage

        if not extract_tokens_usage:
            self._warn_of_missing_usage(inference_job=extract_job)
            return

        self._emit_usage_event(extract_job, tokens_usage=extract_tokens_usage)

    def _report_search_job(self, search_job: SearchJob):
        search_tokens_usage = search_job.job_report.search_tokens_usage

        if not search_tokens_usage:
            self._warn_of_missing_usage(inference_job=search_job)
            return

        self._emit_usage_event(search_job, tokens_usage=search_tokens_usage)

    def _report_judgment_job(self, *, judgment_job: JudgmentJob):
        judgment_tokens_usage = judgment_job.job_report.judgment_tokens_usage

        if not judgment_tokens_usage:
            self._warn_of_missing_usage(inference_job=judgment_job)
            return

        self._emit_usage_event(judgment_job, tokens_usage=judgment_tokens_usage)

    @classmethod
    def _warn_of_missing_usage(cls, *, inference_job: InferenceJobAbstract) -> None:
        """Warn that an inference job reported no usage: one event whichever family the job is of, its class a field."""
        log.warning("An inference job reported no usage", fields={"inference_job_type": type(inference_job).__name__})

    def _emit_usage_event(self, inference_job: InferenceJobAbstract, *, tokens_usage: AnyTokensUsage) -> None:
        """Emit a UsageReportEvent for this job.

        Scoped path, ahead of every other: when a scoped event log is set
        (``runtime_hub.scoped_event_log``), the event goes into it and nowhere else —
        not into a registered context, not into the runner fallback — whether or not
        the code runs in an isolated sub-execution, and whether or not tracing is
        enabled, since a set override implies tracing-enabled, as it does for the
        tracer setup in ``pipeline_run_setup`` and for ``assemble_tracing``. This is
        what lets code running a leaf inside an isolated sub-execution capture the
        usage that leaf emits and return it with its result, for a backend such as
        Mistral Workflows that has no shared store for the run to read usage back from.
        It is safe inside an isolated sub-execution, unlike the registered fast path
        below: the override is a ContextVar, so it reaches only code running in the
        context that set it and the tasks started from it, and an isolated
        sub-execution sees one only when its own code scoped it.

        Fast path: when set_event_log was registered for this trace context's
        lookup_key (workflow-thread or direct mode), emit through the cached
        per-context event log.

        Isolated-execution path: an emission from inside an isolated sub-execution
        (reported by the boot orchestrator's ``is_in_isolated_execution`` probe — a
        Temporal activity, even when co-located with the workflow worker) NEVER takes
        the fast path. The registered context there is the workflow's in-sandbox
        BufferingEventLog, and an isolated sub-execution does not re-execute on replay —
        a cross-thread write into that buffer makes the workflow's buffer content depend
        on whether the sub-execution actually ran, breaking replay determinism (audit
        finding H1). Such emissions must behave identically whether co-located or remote:
        per-process fallback.

        Fallback: when context lookup misses (runner process — set_event_log
        was never called here) or the emission comes from an isolated sub-execution,
        emit through the per-process activity event log so the event still lands in
        the same backend partition as the rest of the run. See
        _emit_usage_event_runner_fallback for details.
        """
        trace_context = inference_job.job_metadata.trace_context
        if trace_context is None:
            return

        # Gate cost emission on emit_usage_events BEFORE any routing, so the scoped override, the fast
        # path (a registered context) and the runner fallback are all guarded by the same check. This
        # keeps correctness from resting on the cross-file invariant "a context is registered (via
        # set_event_log) only when costs are on": _event_log_contexts is a process-global singleton
        # and clear_event_log is best-effort in finally blocks, so a leaked context from a prior
        # costs-enabled run could otherwise let a later graph-only run (emit_usage_events=False) emit
        # usage events through the fast path on a colliding lookup_key (reused pipeline_run_id /
        # workflow_id).
        if not trace_context.emit_usage_events:
            return

        # A scoped override (see hub.scoped_event_log) is the transport of whatever runs in its scope and
        # implies tracing-enabled: the event goes into it and nowhere else, ahead of the registered contexts
        # and the runner fallback, inside an isolated sub-execution too (see the docstring). The run is the
        # job's own, as on the runner fallback, since no registration names one here.
        event_log_override = get_event_log_override()
        if event_log_override is not None:
            self._emit_into_event_log(
                event_log=event_log_override,
                pipeline_run_id=inference_job.job_metadata.run_metadata.pipeline_run_id,
                trace_context=trace_context,
                tokens_usage=tokens_usage,
            )
            return

        if not is_in_isolated_execution():
            context = self._event_log_contexts.get(trace_context.lookup_key)
            if context is not None:
                self._emit_into_event_log(
                    event_log=context.event_log,
                    pipeline_run_id=context.pipeline_run_id,
                    trace_context=trace_context,
                    tokens_usage=tokens_usage,
                )
                return

        self._emit_usage_event_runner_fallback(
            inference_job=inference_job,
            tokens_usage=tokens_usage,
            trace_context=trace_context,
        )

    @staticmethod
    def _emit_into_event_log(
        *,
        event_log: EventLogProtocol,
        pipeline_run_id: str,
        trace_context: TraceContext,
        tokens_usage: AnyTokensUsage,
    ) -> None:
        """Build the usage event a trace context states and emit it into ``event_log``, best-effort.

        Shared by every emit path — the scoped override, a context registered via set_event_log and the
        runner fallback — which differ only in the event log they write into and the run they name. The
        execution, its attempt and its lineage are the trace context's on every path: a usage event belongs
        to the attempt of the workflow that ran it, which a new attempt of that workflow supersedes.
        """
        event = UsageReportEvent(
            pipeline_run_id=pipeline_run_id,
            workflow_id=trace_context.own_attempt.execution,
            attempt=trace_context.own_attempt.attempt,
            lineage=trace_context.lineage,
            path=trace_context.parent_path,
            writer_id=event_log.writer_id,
            mode=trace_context.run_mode,
            timestamp=datetime.now(UTC),
            sequence=event_log.next_sequence(),
            node_id=trace_context.parent_node_id or UNATTRIBUTED_NODE_ID,
            tokens_usage=tokens_usage,
        )
        ReportingManager._emit_best_effort(event_log=event_log, event=event)

    @staticmethod
    def _emit_best_effort(*, event_log: EventLogProtocol, event: UsageReportEvent) -> None:
        """Emit a usage event, dropping infra-level backend failures with a WARNING.

        Shared by every emit path (the scoped override, the registered-context fast path and the runner fallback).
        report_inference_job runs synchronously after the inference has already succeeded, so an
        event-log write failure must not propagate and fail the pipeline. We catch the specific
        infra exception classes the backends raise at emit() time (see
        ``_EMIT_BEST_EFFORT_EXCEPTIONS``) and drop the event. Other exceptions propagate.
        """
        try:
            event_log.emit(event)
        except _EMIT_BEST_EFFORT_EXCEPTIONS as exc:
            log.warning("A usage event could not be written to the event log and was dropped", fields=error_fields(exc=exc))

    def _emit_usage_event_runner_fallback(
        self,
        inference_job: InferenceJobAbstract,
        *,
        tokens_usage: AnyTokensUsage,
        trace_context: TraceContext,
    ) -> None:
        """Emit through the per-process activity event log.

        This is the universal path for activity-side usage emissions (audit finding
        H1): every emission from inside a Temporal activity routes here, co-located
        or remote alike, so the workflow's in-sandbox buffer stays a pure function
        of inline execution — unless the activity's own code set a scoped event log,
        which takes the emission instead. It also covers the original fallback case — a runner
        process where ``set_event_log`` was never called. The event log is
        process-local, built from ``tracing_config``, stamped with a stable
        per-process writer_id of the form ``act_{pid}_{uuid8}``.

        Documented over-counting risk (R2): retried activities re-emit a fresh
        event at sequence N+1 instead of overwriting the original at N, so the
        same usage may be counted twice if the activity is retried by Temporal.
        Suppression of retried-emit duplicates is a separate, harder problem
        (deferred follow-up).

        Construction-time failures (lazy event-log build) caught and dropped with WARNING:
        - ``OSError``: NDJSON dir unwritable, file system errors.
        - ``MissingDependencyError``: ``boto3`` missing for the DynamoDB backend.
        - ``PipelexConfigError``: factory misconfigured.
        The emit() itself is delegated to ``_emit_best_effort``, which drops the
        backend's emit-time infra failures (see ``_EMIT_BEST_EFFORT_EXCEPTIONS``).
        Other exceptions propagate.
        """
        tracing_config = get_config().runtime.tracing
        if not tracing_config.is_enabled:
            return

        try:
            process_event_log = ActivityEventLogCache.get_or_create(tracing_config)
        except (OSError, MissingDependencyError, PipelexConfigError) as exc:
            log.warning("The activity event log could not be built and a usage event was dropped", fields=error_fields(exc=exc))
            return

        if process_event_log is None:
            return

        # The line names the run's tracer key beside the execution: the execution is `direct` for every run in direct
        # mode and under the kernel, so it alone would not say which run engaged the fallback.
        ActivityEventLogCache.log_once_runner_fallback_engaged(
            workflow_id=trace_context.own_attempt.execution, tracer_key=trace_context.lookup_key, writer_id=process_event_log.writer_id
        )

        self._emit_into_event_log(
            event_log=process_event_log,
            pipeline_run_id=inference_job.job_metadata.run_metadata.pipeline_run_id,
            trace_context=trace_context,
            tokens_usage=tokens_usage,
        )

    @override
    def report_inference_job(self, inference_job: InferenceJobAbstract):
        if isinstance(inference_job, LLMJob):
            self._report_llm_job(llm_job=inference_job)
        elif isinstance(inference_job, ImgGenJob):
            self._report_img_gen_job(img_gen_job=inference_job)
        elif isinstance(inference_job, ExtractJob):
            self._report_extract_job(extract_job=inference_job)
        elif isinstance(inference_job, SearchJob):
            self._report_search_job(search_job=inference_job)
        elif isinstance(inference_job, JudgmentJob):
            self._report_judgment_job(judgment_job=inference_job)
        else:
            log.error(
                "The usage of an inference job of an unknown type was lost",
                fields={"inference_job_type": type(inference_job).__name__},
            )
