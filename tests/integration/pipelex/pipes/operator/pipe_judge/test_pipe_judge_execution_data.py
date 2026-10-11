import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.content_generation.assignment_models import JudgmentAssignment
from pipelex.cogt.content_generation.content_generator import ContentGenerator
from pipelex.cogt.judgment.judgment_models import ChoiceAnswer, JudgmentOutcome, RatingAnswer, YesNoAnswer
from pipelex.core.stuffs.text_content import TextContent
from pipelex.pipe_operators.judge.pipe_judge import PipeJudge
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.system.pipe_run_mode import PipeRunMode
from tests.integration.pipelex.pipes.operator.pipe_judge.test_data import PipeJudgeLoadTestData, PipeJudgeSeveralQuestionsTestData

_ANSWERS: dict[str, JudgmentOutcome] = {
    "urgent": YesNoAnswer(probability=0.9),
    "team": ChoiceAnswer(choice="technical", confidence=0.8),
    "severity": RatingAnswer(level=1, confidence=0.7),
}


def _answer(*, judgment_assignment: JudgmentAssignment) -> dict[str, JudgmentOutcome]:
    """Answer each question by its name, the single form's one question as a yes/no."""
    return {name: _ANSWERS.get(name, YesNoAnswer(probability=0.9)) for name in judgment_assignment.questions}


@pytest.mark.asyncio(loop_scope="class")
class TestPipeJudgeExecutionData:
    @pytest.mark.parametrize(
        ("topic", "bundle", "expected_kinds"),
        [
            pytest.param(
                "one question",
                PipeJudgeLoadTestData.bundle(step_fields=f'model = "{PipeJudgeLoadTestData.JUDGMENT_MODEL}"'),
                {"": "yes_no"},
                id="one_question",
            ),
            pytest.param(
                "several questions",
                PipeJudgeSeveralQuestionsTestData.bundle(),
                {"urgent": "yes_no", "team": "choice", "severity": "rating"},
                id="several_questions",
            ),
        ],
    )
    async def test_a_question_kind_is_recorded_as_plain_text(
        self,
        mocker: MockerFixture,
        topic: str,  # ruff: ignore[unused-method-argument]
        bundle: str,
        expected_kinds: dict[str, str],
    ) -> None:
        """The kind is stored as a plain string, never as the enum, which a serializer would write out with its class."""
        mocker.patch.object(ContentGenerator, "make_judgment_answers", side_effect=_answer)
        execution_data_spy = mocker.spy(PipeJudge, "_register_execution_data")

        await PipelexMTHDSProtocol(pipe_run_mode=PipeRunMode.LIVE).execute(
            mthds_contents=[bundle],
            pipe_code="judge_it",
            inputs={"message": TextContent(text=PipeJudgeSeveralQuestionsTestData.MESSAGE)},
        )

        execution_data = execution_data_spy.call_args.kwargs["execution_data"]
        recorded_kinds = (
            {name: record["judgment_kind"] for name, record in execution_data["questions"].items()}
            if "questions" in execution_data
            else {"": execution_data["judgment_kind"]}
        )
        assert recorded_kinds == expected_kinds
        assert all(type(recorded_kind) is str for recorded_kind in recorded_kinds.values())
