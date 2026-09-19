"""The judgment worker's template method: what it stamps, what it checks, and when it reports.

The guards here are the reason a backend cannot quietly answer the wrong thing. Each one is
mutation-tested in the sense the repo means: break the guard in ``judgment_worker_abstract`` and
exactly one of these goes red.
"""

import pytest
from typing_extensions import override

from pipelex.cogt.exceptions import CogtError, JudgmentAnswerMismatchError
from pipelex.cogt.inference.inference_job_abstract import InferenceJobAbstract
from pipelex.cogt.judgment.judgment_job import JudgmentJob
from pipelex.cogt.judgment.judgment_job_factory import JudgmentJobFactory
from pipelex.cogt.judgment.judgment_models import (
    ChoiceAnswer,
    ChoiceQuestion,
    JudgmentAnswer,
    JudgmentQuestion,
    RatingAnswer,
    RatingQuestion,
    YesNoAnswer,
    YesNoQuestion,
)
from pipelex.cogt.judgment.judgment_setting import JudgmentSetting
from pipelex.cogt.judgment.judgment_worker_abstract import JudgmentWorkerAbstract
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.usage.cost_category import CostCategory
from pipelex.reporting.reporting_protocol import ReportingNoOp, ReportingProtocol
from pipelex.system.job_metadata import JobCategory, JobMetadata, RunMetadata, UnitJobId
from tests.unit.pipelex.cogt.judgment.test_data import JudgmentTestCases


class _FakeJudgmentWorker(JudgmentWorkerAbstract):
    """A worker that answers whatever it was told to, including the wrong thing."""

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

    @override
    async def _judge(self, judgment_job: JudgmentJob) -> dict[str, JudgmentAnswer]:
        if self._raises is not None:
            raise self._raises
        return self._answers


class _RecordingDelegate(ReportingNoOp):
    """A reporting delegate that keeps what it was handed, so the `finally` can be asserted on."""

    def __init__(self) -> None:
        self.reported: list[InferenceJobAbstract] = []

    @override
    def report_inference_job(self, inference_job: InferenceJobAbstract) -> None:
        self.reported.append(inference_job)


