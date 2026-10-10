"""The judgment worker's template method: what it stamps, what it checks, and when it reports.

The guards here are the reason a backend cannot quietly answer the wrong thing. Each one is
mutation-tested in the sense the repo means: break the guard in ``judgment_worker_abstract`` and
exactly one of these goes red.
"""

import pytest
from typing_extensions import override

from pipelex.cogt.exceptions import (
    CogtError,
    JudgmentAnswerMismatchError,
)
from pipelex.cogt.inference.inference_job_abstract import InferenceJobAbstract
from pipelex.cogt.judgment.judgment_models import (
    ChoiceAnswer,
    ChoiceQuestion,
    JudgmentAnswer,
    JudgmentQuestion,
    JudgmentRefusal,
    RatingAnswer,
    RatingQuestion,
    YesNoAnswer,
    YesNoQuestion,
)
from pipelex.reporting.reporting_protocol import ReportingNoOp
from pipelex.system.job_metadata import JobCategory, UnitJobId
from tests.unit.pipelex.cogt.judgment.fake_judgment_worker import FakeJudgmentWorker, make_fake_judgment_job, make_fake_judgment_model
from tests.unit.pipelex.cogt.judgment.test_data import JudgmentTestCases, described_levels


class _RecordingDelegate(ReportingNoOp):
    """A reporting delegate that keeps what it was handed, so the `finally` can be asserted on."""

    def __init__(self) -> None:
        self.reported: list[InferenceJobAbstract] = []

    @override
    def report_inference_job(self, inference_job: InferenceJobAbstract) -> None:
        self.reported.append(inference_job)


