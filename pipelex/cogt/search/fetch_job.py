from datetime import datetime

from pydantic import BaseModel
from typing_extensions import override

from pipelex.cogt.inference.inference_job_abstract import InferenceJobAbstract
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.search.fetch_report import FetchTokensUsage


class FetchJobReport(BaseModel):
    fetch_tokens_usage: FetchTokensUsage | None = None


class FetchJob(InferenceJobAbstract):
    job_report: FetchJobReport = FetchJobReport()

    @override
    def validate_before_execution(self):
        pass

    def fetch_job_before_start(self, inference_model: InferenceModelSpec):
        self.job_metadata.started_at = datetime.now()

        self.job_report = FetchJobReport()
        self.job_report.fetch_tokens_usage = FetchTokensUsage(
            job_metadata=self.job_metadata,
            inference_model_name=inference_model.name,
            unit_costs=inference_model.costs,
            inference_model_id=inference_model.model_id,
            nb_tokens_by_category={},
        )

    def fetch_job_after_complete(self):
        self.job_metadata.completed_at = datetime.now()
