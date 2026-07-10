from datetime import datetime, timezone
from typing import NamedTuple, cast

from typing_extensions import override

from pipelex import log
from pipelex.base_exceptions import PipelexConfigError
from pipelex.cogt.extract.extract_job import ExtractJob
from pipelex.cogt.img_gen.img_gen_job import ImgGenJob
from pipelex.cogt.inference.inference_job_abstract import InferenceJobAbstract
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.search.search_job import SearchJob
from pipelex.config import get_config
from pipelex.graph.trace_context import TraceContext
from pipelex.hub import is_in_isolated_execution
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.reporting.reporting_types import AnyTokensUsage
from pipelex.system.exceptions import MissingDependencyError
from pipelex.tracing.activity_event_log import ActivityEventLogCache
from pipelex.tracing.event_log_protocol import EventLogProtocol
from pipelex.tracing.trace_events import UsageReportEvent

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
# inference into a failed pipeline. Both emit paths — the registered-context fast path and the
# runner fallback — drop these with a WARNING. OSError covers the NDJSON backend (dir/file write
# errors); ClientError (service-side throttle / auth) and BotoCoreError (transport / credential /
# timeout, e.g. EndpointConnectionError, ReadTimeoutError, NoCredentialsError) cover the DynamoDB
# backend when boto3 is installed. ClientError and BotoCoreError are sibling botocore base classes
# (neither subclasses the other), so both must be listed.
# cast: botocore is untyped, so the imported classes are Unknown; we know they are BaseException types.
# Single assignment (no reassignment) so the uppercase constant satisfies reportConstantRedefinition.
_EMIT_BEST_EFFORT_EXCEPTIONS: tuple[type[BaseException], ...] = (
    (OSError, cast("type[BaseException]", _BotoClientError), cast("type[BaseException]", _BotoCoreError))
    if _BotoClientError is not None and _BotoCoreError is not None
    else (OSError,)
)


