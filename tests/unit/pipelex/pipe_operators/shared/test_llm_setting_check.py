from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from pipelex.cogt.exceptions import LLMCapabilityError
from pipelex.cogt.llm.llm_job_components import ReasoningEffort
from pipelex.cogt.llm.llm_setting import LLMModelChoice, LLMSetting
from pipelex.cogt.models.model_reference import ModelReference
from pipelex.core.pipes.exceptions import PipeValidationError
from pipelex.pipe_operators.shared.llm_setting_check import refuse_llm_setting_its_model_refuses
from pipelex.validation_error_types import PipeValidationErrorType

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

_SETTING = LLMSetting(model="@some-alias", temperature=0.2, reasoning_effort=ReasoningEffort.HIGH)
_WORKER_REFUSAL = "Model 'some-model' does not support reasoning (thinking_mode=none)"


class TestLLMSettingCheck:
    @pytest.mark.parametrize(
        ("llm_choice", "field_name", "is_structured", "expected_message", "expected_model_reference"),
        [
            pytest.param(
                ModelReference.parse("$deep-analysis"),
                "model",
                True,
                "PipeLLM 'answer_it' generates a structured output with the model setting `$deep-analysis` its `model` names, "
                f"which the model it resolves to refuses: {_WORKER_REFUSAL} Name another setting in `model`, or one whose model takes it.",
                "$deep-analysis",
                id="preset_reference",
            ),
            pytest.param(
                _SETTING,
                "model_to_structure",
                True,
                "PipeLLM 'answer_it' generates a structured output with the model setting its `model_to_structure` writes inline, "
                f"which the model it resolves to refuses: {_WORKER_REFUSAL} "
                "Change the setting in `model_to_structure`, or name a model that takes it.",
                None,
                id="inline_setting",
            ),
            pytest.param(
                None,
                None,
                False,
                "PipeLLM 'answer_it' generates text with the model deck's default setting for text, "
                f"which the model it resolves to refuses: {_WORKER_REFUSAL} Name a model setting in the pipe, or change the deck's default for text.",
                None,
                id="deck_default_for_text",
            ),
            pytest.param(
                None,
                None,
                True,
                "PipeLLM 'answer_it' generates a structured output with the model deck's default setting for structured outputs, "
                f"which the model it resolves to refuses: {_WORKER_REFUSAL} "
                "Name a model setting in the pipe, or change the deck's default for structured outputs.",
                None,
                id="deck_default_for_structured_outputs",
            ),
        ],
    )
    def test_a_refusal_names_the_pipe_the_setting_and_the_model_s_reason(
        self,
        mocker: MockerFixture,
        llm_choice: LLMModelChoice | None,
        field_name: str | None,
        is_structured: bool,
        expected_message: str,
        expected_model_reference: str | None,
    ) -> None:
        check = mocker.patch(
            "pipelex.pipe_operators.shared.llm_setting_check.check_llm_setting_with_served_model",
            side_effect=LLMCapabilityError(_WORKER_REFUSAL),
        )
        with pytest.raises(PipeValidationError) as exc_info:
            refuse_llm_setting_its_model_refuses(
                pipe_type="PipeLLM",
                pipe_code="answer_it",
                domain_code="some_domain",
                llm_setting=_SETTING,
                llm_choice=llm_choice,
                field_name=field_name,
                is_structured=is_structured,
            )
        check.assert_called_once_with(llm_setting=_SETTING, is_structured=is_structured)
        refusal = exc_info.value
        assert str(refusal) == expected_message
        assert refusal.error_type == PipeValidationErrorType.LLM_SETTING_REFUSED_BY_MODEL
        assert refusal.pipe_code == "answer_it"
        assert refusal.domain_code == "some_domain"
        assert refusal.field_name == field_name
        assert refusal.model_reference == expected_model_reference

    def test_a_setting_the_model_takes_passes(self, mocker: MockerFixture) -> None:
        mocker.patch("pipelex.pipe_operators.shared.llm_setting_check.check_llm_setting_with_served_model", return_value=None)
        refuse_llm_setting_its_model_refuses(
            pipe_type="PipeStructure",
            pipe_code="structure_it",
            domain_code="some_domain",
            llm_setting=_SETTING,
            llm_choice=_SETTING,
            field_name="model",
            is_structured=True,
        )
