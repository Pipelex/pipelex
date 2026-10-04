"""A judgment worker that answers whatever it is told to, and the job and model spec it is tested with."""

from typing_extensions import override

from pipelex.cogt.document.prompt_document import PromptDocument
from pipelex.cogt.exceptions import CogtError
from pipelex.cogt.image.prompt_image import PromptImage
from pipelex.cogt.judgment.judgment_job import JudgmentJob
from pipelex.cogt.judgment.judgment_job_factory import JudgmentJobFactory
from pipelex.cogt.judgment.judgment_models import JudgmentAnswer, JudgmentQuestion
from pipelex.cogt.judgment.judgment_setting import JudgmentSetting
from pipelex.cogt.judgment.judgment_worker_abstract import JudgmentWorkerAbstract
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.usage.cost_category import CostCategory
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.system.job_metadata import JobMetadata, RunMetadata


class FakeJudgmentWorker(JudgmentWorkerAbstract):
    """A worker that answers whatever it was told to, including the wrong thing, and records whether it was reached."""

    def __init__(
        self,
        inference_model: InferenceModelSpec,
        *,
        answers: dict[str, JudgmentAnswer] | None = None,
        raises: CogtError | None = None,
        reporting_delegate: ReportingProtocol | None = None,
    ) -> None:
        JudgmentWorkerAbstract.__init__(self, inference_model, reporting_delegate=reporting_delegate)
        self._answers = answers or {}
        self._raises = raises
        self.was_called = False

    @override
    async def _judge(self, judgment_job: JudgmentJob) -> dict[str, JudgmentAnswer]:
        self.was_called = True
        if self._raises is not None:
            raise self._raises
        return self._answers


def make_fake_judgment_job(
    questions: dict[str, JudgmentQuestion],
    *,
    images: dict[str, list[PromptImage]] | None = None,
    documents: dict[str, list[PromptDocument]] | None = None,
) -> JudgmentJob:
    return JudgmentJobFactory.make_judgment_job(
        state={"message": "the roof is on fire"},
        images=images,
        documents=documents,
        questions=questions,
        judgment_setting=JudgmentSetting(model="fake-judgment-handle"),
        job_metadata=JobMetadata(run_metadata=RunMetadata(storage_scope="test/scope", read_scope=None, user_id="u", pipeline_run_id="run_judgment")),
    )


def make_fake_judgment_model(*, inputs: list[str] | None = None, max_prompt_images: int | None = None) -> InferenceModelSpec:
    """A judgment model spec reading `inputs`, text alone when none are given."""
    return InferenceModelSpec(
        backend_name="fake_backend",
        name="fake-judgment-handle",
        sdk="fake_judgment_sdk",
        model_type=ModelType.JUDGMENT,
        model_id="fake-judgment-1.0",
        inputs=inputs or ["text"],
        outputs=["judgments"],
        costs={CostCategory.INPUT: 0.042, CostCategory.OUTPUT: 0},
        thinking_mode=ThinkingMode.NONE,
        max_tokens=None,
        max_prompt_images=max_prompt_images,
    )
