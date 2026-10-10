from datetime import datetime

from pydantic import BaseModel, Field
from typing_extensions import override

from pipelex.cogt.inference.inference_job_abstract import InferenceJobAbstract
from pipelex.cogt.judgment.judgment_models import JudgmentPrompt, JudgmentQuestion
from pipelex.cogt.judgment.judgment_report import JudgmentTokensUsage
from pipelex.cogt.judgment.judgment_setting import JudgmentSetting
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec


class JudgmentJobParams(BaseModel):
    judgment_setting: JudgmentSetting


class JudgmentJobReport(BaseModel):
    judgment_tokens_usage: JudgmentTokensUsage | None = None


class JudgmentJob(InferenceJobAbstract):
    """One prompt, a map of questions over it, and the outcomes they get.

    The shape is batch-first because batching is the backends' whole economy: the spike measured
    three questions over one evidence at 506 input tokens against 1138 for the same three sent
    separately. A caller with one question sends a batch of one; a contract that could not express
    the batch would have to be broken to gain it later.

    The question keys are the caller's own, and they are what the outcomes come back under. A backend
    may show them to its model or not: the one that sends a question's name echoes it on its answer.

    The evidence is the rendered prompt with the images and documents it presents, ordered as its
    tokens number them, exactly as an image or a document reaches an LLM. Whether the model reads them
    is its own capability, which the worker checks before the backend is called.
    """

    prompt: JudgmentPrompt
    questions: dict[str, JudgmentQuestion] = Field(min_length=1)
    job_params: JudgmentJobParams
    job_report: JudgmentJobReport = JudgmentJobReport()

    @override
    def validate_before_execution(self):
        pass

    def judgment_job_before_start(self, *, inference_model: InferenceModelSpec):
        self.job_metadata.started_at = datetime.now()

        self.job_report = JudgmentJobReport()
        self.job_report.judgment_tokens_usage = JudgmentTokensUsage(
            job_metadata=self.job_metadata,
            inference_model_name=inference_model.name,
            unit_costs=inference_model.costs,
            inference_model_id=inference_model.model_id,
            nb_tokens_by_category={},
        )

    def judgment_job_after_complete(self):
        self.job_metadata.completed_at = datetime.now()
