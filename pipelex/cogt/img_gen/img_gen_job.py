from datetime import datetime

from typing_extensions import override

from pipelex.cogt.img_gen.img_gen_job_components import ImgGenJobConfig, ImgGenJobParams, ImgGenJobReport
from pipelex.cogt.img_gen.img_gen_prompt import ImgGenPrompt
from pipelex.cogt.img_gen.img_gen_report import ImgGenTokensUsage
from pipelex.cogt.inference.inference_job_abstract import InferenceJobAbstract
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec


class ImgGenJob(InferenceJobAbstract):
    img_gen_prompt: ImgGenPrompt
    job_params: ImgGenJobParams
    job_config: ImgGenJobConfig
    job_report: ImgGenJobReport

    @override
    def validate_before_execution(self):
        self.img_gen_prompt.validate_before_execution()

    def img_gen_job_before_start(self, inference_model: InferenceModelSpec):
        # Reset metadata
        self.job_metadata.started_at = datetime.now()

        # Reset outputs
        self.job_report = ImgGenJobReport()
        self.job_report.img_gen_tokens_usage = ImgGenTokensUsage(
            job_metadata=self.job_metadata,
            inference_model_name=inference_model.name,
            unit_costs=inference_model.costs,
            inference_model_id=inference_model.model_id,
            nb_tokens_by_category={},
        )

    def img_gen_job_after_complete(self):
        self.job_metadata.completed_at = datetime.now()
