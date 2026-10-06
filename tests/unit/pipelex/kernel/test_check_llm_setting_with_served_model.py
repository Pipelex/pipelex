from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from pipelex.base_exceptions import DisclosureMode
from pipelex.cogt.exceptions import LLMSettingRefusedError, ModelWaterfallError
from pipelex.cogt.llm.llm_job_components import LLMJobParams, ReasoningEffort
from pipelex.cogt.llm.llm_setting import LLMSetting
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.cogt.model_backends.constraints import ValuedConstraint
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.usage.cost_category import CostCategory
from pipelex.kernel.llm_ops import check_llm_setting_with_served_model
from pipelex.system.exceptions import MissingDependencyError

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

_SETTING = LLMSetting(model="@some-alias", temperature=0.2, reasoning_effort=ReasoningEffort.HIGH)


def _make_model(*, thinking_mode: ThinkingMode, valued_constraints: dict[ValuedConstraint, Any] | None = None) -> InferenceModelSpec:
    return InferenceModelSpec(
        backend_name="some_backend",
        name="some-model",
        sdk="some_sdk",
        model_type=ModelType.LLM,
        model_id="some-model-id",
        inputs=["text"],
        outputs=["text", "structured"],
        costs={CostCategory.INPUT: 1, CostCategory.OUTPUT: 2},
        thinking_mode=thinking_mode,
        max_tokens=4096,
        max_prompt_images=None,
        valued_constraints=valued_constraints or {},
    )


def _serve(mocker: MockerFixture, *, served: InferenceModelSpec | Exception | None, check: Any) -> Any:
    """Patch the deck to serve `served` for any handle, and the registry to hand out `check` for any sdk; return the deck lookup."""
    deck = mocker.MagicMock()
    if isinstance(served, Exception):
        deck.get_optional_inference_model.side_effect = served
    else:
        deck.get_optional_inference_model.return_value = served
    mocker.patch("pipelex.kernel.llm_ops.get_model_deck", return_value=deck)
    registry = mocker.MagicMock()
    registry.lookup_llm_request_check.return_value = check
    mocker.patch("pipelex.kernel.llm_ops.get_inference_backend_registry", return_value=registry)
    return deck.get_optional_inference_model


class TestCheckLLMSettingWithServedModel:
    @pytest.mark.parametrize("is_structured", [False, True])
    def test_the_backend_check_runs_with_the_constrained_job_params(self, mocker: MockerFixture, is_structured: bool) -> None:
        """The registered check sees the job params the worker would send, the model's fixed temperature applied."""
        inference_model = _make_model(thinking_mode=ThinkingMode.MANUAL, valued_constraints={ValuedConstraint.FIXED_TEMPERATURE: 1})
        check = mocker.MagicMock()
        lookup = _serve(mocker, served=inference_model, check=check)

        check_llm_setting_with_served_model(llm_setting=_SETTING, is_structured=is_structured)

        lookup.assert_called_once_with(model_handle="@some-alias", model_type=ModelType.LLM)
        check.assert_called_once_with(
            inference_model=inference_model,
            job_params=LLMJobParams(temperature=1, max_tokens=4096, reasoning_effort=ReasoningEffort.HIGH),
            is_structured=is_structured,
        )

    def test_a_backend_without_a_check_is_held_to_the_shared_rule(self, mocker: MockerFixture) -> None:
        """A model with no thinking takes no reasoning setting, whatever plugin serves it."""
        _serve(mocker, served=_make_model(thinking_mode=ThinkingMode.NONE), check=None)
        with pytest.raises(LLMSettingRefusedError, match=r"does not support reasoning \(thinking_mode=none\)"):
            check_llm_setting_with_served_model(llm_setting=_SETTING, is_structured=True)

    def test_a_refusal_names_the_model_by_its_handle_and_is_shown_under_strict_disclosure(self, mocker: MockerFixture) -> None:
        """A worker names the model with its SDK, backend and provider id, which only its operator may see."""
        _serve(mocker, served=_make_model(thinking_mode=ThinkingMode.NONE), check=None)
        with pytest.raises(LLMSettingRefusedError) as exc_info:
            check_llm_setting_with_served_model(llm_setting=_SETTING, is_structured=False)
        message = str(exc_info.value)
        assert message.startswith("Model 'some-model' does not support reasoning")
        for internal_name in ("some_sdk", "some_backend", "some-model-id"):
            assert internal_name not in message
        assert exc_info.value.to_error_report().to_dict(disclosure_mode=DisclosureMode.STRICT)["message"] == message

    @pytest.mark.parametrize(
        "served",
        [
            pytest.param(None, id="not_served"),
            pytest.param(ModelWaterfallError(message="none served", model_handle="~some-waterfall", fallback_list=["a", "b"]), id="waterfall"),
        ],
    )
    def test_a_model_no_backend_serves_is_left_to_the_run(self, mocker: MockerFixture, served: InferenceModelSpec | Exception | None) -> None:
        check = mocker.MagicMock()
        _serve(mocker, served=served, check=check)
        check_llm_setting_with_served_model(llm_setting=_SETTING, is_structured=True)
        check.assert_not_called()

    def test_a_backend_whose_sdk_is_missing_is_left_to_the_run(self, mocker: MockerFixture) -> None:
        check = mocker.MagicMock(side_effect=MissingDependencyError("some-sdk", "some-extra"))
        _serve(mocker, served=_make_model(thinking_mode=ThinkingMode.MANUAL), check=check)
        check_llm_setting_with_served_model(llm_setting=_SETTING, is_structured=True)
        check.assert_called_once()