@pytest.mark.asyncio
class TestJudgmentWorkerContract:
    async def test_it_answers_every_question_and_stamps_the_job(self) -> None:
        job = make_fake_judgment_job(JudgmentTestCases.THREE_QUESTIONS)
        worker = FakeJudgmentWorker(make_fake_judgment_model(), answers=JudgmentTestCases.THREE_ANSWERS)

        answers = await worker.judge(job)

        assert set(answers) == set(JudgmentTestCases.THREE_QUESTIONS)
        assert job.job_metadata.job_category == JobCategory.JUDGMENT_JOB
        assert job.job_metadata.unit_job_id == UnitJobId.JUDGMENT_ANSWER
        assert job.job_metadata.started_at is not None
        assert job.job_metadata.completed_at is not None

    async def test_it_refuses_an_answer_to_a_question_nobody_asked(self) -> None:
        job = make_fake_judgment_job({"is_urgent": YesNoQuestion(instructions="Is it urgent?")})
        worker = FakeJudgmentWorker(
            make_fake_judgment_model(),
            answers={"is_urgent": YesNoAnswer(probability=0.9), "is_spam": YesNoAnswer(probability=0.1)},
        )

        with pytest.raises(JudgmentAnswerMismatchError) as exc_info:
            await worker.judge(job)

        assert "is_spam" in str(exc_info.value)

    async def test_it_accepts_a_refusal_for_any_question(self) -> None:
        """A refusal is an outcome, not an error: the worker hands it up for the operator's policy to read."""
        job = make_fake_judgment_job(JudgmentTestCases.THREE_QUESTIONS)
        worker = FakeJudgmentWorker(
            make_fake_judgment_model(),
            answers={"is_urgent": JudgmentRefusal(), "topic": JudgmentRefusal(), "severity": JudgmentTestCases.THREE_ANSWERS["severity"]},
        )

        outcomes = await worker.judge(job)

        assert outcomes == {"is_urgent": JudgmentRefusal(), "topic": JudgmentRefusal(), "severity": JudgmentTestCases.THREE_ANSWERS["severity"]}

    async def test_it_refuses_a_refusal_under_a_key_nobody_asked(self) -> None:
        job = make_fake_judgment_job({"is_urgent": YesNoQuestion(instructions="Is it urgent?")})
        worker = FakeJudgmentWorker(make_fake_judgment_model(), answers={"is_urgent": YesNoAnswer(probability=0.9), "is_spam": JudgmentRefusal()})

        with pytest.raises(JudgmentAnswerMismatchError) as exc_info:
            await worker.judge(job)

        assert "unasked ['is_spam']" in str(exc_info.value)

    async def test_it_refuses_a_dropped_answer(self) -> None:
        job = make_fake_judgment_job(JudgmentTestCases.THREE_QUESTIONS)
        worker = FakeJudgmentWorker(make_fake_judgment_model(), answers={"is_urgent": YesNoAnswer(probability=0.9)})

        with pytest.raises(JudgmentAnswerMismatchError) as exc_info:
            await worker.judge(job)

        assert "severity" in str(exc_info.value)

    @pytest.mark.parametrize(
        ("question", "answer", "asked_kind"),
        [
            pytest.param(YesNoQuestion(instructions="Is it severe?"), ChoiceAnswer(choice="mild"), "yes_no", id="yes_no_answered_by_a_choice"),
            pytest.param(
                ChoiceQuestion(instructions="Which severity?", options={"mild": None, "bad": None}),
                RatingAnswer(level=0),
                "choice",
                id="choice_answered_by_a_rating",
            ),
            pytest.param(
                RatingQuestion(instructions="How severe?", levels=described_levels("mild", "bad", "critical")),
                ChoiceAnswer(choice="mild"),
                "rating",
                id="rating_answered_by_a_choice",
            ),
        ],
    )
    async def test_it_refuses_an_answer_of_the_wrong_kind(self, question: JudgmentQuestion, answer: JudgmentAnswer, asked_kind: str) -> None:
        job = make_fake_judgment_job({"severity": question})
        worker = FakeJudgmentWorker(make_fake_judgment_model(), answers={"severity": answer})

        with pytest.raises(JudgmentAnswerMismatchError) as exc_info:
            await worker.judge(job)

        assert "severity" in str(exc_info.value)
        assert f"it asked for '{asked_kind}'" in str(exc_info.value)

    @pytest.mark.parametrize(
        ("answer", "named"),
        [
            pytest.param(ChoiceAnswer(choice="storm"), "storm", id="choice"),
            pytest.param(ChoiceAnswer(choice="fire", probabilities={"fire": 0.7, "storm": 0.3}), "storm", id="choice_distribution"),
        ],
    )
    async def test_it_refuses_an_option_the_question_does_not_offer(self, answer: ChoiceAnswer, named: str) -> None:
        job = make_fake_judgment_job({"topic": ChoiceQuestion(instructions="Which topic?", options={"fire": None, "flood": "water damage"})})
        worker = FakeJudgmentWorker(make_fake_judgment_model(), answers={"topic": answer})

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
        job = make_fake_judgment_job({"severity": RatingQuestion(instructions="How severe?", levels=described_levels("mild", "bad", "critical"))})
        worker = FakeJudgmentWorker(make_fake_judgment_model(), answers={"severity": answer})

        with pytest.raises(JudgmentAnswerMismatchError) as exc_info:
            await worker.judge(job)

        assert "severity" in str(exc_info.value)
        assert f"[{named}]" in str(exc_info.value)

    @pytest.mark.parametrize(
        ("question", "answer", "named"),
        [
            pytest.param(
                ChoiceQuestion(instructions="Which topic?", options={"fire": None, "flood": None}),
                ChoiceAnswer(choice="fire", probabilities={"fire": 1.0000001, "flood": 0.0}),
                "fire",
                id="choice_probability_above_one",
            ),
            pytest.param(
                RatingQuestion(instructions="How severe?", levels=described_levels("mild", "bad", "critical")),
                RatingAnswer(level=1, probabilities={0: -0.1, 1: 1.1}),
                "0",
                id="rating_probability_below_zero",
            ),
            pytest.param(
                RatingQuestion(instructions="How severe?", levels=described_levels("mild", "bad", "critical")),
                RatingAnswer(level=2, position=float("inf")),
                "position",
                id="rating_infinite_position",
            ),
            pytest.param(
                RatingQuestion(instructions="How severe?", levels=described_levels("mild", "bad", "critical")),
                RatingAnswer(level=2, position=2.5),
                "position of 2.5",
                id="rating_position_past_the_last_level",
            ),
        ],
    )
    async def test_it_refuses_a_measure_its_verdict_cannot_hold(self, question: JudgmentQuestion, answer: JudgmentAnswer, named: str) -> None:
        """A probability outside the unit interval or a position off the scale is refused as a mismatch, not left to the verdict's own model."""
        job = make_fake_judgment_job({"verdict": question})
        worker = FakeJudgmentWorker(make_fake_judgment_model(), answers={"verdict": answer})

        with pytest.raises(JudgmentAnswerMismatchError) as exc_info:
            await worker.judge(job)

        assert "verdict" in str(exc_info.value)
        assert named in str(exc_info.value)

    async def test_it_accepts_the_top_level_and_a_full_distribution(self) -> None:
        job = make_fake_judgment_job(
            {
                "severity": RatingQuestion(instructions="How severe?", levels=described_levels("mild", "bad", "critical")),
                "topic": ChoiceQuestion(instructions="Which topic?", options={"fire": None, "flood": "water damage"}),
            }
        )
        worker = FakeJudgmentWorker(
            make_fake_judgment_model(),
            answers={
                "severity": RatingAnswer(level=2, probabilities={0: 0.1, 1: 0.2, 2: 0.7}),
                "topic": ChoiceAnswer(choice="flood", probabilities={"fire": 0.4, "flood": 0.6}),
            },
        )

        answers = await worker.judge(job)

        assert set(answers) == {"severity", "topic"}

    async def test_it_reports_on_the_way_out_even_when_the_answers_are_rejected(self) -> None:
        """A rejected answer set was still paid for: the provider answered before the guard ran."""
        job = make_fake_judgment_job({"is_urgent": YesNoQuestion(instructions="Is it urgent?")})
        delegate = _RecordingDelegate()
        worker = FakeJudgmentWorker(
            make_fake_judgment_model(),
            answers={"something_else": YesNoAnswer(probability=0.9)},
            reporting_delegate=delegate,
        )

        with pytest.raises(JudgmentAnswerMismatchError):
            await worker.judge(job)

        assert delegate.reported == [job]
        assert job.job_metadata.completed_at is not None

    async def test_it_reports_on_the_happy_path_too(self) -> None:
        job = make_fake_judgment_job({"is_urgent": YesNoQuestion(instructions="Is it urgent?")})
        delegate = _RecordingDelegate()
        worker = FakeJudgmentWorker(make_fake_judgment_model(), answers={"is_urgent": YesNoAnswer(probability=0.9)}, reporting_delegate=delegate)

        await worker.judge(job)

        assert delegate.reported == [job]

    async def test_it_names_the_model_and_the_backend_on_a_provider_failure(self) -> None:
        job = make_fake_judgment_job({"is_urgent": YesNoQuestion(instructions="Is it urgent?")})
        worker = FakeJudgmentWorker(make_fake_judgment_model(), raises=CogtError("the provider said no"))

        with pytest.raises(CogtError) as exc_info:
            await worker.judge(job)

        assert exc_info.value.model_handle == "fake-judgment-handle"
        assert exc_info.value.backend_name == "fake_backend"

    async def test_a_choice_answer_carries_the_option_it_names(self) -> None:
        job = make_fake_judgment_job({"topic": ChoiceQuestion(instructions="Which topic?", options={"fire": None, "flood": "water damage"})})
        worker = FakeJudgmentWorker(make_fake_judgment_model(), answers={"topic": ChoiceAnswer(choice="fire", confidence=0.8)})

        answers = await worker.judge(job)

        answer = answers["topic"]
        assert isinstance(answer, ChoiceAnswer)
        assert answer.choice == "fire"

    async def test_a_rating_answer_carries_its_level(self) -> None:
        job = make_fake_judgment_job({"severity": RatingQuestion(instructions="How severe?", levels=described_levels("mild", "bad", "critical"))})
        worker = FakeJudgmentWorker(make_fake_judgment_model(), answers={"severity": RatingAnswer(level=2, position=1.8)})

        answers = await worker.judge(job)

        answer = answers["severity"]
        assert isinstance(answer, RatingAnswer)
        assert answer.level == 2
