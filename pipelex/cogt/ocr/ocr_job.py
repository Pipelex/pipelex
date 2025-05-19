# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from datetime import datetime

from typing_extensions import override

from pipelex.cogt.inference.inference_job_abstract import InferenceJobAbstract
from pipelex.cogt.ocr.ocr_engine import OcrEngine
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

    def ocr_job_before_start(self, ocr_engine: OcrEngine):
        # Reset metadata
        self.job_metadata.started_at = datetime.now()

        # Reset outputs
        self.job_report = OcrJobReport()

    def ocr_job_after_complete(self):
        self.job_metadata.completed_at = datetime.now()
