from datetime import datetime

from typing_extensions import override

from pipelex.cogt.inference.inference_job_abstract import InferenceJobAbstract
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.ocr.ocr_input import OcrInput
from pipelex.cogt.ocr.ocr_job_components import OcrJobConfig, OcrJobParams, OcrJobReport


class OcrJob(InferenceJobAbstract):
    ocr_input: OcrInput
    job_params: OcrJobParams
    job_config: OcrJobConfig
    job_report: OcrJobReport = OcrJobReport()

    @override
    def validate_before_execution(self):
        pass

    def ocr_job_before_start(self, inference_model: InferenceModelSpec):
        # Reset metadata
        self.job_metadata.started_at = datetime.now()

        # Reset outputs
        self.job_report = OcrJobReport()

    def ocr_job_after_complete(self):
        self.job_metadata.completed_at = datetime.now()
