"""A PipeJudge asking several questions runs as one judgment and fills its output's structure, a refusal included."""

from typing import Any

import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.content_generation.assignment_models import JudgmentAssignment
from pipelex.cogt.content_generation.content_generator import ContentGenerator
from pipelex.cogt.judgment.judgment_models import (
    ChoiceAnswer,
    ChoiceQuestion,
    JudgmentOutcome,
    JudgmentRefusal,
    RatingAnswer,
    RatingLevel,
    RatingQuestion,
    YesNoAnswer,
    YesNoCriteria,
    YesNoQuestion,
)
from pipelex.core.stuffs.choice_content import ChoiceContent
from pipelex.core.stuffs.rating_content import RatingContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.core.stuffs.yes_no_content import YesNoContent
from pipelex.pipe_operators.judge.pipe_judge import PipeJudge
from pipelex.pipeline.exceptions import PipelineExecutionError
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.system.pipe_run_mode import PipeRunMode
from tests.integration.pipelex.pipes.operator.pipe_judge.test_data import PipeJudgeSeveralQuestionsTestData

_ANSWERS: dict[str, JudgmentOutcome] = {
    "urgent": YesNoAnswer(probability=0.6),
    "team": ChoiceAnswer(choice="technical", confidence=0.8),
    "severity": RatingAnswer(level=1, confidence=0.7),
}


async def _run(*, pipe_run_mode: PipeRunMode) -> Any:
    response = await PipelexMTHDSProtocol(pipe_run_mode=pipe_run_mode).execute(
        mthds_contents=[PipeJudgeSeveralQuestionsTestData.bundle()],
        pipe_code=PipeJudgeSeveralQuestionsTestData.PIPE_CODE,
        inputs={"message": TextContent(text=PipeJudgeSeveralQuestionsTestData.MESSAGE)},
    )
    assert response.pipe_output is not None
    return response.pipe_output.main_stuff.content


@pytest.mark.asyncio(loop_scope="class")
class TestPipeJudgeSeveralQuestionsRun:
    async def test_every_verdict_fills_its_field_and_a_refusal_leaves_an_optional_one_absent(self, mocker: MockerFixture) -> None:
        """One job asks every question; the optional field a refusal leaves absent is recorded in the execution data."""
        asked_jobs: list[JudgmentAssignment] = []

        def _answer(*, judgment_assignment: JudgmentAssignment) -> dict[str, JudgmentOutcome]:
            asked_jobs.append(judgment_assignment)
            return {**_ANSWERS, "severity": JudgmentRefusal()}

        mocker.patch.object(ContentGenerator, "make_judgment_answers", side_effect=_answer)
        execution_data_spy = mocker.spy(PipeJudge, "_register_execution_data")

        triage = await _run(pipe_run_mode=PipeRunMode.LIVE)

        (job,) = asked_jobs
        assert list(job.questions) == ["urgent", "team", "severity"]
        assert job.questions["urgent"] == YesNoQuestion(
            instructions="Is the message urgent?", criteria=YesNoCriteria(yes="It cannot wait", no="It can wait")
        )
        assert job.questions["team"] == ChoiceQuestion(
            instructions="Which team handles it?", options={"billing": "Charges and invoices", "technical": "Errors and outages"}
        )
        assert job.questions["severity"] == RatingQuestion(
            instructions="How severe is the reported issue?", levels=[RatingLevel(label="Minor"), RatingLevel(label="Major")]
        )
        assert job.prompt.text == f"<message>\n{PipeJudgeSeveralQuestionsTestData.MESSAGE}\n</message>"
        # The threshold of 0.7 turns the model's 0.6 into a no, and `Team` refines `Choice`, so its field holds a choice.
        assert triage.urgent == YesNoContent(yes_no=False, probability=0.6)
        assert isinstance(triage.team, ChoiceContent)
        assert triage.team.choice == "technical"
        assert triage.severity is None
        execution_data = execution_data_spy.call_args.kwargs["execution_data"]
        assert execution_data["rendered_prompt"] == job.prompt.text
        assert execution_data["resolved_model"] == job.judgment_setting.model
        assert execution_data["questions"] == {
            "urgent": {
                "rendered_question": "Is the message urgent?",
                "judgment_kind": "yes_no",
                "threshold": 0.7,
                "threshold_applied": True,
                "outcome": {"kind": "yes_no", "probability": 0.6},
            },
            "team": {
                "rendered_question": "Which team handles it?",
                "judgment_kind": "choice",
                "outcome": {"kind": "choice", "choice": "technical", "confidence": 0.8},
            },
            "severity": {
                "rendered_question": "How severe is the reported issue?",
                "judgment_kind": "rating",
                "outcome": {"kind": "refusal"},
            },
        }

    async def test_a_refusal_behind_a_required_field_fails_the_step_naming_the_question(self, mocker: MockerFixture) -> None:
        mocker.patch.object(ContentGenerator, "make_judgment_answers", return_value={**_ANSWERS, "team": JudgmentRefusal()})

        with pytest.raises(PipelineExecutionError) as exc_info:
            await _run(pipe_run_mode=PipeRunMode.LIVE)

        assert "declined to answer the question 'team', and its output field cannot be left absent" in str(exc_info.value)

    async def test_a_dry_run_answers_every_question(self) -> None:
        triage = await _run(pipe_run_mode=PipeRunMode.DRY)

        assert isinstance(triage.urgent, YesNoContent)
        assert triage.team.choice == "billing"
        assert triage.severity == RatingContent(level=0, label="Minor")
