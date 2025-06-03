from typing import Dict, List, Optional

from pydantic import Field, RootModel
from typing_extensions import override

from pipelex import log
from pipelex.cogt.config_cogt import CogtReportConfig
from pipelex.cogt.exceptions import InferenceReportManagerError
from pipelex.cogt.inference.cost_registry import CostRegistry
from pipelex.cogt.inference.inference_job_abstract import InferenceJobAbstract
from pipelex.cogt.inference.inference_report_delegate import InferenceReportDelegate
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_report import LLMTokenCostReport, LLMTokensUsage
from pipelex.pipeline.pipeline_models import SpecialPipelineId
from pipelex.tools.misc.file_utils import ensure_path, get_incremental_file_path

LLMUsageRegistryRoot = List[LLMTokensUsage]


class UsageRegistry(RootModel[LLMUsageRegistryRoot]):
    root: LLMUsageRegistryRoot = Field(default_factory=list)

    def get_current_tokens_usage(self) -> LLMUsageRegistryRoot:
        return self.root

    def add_tokens_usage(self, llm_tokens_usage: LLMTokensUsage):
        self.root.append(llm_tokens_usage)


class InferenceReportManager(InferenceReportDelegate):
    def __init__(self, report_config: CogtReportConfig):
        self._usage_registries: Dict[str, UsageRegistry] = {}
        self._report_config = report_config

    ############################################################
    # Manager lifecycle
    ############################################################

    def setup(self):
        self._usage_registries.clear()
        self._usage_registries[SpecialPipelineId.UNTITLED] = UsageRegistry()

    def teardown(self):
        self._usage_registries.clear()

    ############################################################
    # Private methods
    ############################################################

    def _get_registry(self, pipeline_run_id: str) -> UsageRegistry:
        if pipeline_run_id not in self._usage_registries:
            raise InferenceReportManagerError(f"Registry for pipeline '{pipeline_run_id}' does not exist")
        return self._usage_registries[pipeline_run_id]

    def _report_llm_job(self, llm_job: LLMJob):
        llm_tokens_usage = llm_job.job_report.llm_tokens_usage

        if not llm_tokens_usage:
            log.warning("LLM job has no llm_tokens_usage")
            return

        llm_token_cost_report: Optional[LLMTokenCostReport] = None

        if self._report_config.is_log_costs_to_console:
            llm_token_cost_report = CostRegistry.complete_cost_report(llm_tokens_usage=llm_tokens_usage)

        pipeline_run_id = llm_job.job_metadata.pipeline_run_id
        self._get_registry(pipeline_run_id).add_tokens_usage(llm_tokens_usage)

        if self._report_config.is_log_costs_to_console:
            log.verbose(llm_token_cost_report, title="Token Cost report")

    ############################################################
    # InferenceReportDelegate
    ############################################################

    @override
    def open_registry(self, pipeline_run_id: str):
        if pipeline_run_id in self._usage_registries:
            raise InferenceReportManagerError(f"Registry for pipeline '{pipeline_run_id}' already exists")
        self._usage_registries[pipeline_run_id] = UsageRegistry()

    @override
    def report_inference_job(self, inference_job: InferenceJobAbstract):
        log.info(f"Inference job '{inference_job.job_metadata.unit_job_id}' completed in {inference_job.job_metadata.duration:.2f} seconds")
        if not isinstance(inference_job, LLMJob):
            # InferenceReportManager does not support reporting for other types of inference jobs yet
            # TODO: add support for other types of inference jobs
            return
        llm_job: LLMJob = inference_job
        self._report_llm_job(llm_job=llm_job)

    @override
    def generate_report(self, pipeline_run_id: Optional[str] = None):
        pipeline_run_id = pipeline_run_id or SpecialPipelineId.UNTITLED
        cost_report_file_path: Optional[str] = None
        if self._report_config.is_generate_cost_report_file_enabled:
            ensure_path(self._report_config.cost_report_dir_path)
            cost_report_file_path = get_incremental_file_path(
                base_path=self._report_config.cost_report_dir_path,
                base_name=self._report_config.cost_report_base_name,
                extension=self._report_config.cost_report_extension,
            )

        registry = self._get_registry(pipeline_run_id)
        CostRegistry.generate_report(
            pipeline_run_id=pipeline_run_id,
            llm_tokens_usages=registry.get_current_tokens_usage(),
            unit_scale=self._report_config.cost_report_unit_scale,
            cost_report_file_path=cost_report_file_path,
        )

    @override
    def close_registry(self, pipeline_run_id: str):
        self._usage_registries.pop(pipeline_run_id)
