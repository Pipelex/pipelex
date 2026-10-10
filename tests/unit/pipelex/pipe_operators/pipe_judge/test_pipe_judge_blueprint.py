from typing import Any

import pytest
from pydantic import ValidationError

from pipelex.cogt.judgment.judgment_models import JudgmentKind
from pipelex.pipe_operators.judge.pipe_judge_blueprint import JudgeRatingLevel, PipeJudgeBlueprint
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
