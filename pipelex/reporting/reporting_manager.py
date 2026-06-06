from datetime import datetime, timezone
from typing import NamedTuple

from typing_extensions import override

from pipelex import log
from pipelex.base_exceptions import PipelexConfigError
from pipelex.cogt.extract.extract_job import ExtractJob
from pipelex.cogt.img_gen.img_gen_job import ImgGenJob
from pipelex.cogt.inference.inference_job_abstract import InferenceJobAbstract
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.search.search_job import SearchJob
from pipelex.config import get_config
from pipelex.graph.graph_context import GraphContext
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.reporting.reporting_types import AnyTokensUsage
from pipelex.system.exceptions import MissingDependencyError
from pipelex.tracing.activity_event_log import ActivityEventLogCache
from pipelex.tracing.event_log_protocol import EventLogProtocol
from pipelex.tracing.trace_events import UsageReportEvent

try:
    from botocore.exceptions import ClientError as _BotoClientError  # type: ignore[import-untyped]
except ImportError:
    _BotoClientError = None  # type: ignore[assignment, misc]


class _EventLogContext(NamedTuple):
    """Per-workflow/run event log state. Private to ReportingManager."""

    event_log: EventLogProtocol
    workflow_id: str
    pipeline_run_id: str


class ReportingManager(ReportingProtocol):
    def __init__(self):
        # Per-context event log state, keyed by graph_context.lookup_key.
        # Each concurrent workflow/run gets its own isolated context.
        self._event_log_contexts: dict[str, _EventLogContext] = {}

    ############################################################
    # Event log configuration
    ############################################################

    @override
    def set_event_log(
        self,
        context_key: str,
        event_log: EventLogProtocol,
        workflow_id: str,
        pipeline_run_id: str,
    ) -> None:
        """Configure event log for a specific workflow/run context.

        Args:
            context_key: Unique key for this context (graph_context.lookup_key).
            event_log: The event log backend for emitting UsageReportEvents.
            workflow_id: Temporal workflow ID or "direct".
            pipeline_run_id: Pipeline run ID for event correlation.
        """
        self._event_log_contexts[context_key] = _EventLogContext(
            event_log=event_log,
            workflow_id=workflow_id,
            pipeline_run_id=pipeline_run_id,
        )

    @override
    def clear_event_log(self, context_key: str) -> None:
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

        self._emit_usage_event(llm_job, llm_tokens_usage)

    def _report_img_gen_job(self, img_gen_job: ImgGenJob):
        img_gen_tokens_usage = img_gen_job.job_report.img_gen_tokens_usage

        if not img_gen_tokens_usage:
            log.warning("ImgGen job has no img_gen_tokens_usage")
            return

        self._emit_usage_event(img_gen_job, img_gen_tokens_usage)

    def _report_extract_job(self, extract_job: ExtractJob):
        extract_tokens_usage = extract_job.job_report.extract_tokens_usage

        if not extract_tokens_usage:
            log.warning("Extract job has no extract_tokens_usage")
            return

        self._emit_usage_event(extract_job, extract_tokens_usage)

    def _report_search_job(self, search_job: SearchJob):
        search_tokens_usage = search_job.job_report.search_tokens_usage

        if not search_tokens_usage:
            log.warning("Search job has no search_tokens_usage")
            return

        self._emit_usage_event(search_job, search_tokens_usage)

    def _emit_usage_event(self, inference_job: InferenceJobAbstract, tokens_usage: AnyTokensUsage) -> None:
        """Emit a UsageReportEvent for this job.

        Fast path: when set_event_log was registered for this graph context's
        lookup_key (router process or direct mode), emit through the cached
        per-context event log.

        Fallback: when context lookup misses (runner process — set_event_log
        was never called here), emit through the per-process activity event
        log so the event still lands in the same backend partition as the
        rest of the run. See _emit_usage_event_runner_fallback for details.
        """
        graph_context = inference_job.job_metadata.graph_context
        if graph_context is None:
            return

        # Gate cost emission on emit_usage_events BEFORE the context lookup, so both the fast path
        # (_emit_via_registered_context) and the runner fallback are guarded by the same check. This
        # keeps correctness from resting on the cross-file invariant "a context is registered (via
        # set_event_log) only when costs are on": _event_log_contexts is a process-global singleton
        # and clear_event_log is best-effort in finally blocks, so a leaked context from a prior
        # costs-enabled run could otherwise let a later graph-only run (emit_usage_events=False) emit
        # usage events through the fast path on a colliding lookup_key (reused pipeline_run_id /
        # workflow_id).
        if not graph_context.emit_usage_events:
            return

        context = self._event_log_contexts.get(graph_context.lookup_key)
        if context is not None:
            self._emit_via_registered_context(context, graph_context, tokens_usage)
            return

        self._emit_usage_event_runner_fallback(
            inference_job=inference_job,
            tokens_usage=tokens_usage,
            graph_context=graph_context,
        )

    @staticmethod
    def _emit_via_registered_context(
        context: _EventLogContext,
        graph_context: GraphContext,
        tokens_usage: AnyTokensUsage,
    ) -> None:
        """Fast-path emit through a context registered via set_event_log."""
        node_id = graph_context.parent_node_id or "unknown"
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
        context.event_log.emit(event)

    def _emit_usage_event_runner_fallback(
        self,
        inference_job: InferenceJobAbstract,
        tokens_usage: AnyTokensUsage,
        graph_context: GraphContext,
    ) -> None:
        """Emit through a per-process activity event log when no context was registered.

        On the runner, ``set_event_log`` was never called — the workflow only
        registered a context on the router process. We fall back to a
        process-local event log built from ``tracing_config``, stamped with a
        stable per-process writer_id of the form ``act_{pid}_{uuid8}``.

        Documented over-counting risk (R2): retried activities re-emit a fresh
        event at sequence N+1 instead of overwriting the original at N, so the
        same usage may be counted twice if the activity is retried by Temporal.
        Suppression of retried-emit duplicates is a separate, harder problem
        (deferred follow-up).

        Specific exceptions caught and dropped with WARNING:
        - ``OSError``: NDJSON dir unwritable, file system errors.
        - ``MissingDependencyError``: ``boto3`` missing for the DynamoDB backend.
        - ``PipelexConfigError``: factory misconfigured.
        - ``botocore.exceptions.ClientError`` (when boto3 is installed):
            DynamoDB throttle / auth fail at PutItem time.
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

        workflow_id = graph_context.tracer_key or graph_context.graph_id
        node_id = graph_context.parent_node_id or "unknown"

        ActivityEventLogCache.warn_once_runner_fallback_engaged(workflow_id=workflow_id, writer_id=process_event_log.writer_id)

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

        emit_exceptions: tuple[type[BaseException], ...] = (OSError,)
        if _BotoClientError is not None:
            emit_exceptions = (*emit_exceptions, _BotoClientError)

        try:
            process_event_log.emit(event)
        except emit_exceptions as exc:
            log.warning(f"Runner-side usage event emit failed; dropping: {exc}")

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
