from typing import Any

import pytest
from pydantic import ValidationError

from pipelex.cogt.judgment.judgment_models import JudgmentKind
from pipelex.pipe_operators.judge.pipe_judge_blueprint import PipeJudgeBlueprint
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

    def test_prompt_is_read_as_question(self):
        blueprint = PipeJudgeBlueprint.model_validate({"description": "d", "output": "YesNo", "prompt": "Is it urgent?"})
        assert blueprint.question == "Is it urgent?"
        assert "prompt" not in blueprint.model_dump()
