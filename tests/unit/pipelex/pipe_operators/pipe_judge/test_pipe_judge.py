from typing import Any

import pytest
from pydantic import ValidationError

from pipelex.cogt.judgment.judgment_models import ChoiceQuestion, YesNoQuestion
from pipelex.cogt.templating.template_blueprint import TemplateBlueprint
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.pipes.stuff_spec.stuff_spec import StuffSpec
from pipelex.kernel.prompt_assembly import UserPromptContent
from pipelex.pipe_operators.judge.pipe_judge import PipeJudge, PipeJudgeQuestion
from pipelex.tools.jinja2.template_category import TemplateCategory

_URGENT = PipeJudgeQuestion(judgment_question=YesNoQuestion(instructions="Is it urgent?"), threshold=0.7)
_TEAM = PipeJudgeQuestion(judgment_question=ChoiceQuestion(instructions="Which team handles $topic?", options={"billing": None, "technical": None}))


def _pipe_judge(**question_fields: Any) -> PipeJudge:
    return PipeJudge(
        code="judge_it",
        domain_code="judge_unit",
        description="Judge the evidence",
        output=StuffSpec(concept=ConceptFactory.make_native_concept(NativeConceptCode.YES_NO)),
        judgment_choice=None,
        prompt_content=UserPromptContent(template=TemplateBlueprint(template="$message", category=TemplateCategory.LLM_PROMPT)),
        **question_fields,
    )


class TestPipeJudge:
    @pytest.mark.parametrize(
        ("question_fields", "message_fragment"),
        [
            pytest.param({"question": _URGENT, "questions": {"team": _TEAM}}, "it was given both a single question and several", id="both"),
            pytest.param({}, "it was given none", id="neither"),
            pytest.param({"questions": {}}, "it was given none", id="no_question_among_several"),
        ],
    )
    def test_a_step_asks_one_question_or_several_never_both_nor_none(self, question_fields: dict[str, Any], message_fragment: str):
        with pytest.raises(ValidationError) as exc_info:
            _pipe_judge(**question_fields)
        assert message_fragment in str(exc_info.value)

    @pytest.mark.parametrize(
        ("question_fields", "expected_labels"),
        [
            pytest.param({"question": _URGENT}, ["question"], id="one"),
            pytest.param({"questions": {"urgent": _URGENT, "team": _TEAM}}, ["question 'urgent'", "question 'team'"], id="several"),
        ],
    )
    def test_each_question_is_labelled_for_messages(self, question_fields: dict[str, Any], expected_labels: list[str]):
        pipe_judge = _pipe_judge(**question_fields)
        assert [question_label for question_label, _ in pipe_judge.labelled_questions] == expected_labels

    def test_the_variables_of_every_question_are_required(self):
        pipe_judge = _pipe_judge(questions={"urgent": _URGENT, "team": _TEAM})
        assert pipe_judge.required_variables() == {"message", "topic"}