@pytest.mark.asyncio
class TestJudgmentWorkerContract:
    def _job(self, questions: dict[str, JudgmentQuestion]) -> JudgmentJob:
        return JudgmentJobFactory.make_judgment_job(
            state={"message": "the roof is on fire"},
            questions=questions,
            judgment_setting=JudgmentSetting(model="fake-judgment-handle"),
            job_metadata=JobMetadata(run_metadata=RunMetadata(storage_scope="test/scope", user_id="u", pipeline_run_id="run_judgment")),
        )

    def _model(self) -> InferenceModelSpec:
        return InferenceModelSpec(
            backend_name="fake_backend",
            name="fake-judgment-handle",
            sdk="fake_judgment_sdk",
            model_type=ModelType.JUDGMENT,
            model_id="fake-judgment-1.0",
            inputs=["text"],
            outputs=["judgments"],
            costs={CostCategory.INPUT: 0.042, CostCategory.OUTPUT: 0},
            thinking_mode=ThinkingMode.NONE,
            max_tokens=None,
            max_prompt_images=None,
        )

    async def test_it_answers_every_question_and_stamps_the_job(self) -> None:
        job = self._job(JudgmentTestCases.THREE_QUESTIONS)
        worker = _FakeJudgmentWorker(self._model(), answers=JudgmentTestCases.THREE_ANSWERS)

        answers = await worker.judge(job)

        assert set(answers) == set(JudgmentTestCases.THREE_QUESTIONS)
        assert job.job_metadata.job_category == JobCategory.JUDGMENT_JOB
        assert job.job_metadata.unit_job_id == UnitJobId.JUDGMENT_ANSWER
        assert job.job_metadata.started_at is not None
        assert job.job_metadata.completed_at is not None

    async def test_it_refuses_an_answer_to_a_question_nobody_asked(self) -> None:
        job = self._job({"is_urgent": YesNoQuestion(instructions="Is it urgent?")})
        worker = _FakeJudgmentWorker(
            self._model(),
            answers={"is_urgent": YesNoAnswer(probability=0.9), "is_spam": YesNoAnswer(probability=0.1)},
        )

        with pytest.raises(JudgmentAnswerMismatchError) as exc_info:
            await worker.judge(job)

        assert "is_spam" in str(exc_info.value)

    async def test_it_refuses_a_dropped_answer(self) -> None:
        job = self._job(JudgmentTestCases.THREE_QUESTIONS)
        worker = _FakeJudgmentWorker(self._model(), answers={"is_urgent": YesNoAnswer(probability=0.9)})

        with pytest.raises(JudgmentAnswerMismatchError) as exc_info:
            await worker.judge(job)

        assert "severity" in str(exc_info.value)

    async def test_it_refuses_an_answer_of_the_wrong_kind(self) -> None:
        job = self._job({"severity": RatingQuestion(instructions="How severe?", levels=["mild", "bad", "critical"])})
        worker = _FakeJudgmentWorker(self._model(), answers={"severity": ChoiceAnswer(choice="mild")})

        with pytest.raises(JudgmentAnswerMismatchError) as exc_info:
            await worker.judge(job)

        assert "severity" in str(exc_info.value)
        assert "rating" in str(exc_info.value)

    @pytest.mark.parametrize(
        ("answer", "named"),
        [
            pytest.param(ChoiceAnswer(choice="storm"), "storm", id="choice"),
            pytest.param(ChoiceAnswer(choice="fire", probabilities={"fire": 0.7, "storm": 0.3}), "storm", id="choice_distribution"),
        ],
    )
    async def test_it_refuses_an_option_the_question_does_not_offer(self, answer: ChoiceAnswer, named: str) -> None:
        job = self._job({"topic": ChoiceQuestion(instructions="Which topic?", options={"fire": None, "flood": "water damage"})})
        worker = _FakeJudgmentWorker(self._model(), answers={"topic": answer})

        with pytest.raises(JudgmentAnswerMismatchError) as exc_info:
            await worker.judge(job)

        assert "topic" in str(exc_info.value)
        assert named in str(exc_info.value)

    @pytest.mark.parametrize(
        ("answer", "named"),
        [
            pytest.param(RatingAnswer(level=3), "3", id="level_one_past_the_top"),
            pytest.param(RatingAnswer(level=1, probabilities={0: 0.2, 1: 0.5, 3: 0.3}), "3", id="level_distribution"),
            pytest.param(RatingAnswer(level=1, probabilities={-1: 0.2, 1: 0.8}), "-1", id="negative_level_distribution"),
        ],
    )
    async def test_it_refuses_a_level_beyond_the_scale(self, answer: RatingAnswer, named: str) -> None:
        job = self._job({"severity": RatingQuestion(instructions="How severe?", levels=["mild", "bad", "critical"])})
        worker = _FakeJudgmentWorker(self._model(), answers={"severity": answer})

        with pytest.raises(JudgmentAnswerMismatchError) as exc_info:
            await worker.judge(job)

        assert "severity" in str(exc_info.value)
        assert f"[{named}]" in str(exc_info.value)

    async def test_it_accepts_the_top_level_and_a_full_distribution(self) -> None:
        job = self._job(
            {
                "severity": RatingQuestion(instructions="How severe?", levels=["mild", "bad", "critical"]),
                "topic": ChoiceQuestion(instructions="Which topic?", options={"fire": None, "flood": "water damage"}),
            }
        )
        worker = _FakeJudgmentWorker(
            self._model(),
            answers={
                "severity": RatingAnswer(level=2, probabilities={0: 0.1, 1: 0.2, 2: 0.7}),
                "topic": ChoiceAnswer(choice="flood", probabilities={"fire": 0.4, "flood": 0.6}),
            },
        )

        answers = await worker.judge(job)

        assert set(answers) == {"severity", "topic"}

    async def test_it_reports_on_the_way_out_even_when_the_answers_are_rejected(self) -> None:
        """A rejected answer set was still paid for: the provider answered before the guard ran."""
        job = self._job({"is_urgent": YesNoQuestion(instructions="Is it urgent?")})
        delegate = _RecordingDelegate()
        worker = _FakeJudgmentWorker(
            self._model(),
            answers={"something_else": YesNoAnswer(probability=0.9)},
            reporting_delegate=delegate,
        )

        with pytest.raises(JudgmentAnswerMismatchError):
            await worker.judge(job)

        assert delegate.reported == [job]
        assert job.job_metadata.completed_at is not None

    async def test_it_reports_on_the_happy_path_too(self) -> None:
        job = self._job({"is_urgent": YesNoQuestion(instructions="Is it urgent?")})
        delegate = _RecordingDelegate()
        worker = _FakeJudgmentWorker(self._model(), answers={"is_urgent": YesNoAnswer(probability=0.9)}, reporting_delegate=delegate)

        await worker.judge(job)

        assert delegate.reported == [job]

    async def test_it_names_the_model_and_the_backend_on_a_provider_failure(self) -> None:
        job = self._job({"is_urgent": YesNoQuestion(instructions="Is it urgent?")})
        worker = _FakeJudgmentWorker(self._model(), raises=CogtError("the provider said no"))

        with pytest.raises(CogtError) as exc_info:
            await worker.judge(job)

        assert exc_info.value.model_handle == "fake-judgment-handle"
        assert exc_info.value.backend_name == "fake_backend"

    async def test_a_choice_answer_carries_the_option_it_names(self) -> None:
        job = self._job({"topic": ChoiceQuestion(instructions="Which topic?", options={"fire": None, "flood": "water damage"})})
        worker = _FakeJudgmentWorker(self._model(), answers={"topic": ChoiceAnswer(choice="fire", confidence=0.8)})

        answers = await worker.judge(job)

        answer = answers["topic"]
        assert isinstance(answer, ChoiceAnswer)
        assert answer.choice == "fire"

    async def test_a_rating_answer_carries_its_level(self) -> None:
        job = self._job({"severity": RatingQuestion(instructions="How severe?", levels=["mild", "bad", "critical"])})
        worker = _FakeJudgmentWorker(self._model(), answers={"severity": RatingAnswer(level=2, position=1.8)})

        answers = await worker.judge(job)

        answer = answers["severity"]
        assert isinstance(answer, RatingAnswer)
        assert answer.level == 2
