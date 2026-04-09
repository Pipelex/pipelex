from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from pydantic import Field, RootModel
from typing_extensions import override

from pipelex import log
from pipelex.cogt.exceptions import ReportingManagerError
from pipelex.cogt.extract.extract_job import ExtractJob
from pipelex.cogt.img_gen.img_gen_job import ImgGenJob
from pipelex.cogt.inference.inference_job_abstract import InferenceJobAbstract
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_report import LLMTokensUsage
from pipelex.cogt.search.search_job import SearchJob
from pipelex.cogt.usage.cost_registry import CostRegistry
from pipelex.config import get_config
from pipelex.pipeline.pipeline_models import SpecialPipelineId
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.reporting.reporting_types import AnyTokensUsage, TokensUsage
from pipelex.tools.misc.file_utils import ensure_path, get_incremental_file_path
from pipelex.tools.typing.pydantic_utils import empty_list_factory_of
from pipelex.tracing.event_log_protocol import EventLogProtocol
from pipelex.tracing.trace_events import UsageReportEvent

if TYPE_CHECKING:
    from pathlib import Path


@dataclass
class _EventLogContext:
    """Per-workflow/run event log state. Private to ReportingManager."""

    event_log: EventLogProtocol
    workflow_id: str
    pipeline_run_id: str


UsageRegistryRoot = list[TokensUsage]


class UsageRegistry(RootModel[UsageRegistryRoot]):
    root: UsageRegistryRoot = Field(default_factory=empty_list_factory_of(LLMTokensUsage))

    def get_current_tokens_usage(self) -> UsageRegistryRoot:
        return self.root

    def add_tokens_usage(self, tokens_usage: TokensUsage):
        self.root.append(tokens_usage)


