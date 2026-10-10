from typing import Any

import pytest
from pydantic import ValidationError

from pipelex.cogt.judgment.judgment_models import JudgmentKind, RatingLevel
from pipelex.pipe_operators.judge.pipe_judge_blueprint import JudgeRatingLevel, JudgeYesNoCriteria, PipeJudgeBlueprint
from tests.unit.pipelex.pipe_operators.pipe_judge.data import PipeJudgeBlueprintTestCases


class TestPipeJudgeBlueprint:
    @pytest.mark.parametrize(("test_id", "blueprint_fields", "message_fragment"), PipeJudgeBlueprintTestCases.REFUSED)
    def test_refused(self, test_id: str, blueprint_fields: dict[str, Any], message_fragment: str):
        with pytest.raises(ValidationError) as exc_info:
            PipeJudgeBlueprint.model_validate(blueprint_fields)
        assert message_fragment in str(exc_info.value), test_id

    @pytest.mark.parametrize(("test_id", "blueprint_fields", "expected_kind"), PipeJudgeBlueprintTestCases.ACCEPTED)
    def test_accepted(self, test_id: str, blueprint_fields: dict[str, Any], expected_kind: JudgmentKind):
        blueprint = PipeJudgeBlueprint.model_validate(blueprint_fields)
        assert blueprint.judgment_kind == expected_kind, test_id

    @pytest.mark.parametrize(("test_id", "blueprint_fields", "message_fragment"), PipeJudgeBlueprintTestCases.REFUSED_SEVERAL)
    def test_several_questions_refused(self, test_id: str, blueprint_fields: dict[str, Any], message_fragment: str):
        with pytest.raises(ValidationError) as exc_info:
            PipeJudgeBlueprint.model_validate(blueprint_fields)
        assert message_fragment in str(exc_info.value), test_id

    @pytest.mark.parametrize(("test_id", "blueprint_fields", "expected_kinds"), PipeJudgeBlueprintTestCases.ACCEPTED_SEVERAL)
    def test_several_questions_accepted(self, test_id: str, blueprint_fields: dict[str, Any], expected_kinds: dict[str, JudgmentKind]):
        """Each question's kind is read off its own `options` and `levels`, and the pipe itself has no single kind."""
        blueprint = PipeJudgeBlueprint.model_validate(blueprint_fields)
        assert blueprint.questions is not None, test_id
        assert {name: question.judgment_kind for name, question in blueprint.questions.items()} == expected_kinds, test_id
        assert blueprint.question is None, test_id
        assert blueprint.judgment_kind is None, test_id

    def test_a_question_of_several_carries_its_own_fields(self):
        blueprint = PipeJudgeBlueprint.model_validate(
            {
                "description": "d",
                "inputs": {"message": "Text"},
                "output": "MessageTriage",
                "prompt": "@message",
                "questions": {
                    "urgent": {"question": "Is it urgent?", "threshold": 0.7, "criteria": {"yes": "It cannot wait", "no": "It can wait"}},
                    "severity": {"question": "How severe?", "levels": ["Barely", {"description": "Nothing works"}]},
                },
            }
        )
        assert blueprint.questions is not None
        urgent = blueprint.questions["urgent"]
        assert urgent.question == "Is it urgent?"
        assert urgent.threshold == 0.7
        assert urgent.criteria == JudgeYesNoCriteria(yes="It cannot wait", no="It can wait")
        assert urgent.rating_levels is None
        severity = blueprint.questions["severity"]
        assert severity.levels == ["Barely", JudgeRatingLevel(description="Nothing works")]
        assert severity.rating_levels == [RatingLevel(description="Barely"), RatingLevel(description="Nothing works")]

    def test_the_prompt_and_the_question_are_two_fields(self):
        """`prompt` is the evidence and `question` the instruction, so neither is read as the other."""
        blueprint = PipeJudgeBlueprint.model_validate(
            {"description": "d", "inputs": {"message": "Text"}, "output": "YesNo", "prompt": "@message", "question": "Is it urgent?"}
        )
        assert blueprint.prompt == "@message"
        assert blueprint.question == "Is it urgent?"

    def test_a_level_string_and_a_level_table_both_parse(self):
        blueprint = PipeJudgeBlueprint.model_validate(
            {
                "description": "d",
                "inputs": {"report": "Text"},
                "output": "Rating",
                "prompt": "@report",
                "question": "How severe?",
                "levels": ["Barely", {"description": "Severe"}],
            }
        )
        assert blueprint.levels == ["Barely", JudgeRatingLevel(description="Severe")]
