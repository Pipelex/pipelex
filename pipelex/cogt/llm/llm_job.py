from datetime import datetime

from typing_extensions import override

from pipelex.cogt.inference.inference_job_abstract import InferenceJobAbstract
from pipelex.cogt.llm.llm_job_components import LLMJobConfig, LLMJobParams, LLMJobReport
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_report import LLMTokensUsage
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec


class LLMJob(InferenceJobAbstract):
    llm_prompt: LLMPrompt
    job_params: LLMJobParams
    job_config: LLMJobConfig
    job_report: LLMJobReport = LLMJobReport()

    @property
    def params_desc(self) -> str:
        return f"temp={self.job_params.temperature}, max_tokens={self.job_params.max_tokens}"

    @override
    def validate_before_execution(self):
        self.llm_prompt.validate_before_execution()

    def llm_job_before_start(self, inference_model: InferenceModelSpec):
        # Reset metadata
        self.job_metadata.started_at = datetime.now()

        # Reset outputs
        self.job_report = LLMJobReport()

        # Reset info
        self.job_report.llm_tokens_usage = LLMTokensUsage(
            job_metadata=self.job_metadata,
            inference_model_name=inference_model.name,
            unit_costs=inference_model.costs,
            inference_model_id=inference_model.model_id,
            nb_tokens_by_category={},
        )

    def llm_job_after_complete(self):
        self.job_metadata.completed_at = datetime.now()