class ReportingManager(ReportingProtocol):
    def __init__(self):
        self._reporting_config = get_config().pipelex.reporting_config
        self._usage_registries: dict[str, UsageRegistry] = {}
        # Per-context event log state, keyed by graph_context.lookup_key.
        # Each concurrent workflow/run gets its own isolated context.
        self._event_log_contexts: dict[str, _EventLogContext] = {}

    ############################################################
    # Event log configuration
    ############################################################

    def set_event_log(
        self,
        context_key: str,
        event_log: "EventLogProtocol",
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

    def clear_event_log(self, context_key: str) -> None:
        """Remove event log configuration for a completed workflow/run."""
        self._event_log_contexts.pop(context_key, None)

    ############################################################
    # Manager lifecycle
    ############################################################

    @override
    def setup(self):
        self._usage_registries.clear()
        self._usage_registries[SpecialPipelineId.UNTITLED] = UsageRegistry()

    @override
    def teardown(self):
        self._usage_registries.clear()
        self._event_log_contexts.clear()

    ############################################################
    # Private methods
    ############################################################

    def _get_registry(self, pipeline_run_id: str) -> UsageRegistry:
        if pipeline_run_id not in self._usage_registries:
            # Auto-create registry for unknown pipeline IDs. This happens when
            # Activities report inference jobs on a Temporal worker where
            # open_registry() was never called (it runs on the API process).

            # TODO: replace with proper distributed reporting system
            self._usage_registries[pipeline_run_id] = UsageRegistry()
        return self._usage_registries[pipeline_run_id]

    def _report_llm_job(self, llm_job: LLMJob):
        llm_tokens_usage = llm_job.job_report.llm_tokens_usage

        if not llm_tokens_usage:
            log.warning("LLM job has no llm_tokens_usage")
            return

        pipeline_run_id = llm_job.job_metadata.pipeline_run_id
        self._get_registry(pipeline_run_id).add_tokens_usage(llm_tokens_usage)
        self._emit_usage_event(llm_job, llm_tokens_usage)

        if self._reporting_config.is_log_costs_to_console:
            llm_token_cost_report = CostRegistry.complete_cost_report(tokens_usage=llm_tokens_usage)
            log.verbose(llm_token_cost_report, title="Token Cost report")

    def _report_img_gen_job(self, img_gen_job: ImgGenJob):
        img_gen_tokens_usage = img_gen_job.job_report.img_gen_tokens_usage

        if not img_gen_tokens_usage:
            log.warning("ImgGen job has no img_gen_tokens_usage")
            return

        pipeline_run_id = img_gen_job.job_metadata.pipeline_run_id
        self._get_registry(pipeline_run_id).add_tokens_usage(img_gen_tokens_usage)
        self._emit_usage_event(img_gen_job, img_gen_tokens_usage)

        if self._reporting_config.is_log_costs_to_console:
            img_gen_token_cost_report = CostRegistry.complete_cost_report(tokens_usage=img_gen_tokens_usage)
            log.verbose(img_gen_token_cost_report, title="Token Cost report")

    def _report_extract_job(self, extract_job: ExtractJob):
        extract_tokens_usage = extract_job.job_report.extract_tokens_usage

        if not extract_tokens_usage:
            log.warning("Extract job has no extract_tokens_usage")
            return

        pipeline_run_id = extract_job.job_metadata.pipeline_run_id
        self._get_registry(pipeline_run_id).add_tokens_usage(extract_tokens_usage)
        self._emit_usage_event(extract_job, extract_tokens_usage)

        if self._reporting_config.is_log_costs_to_console:
            extract_token_cost_report = CostRegistry.complete_cost_report(tokens_usage=extract_tokens_usage)
            log.verbose(extract_token_cost_report, title="Token Cost report")

    def _report_search_job(self, search_job: SearchJob):
        search_tokens_usage = search_job.job_report.search_tokens_usage

        if not search_tokens_usage:
            log.warning("Search job has no search_tokens_usage")
            return

        pipeline_run_id = search_job.job_metadata.pipeline_run_id
        self._get_registry(pipeline_run_id).add_tokens_usage(search_tokens_usage)
        self._emit_usage_event(search_job, search_tokens_usage)

        if self._reporting_config.is_log_costs_to_console:
            search_token_cost_report = CostRegistry.complete_cost_report(tokens_usage=search_tokens_usage)
            log.verbose(search_token_cost_report, title="Token Cost report")

    ############################################################
    # ReportingProtocol
    ############################################################

    @override
    def open_registry(self, pipeline_run_id: str):
        if pipeline_run_id in self._usage_registries:
            msg = f"Registry for pipeline '{pipeline_run_id}' already exists"
            raise ReportingManagerError(msg)
        self._usage_registries[pipeline_run_id] = UsageRegistry()

    def inject_tokens_usages(self, pipeline_run_id: str, tokens_usages: Sequence[AnyTokensUsage]) -> None:
        """Inject externally-collected token usage records into a pipeline's registry.

        Used after assembling usage data from distributed trace events, so that
        generate_report() can produce a complete cost report across all workers.

        Args:
            pipeline_run_id: The pipeline run to add usage data to.
            tokens_usages: Token usage records to inject.
        """
        registry = self._get_registry(pipeline_run_id)
        for tokens_usage in tokens_usages:
            registry.add_tokens_usage(tokens_usage)

    def _emit_usage_event(self, inference_job: InferenceJobAbstract, tokens_usage: AnyTokensUsage) -> None:
        """Emit a UsageReportEvent if event log is configured for this job's context."""
        graph_context = inference_job.job_metadata.graph_context
        if graph_context is None:
            return

        context = self._event_log_contexts.get(graph_context.lookup_key)
        if context is None:
            return

        # Determine the node_id from graph context (the pipe that dispatched this inference)
        node_id: str = "unknown"
        if graph_context.parent_node_id is not None:
            node_id = graph_context.parent_node_id

        seq = context.event_log.next_sequence()

        event = UsageReportEvent(
            pipeline_run_id=context.pipeline_run_id,
            workflow_id=context.workflow_id,
            timestamp=datetime.now(timezone.utc),
            sequence=seq,
            node_id=node_id,
            tokens_usage=tokens_usage,
        )
        context.event_log.emit(event)

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

    @override
    def generate_report(self, pipeline_run_id: str | None = None):
        cost_report_file_path: Path | None = None
        if self._reporting_config.is_generate_cost_report_file_enabled:
            ensure_path(self._reporting_config.cost_report_dir_path)
            cost_report_file_path = get_incremental_file_path(
                base_path=self._reporting_config.cost_report_dir_path,
                base_name=self._reporting_config.cost_report_base_name,
                extension=self._reporting_config.cost_report_extension,
            )

        registries_to_process: dict[str, UsageRegistry] = {}
        if pipeline_run_id:
            registries_to_process = {pipeline_run_id: self._get_registry(pipeline_run_id)}
        else:
            registries_to_process = self._usage_registries

        for run_id, registry in registries_to_process.items():
            CostRegistry.generate_report(
                pipeline_run_id=run_id,
                tokens_usages=registry.get_current_tokens_usage(),
                unit_scale=self._reporting_config.cost_report_unit_scale,
                cost_report_file_path=cost_report_file_path,
            )

    @override
    def close_registry(self, pipeline_run_id: str):
        self._usage_registries.pop(pipeline_run_id)
