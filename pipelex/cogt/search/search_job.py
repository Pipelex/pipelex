from datetime import datetime

from pydantic import BaseModel
from typing_extensions import override

from pipelex.cogt.inference.inference_job_abstract import InferenceJobAbstract
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.search.search_report import SearchTokensUsage
from pipelex.cogt.search.search_setting import SearchSetting


class SearchJobParams(BaseModel):
    search_setting: SearchSetting
    include_domains: list[str] | None = None
    exclude_domains: list[str] | None = None
    from_date: str | None = None
    to_date: str | None = None


class SearchJobReport(BaseModel):
    search_tokens_usage: SearchTokensUsage | None = None


class SearchJob(InferenceJobAbstract):
    query: str
    job_params: SearchJobParams
    job_report: SearchJobReport = SearchJobReport()

    @override
    def validate_before_execution(self):
        pass

    def search_job_before_start(self, inference_model: InferenceModelSpec):
        self.job_metadata.started_at = datetime.now()

        self.job_report = SearchJobReport()
        self.job_report.search_tokens_usage = SearchTokensUsage(
            job_metadata=self.job_metadata,
            inference_model_name=inference_model.name,
            unit_costs=inference_model.costs,
            inference_model_id=inference_model.model_id,
            nb_tokens_by_category={},
        )

    def search_job_after_complete(self):
        self.job_metadata.completed_at = datetime.now()
