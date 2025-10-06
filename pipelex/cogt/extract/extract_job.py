from datetime import datetime

from typing_extensions import override

from pipelex.cogt.extract.extract_input import ExtractInput
from pipelex.cogt.extract.extract_job_components import ExtractJobConfig, ExtractJobParams, ExtractJobReport
from pipelex.cogt.inference.inference_job_abstract import InferenceJobAbstract


class ExtractJob(InferenceJobAbstract):
    extract_input: ExtractInput
    job_params: ExtractJobParams
    job_config: ExtractJobConfig
    job_report: ExtractJobReport = ExtractJobReport()

    @override
    def validate_before_execution(self):
        pass

    def extract_job_before_start(self):
        # Reset metadata
        self.job_metadata.started_at = datetime.now()

        # Reset outputs
        self.job_report = ExtractJobReport()

    def extract_job_after_complete(self):
        self.job_metadata.completed_at = datetime.now()