class _EventLogContext(NamedTuple):
    """Per-workflow/run event log state. Private to ReportingManager."""

    event_log: EventLogProtocol
    workflow_id: str
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
        workflow_id: str,
        pipeline_run_id: str,
    ) -> None:
        """Configure event log for a specific workflow/run context.

        Args:
            context_key: Unique key for this context (trace_context.lookup_key).
            event_log: The event log backend for emitting UsageReportEvents.
            workflow_id: Run-scoped execution identity stamped into events
                (Temporal run ID, or "direct" outside Temporal).
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
            workflow_id=workflow_id,
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
            log.warning("LLM job has no llm_tokens_usage")
            return

        self._emit_usage_event(llm_job, tokens_usage=llm_tokens_usage)

    def _report_img_gen_job(self, img_gen_job: ImgGenJob):
        img_gen_tokens_usage = img_gen_job.job_report.img_gen_tokens_usage

        if not img_gen_tokens_usage:
            log.warning("ImgGen job has no img_gen_tokens_usage")
            return

        self._emit_usage_event(img_gen_job, tokens_usage=img_gen_tokens_usage)

    def _report_extract_job(self, extract_job: ExtractJob):
        extract_tokens_usage = extract_job.job_report.extract_tokens_usage

        if not extract_tokens_usage:
            log.warning("Extract job has no extract_tokens_usage")
            return

        self._emit_usage_event(extract_job, tokens_usage=extract_tokens_usage)

    def _report_search_job(self, search_job: SearchJob):
        search_tokens_usage = search_job.job_report.search_tokens_usage

        if not search_tokens_usage:
            log.warning("Search job has no search_tokens_usage")
            return

        self._emit_usage_event(search_job, tokens_usage=search_tokens_usage)

    def _emit_usage_event(self, inference_job: InferenceJobAbstract, *, tokens_usage: AnyTokensUsage) -> None:
        """Emit a UsageReportEvent for this job.

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

        # Gate cost emission on emit_usage_events BEFORE the context lookup, so both the fast path
        # (_emit_via_registered_context) and the runner fallback are guarded by the same check. This
        # keeps correctness from resting on the cross-file invariant "a context is registered (via
        # set_event_log) only when costs are on": _event_log_contexts is a process-global singleton
        # and clear_event_log is best-effort in finally blocks, so a leaked context from a prior
        # costs-enabled run could otherwise let a later graph-only run (emit_usage_events=False) emit
        # usage events through the fast path on a colliding lookup_key (reused pipeline_run_id /
        # workflow_id).
        if not trace_context.emit_usage_events:
            return

        if not is_in_isolated_execution():
            context = self._event_log_contexts.get(trace_context.lookup_key)
            if context is not None:
                self._emit_via_registered_context(context=context, trace_context=trace_context, tokens_usage=tokens_usage)
                return

        self._emit_usage_event_runner_fallback(
            inference_job=inference_job,
            tokens_usage=tokens_usage,
            trace_context=trace_context,
        )

    @staticmethod
    def _emit_via_registered_context(
        *,
        context: _EventLogContext,
        trace_context: TraceContext,
        tokens_usage: AnyTokensUsage,
    ) -> None:
        """Fast-path emit through a context registered via set_event_log."""
        node_id = trace_context.parent_node_id or "unknown"
        seq = context.event_log.next_sequence()

        event = UsageReportEvent(
            pipeline_run_id=context.pipeline_run_id,
            workflow_id=context.workflow_id,
            writer_id=context.event_log.writer_id,
            timestamp=datetime.now(timezone.utc),
            sequence=seq,
            node_id=node_id,
            tokens_usage=tokens_usage,
        )
        ReportingManager._emit_best_effort(event_log=context.event_log, event=event)

    @staticmethod
    def _emit_best_effort(*, event_log: EventLogProtocol, event: UsageReportEvent) -> None:
        """Emit a usage event, dropping infra-level backend failures with a WARNING.

        Shared by both emit paths (the registered-context fast path and the runner fallback).
        report_inference_job runs synchronously after the inference has already succeeded, so an
        event-log write failure must not propagate and fail the pipeline. We catch the specific
        infra exception classes the backends raise at emit() time (see
        ``_EMIT_BEST_EFFORT_EXCEPTIONS``) and drop the event. Other exceptions propagate.
        """
        try:
            event_log.emit(event)
        except _EMIT_BEST_EFFORT_EXCEPTIONS as exc:
            log.warning(f"Usage event emit failed; dropping: {exc}")

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
        of inline execution. It also covers the original fallback case — a runner
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
        tracing_config = get_config().pipelex.tracing_config
        if not tracing_config.is_enabled:
            return

        try:
            process_event_log = ActivityEventLogCache.get_or_create(tracing_config)
        except (OSError, MissingDependencyError, PipelexConfigError) as exc:
            log.warning(f"Runner-side activity event log construction failed; dropping usage event: {exc}")
            return

        if process_event_log is None:
            return

        workflow_id = trace_context.tracer_key or trace_context.graph_id
        node_id = trace_context.parent_node_id or "unknown"

        ActivityEventLogCache.log_once_runner_fallback_engaged(workflow_id=workflow_id, writer_id=process_event_log.writer_id)

        seq = process_event_log.next_sequence()
        event = UsageReportEvent(
            pipeline_run_id=inference_job.job_metadata.pipeline_run_id,
            workflow_id=workflow_id,
            writer_id=process_event_log.writer_id,
            timestamp=datetime.now(timezone.utc),
            sequence=seq,
            node_id=node_id,
            tokens_usage=tokens_usage,
        )

        self._emit_best_effort(event_log=process_event_log, event=event)

    @override
    def report_inference_job(self, inference_job: InferenceJobAbstract):
        log.verbose(f"Inference job '{inference_job.job_metadata.unit_job_id}' completed in {inference_job.job_metadata.duration:.2f} seconds")
        if isinstance(inference_job, LLMJob):
            self._report_llm_job(llm_job=inference_job)
        elif isinstance(inference_job, ImgGenJob):
            self._report_img_gen_job(img_gen_job=inference_job)
        elif isinstance(inference_job, ExtractJob):
            self._report_extract_job(extract_job=inference_job)
        elif isinstance(inference_job, SearchJob):
            self._report_search_job(search_job=inference_job)
        else:
            log.warning(f"ReportingManager does not support reporting for inference job type: {type(inference_job).__name__}")
