from datetime import datetime

from typing_extensions import override

from pipelex.cogt.extract.extract_input import ExtractInput
from pipelex.cogt.extract.extract_job_components import ExtractJobConfig, ExtractJobParams, ExtractJobReport
from pipelex.cogt.extract.extract_report import ExtractTokensUsage
from pipelex.cogt.inference.inference_job_abstract import InferenceJobAbstract
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec


class ExtractJob(InferenceJobAbstract):
    extract_input: ExtractInput
    job_params: ExtractJobParams
    job_config: ExtractJobConfig
    job_report: ExtractJobReport = ExtractJobReport()

    @override
    def validate_before_execution(self):
        pass

    def extract_job_before_start(self, inference_model: InferenceModelSpec):
        # Reset metadata
        self.job_metadata.started_at = datetime.now()

        # Reset outputs
        self.job_report = ExtractJobReport()
        self.job_report.extract_tokens_usage = ExtractTokensUsage(
            job_metadata=self.job_metadata,
            inference_model_name=inference_model.name,
            unit_costs=inference_model.costs,
            inference_model_id=inference_model.model_id,
            nb_tokens_by_category={},
        )

    def extract_job_after_complete(self):
        self.job_metadata.completed_at = datetime.now()
