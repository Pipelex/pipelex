"""The judgment model a step runs on, and the refusal when there is none."""

import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.exceptions import JudgmentModelMissingError
from pipelex.kernel.judgment_ops import resolve_judgment_setting


class _DeckWithoutJudgmentDefault:
    judgment_choice_default = None


class TestResolveJudgmentSetting:
    def test_no_choice_and_no_default_is_the_missing_model_error(self, mocker: MockerFixture) -> None:
        mocker.patch("pipelex.kernel.judgment_ops.get_model_deck", return_value=_DeckWithoutJudgmentDefault())

        with pytest.raises(JudgmentModelMissingError) as exc_info:
            resolve_judgment_setting(pipe_code="triage")

        assert "PipeJudge 'triage' has no judgment model" in str(exc_info.value)
        assert "`model`" in str(exc_info.value)
        assert "`choice_default` under `[judgment]`" in str(exc_info.value)
