from datetime import datetime

from typing_extensions import override

from pipelex.cogt.img_gen.img_gen_job_components import ImgGenJobConfig, ImgGenJobParams, ImgGenJobReport
from pipelex.cogt.img_gen.img_gen_prompt import ImgGenPrompt
from pipelex.cogt.inference.inference_job_abstract import InferenceJobAbstract


class ImgGenJob(InferenceJobAbstract):
    img_gen_prompt: ImgGenPrompt
    job_params: ImgGenJobParams
    job_config: ImgGenJobConfig
    job_report: ImgGenJobReport

    @override
    def validate_before_execution(self):
        self.img_gen_prompt.validate_before_execution()

    def img_gen_job_before_start(self):
        # Reset metadata
        self.job_metadata.started_at = datetime.now()

        # Reset outputs
        self.job_report = ImgGenJobReport()

    def img_gen_job_after_complete(self):
        self.job_metadata.completed_at = datetime.now()
