"""The judgment model a step runs on, and the refusal when there is none."""

from typing import Any

import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.exceptions import JudgmentModelMissingError, ModelNotFoundError
from pipelex.cogt.judgment.judgment_setting import JudgmentSetting
from pipelex.kernel.judgment_ops import resolve_judgment_setting


class _DeckWithoutJudgmentDefault:
    judgment_choice_default = None


def _deck_serving_no_judgment_model(mocker: MockerFixture) -> Any:
    """A deck whose judgment alias names a model no backend serves, as on a keyless boot that skipped TypeSafe."""
    model_deck = mocker.Mock(judgment_choice_default=None)
    model_deck.get_judgment_setting.return_value = JudgmentSetting(model="jev-1.13.0")
    model_deck.get_optional_inference_model.return_value = None
    model_deck.get_required_inference_model.side_effect = ModelNotFoundError(
        message="Model handle 'jev-1.13.0' was not found in the model deck.", model_handle="jev-1.13.0"
    )
    return model_deck


class TestResolveJudgmentSetting:
    def test_no_choice_and_no_default_is_the_missing_model_error(self, mocker: MockerFixture) -> None:
        mocker.patch("pipelex.kernel.judgment_ops.get_model_deck", return_value=_DeckWithoutJudgmentDefault())

        with pytest.raises(JudgmentModelMissingError) as exc_info:
            resolve_judgment_setting(pipe_code="triage")

        assert "PipeJudge 'triage' has no judgment model" in str(exc_info.value)
        assert "`model`" in str(exc_info.value)
        assert "`choice_default` under `[judgment]`" in str(exc_info.value)

    def test_no_choice_and_no_default_is_the_missing_model_error_on_a_dry_run_too(self, mocker: MockerFixture) -> None:
        mocker.patch("pipelex.kernel.judgment_ops.get_model_deck", return_value=_DeckWithoutJudgmentDefault())

        with pytest.raises(JudgmentModelMissingError):
            resolve_judgment_setting(pipe_code="triage", is_dry=True)

    def test_a_dry_run_keeps_the_handle_of_a_model_no_backend_serves(self, mocker: MockerFixture) -> None:
        mocker.patch("pipelex.kernel.judgment_ops.get_model_deck", return_value=_deck_serving_no_judgment_model(mocker))

        judgment_setting = resolve_judgment_setting(judgment_choice="@default-judgment", pipe_code="triage", is_dry=True)

        assert judgment_setting.model == "jev-1.13.0"

    def test_a_live_run_refuses_a_model_no_backend_serves(self, mocker: MockerFixture) -> None:
        mocker.patch("pipelex.kernel.judgment_ops.get_model_deck", return_value=_deck_serving_no_judgment_model(mocker))

        with pytest.raises(ModelNotFoundError, match=r"jev-1\.13\.0"):
            resolve_judgment_setting(judgment_choice="@default-judgment", pipe_code="triage")
