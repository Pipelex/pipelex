"""A PipeJudge question the template sandbox refuses is located on the question's own field, in either form of the step."""

import pytest
from mthds.protocol.problem.registry import CoreCode
from pytest_mock import MockerFixture

from pipelex.base_exceptions import PipelexError
from pipelex.cogt.content_generation.content_generator import ContentGenerator
from pipelex.errors.problem import ProblemView
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from tests.integration.pipelex.pipes.operator.pipe_judge.test_data import PipeJudgeLoadTestData, PipeJudgeSeveralQuestionsTestData

# A question that reads a private name its own source spells, which the sandbox refuses whatever the run's data.
_REFUSED_QUESTION = "Is {{ message['_owner'] }} urgent?"


@pytest.mark.asyncio(loop_scope="class")
class TestPipeJudgeTemplateRefusalLocation:
    @pytest.mark.parametrize(
        ("bundle", "expected_field"),
        [
            pytest.param(
                PipeJudgeLoadTestData.bundle(question=_REFUSED_QUESTION, step_fields=f'model = "{PipeJudgeLoadTestData.JUDGMENT_MODEL}"'),
                "question",
                id="one_question",
            ),
            pytest.param(
                PipeJudgeSeveralQuestionsTestData.bundle(
                    questions={
                        **PipeJudgeSeveralQuestionsTestData.QUESTIONS,
                        "team": f'question = "{_REFUSED_QUESTION}"\noptions = {{ billing = "Charges", technical = "Errors" }}',
                    }
                ),
                "questions.team.question",
                id="several_questions",
            ),
        ],
    )
    async def test_a_refused_question_is_located_on_its_field(self, bundle: str, expected_field: str, mocker: MockerFixture) -> None:
        asked = mocker.patch.object(ContentGenerator, "make_judgment_answers")

        with pytest.raises(PipelexError) as exc_info:
            await PipelexMTHDSProtocol().execute(mthds_contents=[bundle], pipe_code="judge_it", inputs={"message": "The site is down"})

        caller = exc_info.value.to_problem(view=ProblemView.CALLER)

        assert caller.code == CoreCode.SECURITY_TEMPLATE_REFUSED, caller.to_wire()
        assert caller.location is not None
        assert caller.location.as_wire() == {"pipe": "judge_it", "path": ["judge_it"], "field": expected_field}
        asked.assert_not_called()
