from typing import cast

import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.exceptions import LLMCapabilityError
from pipelex.cogt.llm.llm_job_components import LLMJobParams, ReasoningEffort
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.providers.bedrock.bedrock_llm_worker import BedrockLLMWorker


def _make_model(mocker: MockerFixture) -> InferenceModelSpec:
    """A mocked spec, for a check that reads nothing but the model's description."""
    mock_model = mocker.MagicMock()
    mock_model.desc = "test-bedrock-model"
    return cast("InferenceModelSpec", mock_model)


class TestBedrockReasoning:
    def test_no_reasoning_params_passes(self, mocker: MockerFixture):
        """A text request with no reasoning setting passes."""
        job_params = LLMJobParams(temperature=0.5)
        BedrockLLMWorker.check_request(inference_model=_make_model(mocker), job_params=job_params, is_structured=False)

    @pytest.mark.parametrize(
        "effort",
        [
            ReasoningEffort.NONE,
            ReasoningEffort.MINIMAL,
            ReasoningEffort.LOW,
            ReasoningEffort.MEDIUM,
            ReasoningEffort.HIGH,
            ReasoningEffort.MAX,
        ],
    )
    def test_reasoning_effort_raises_capability_error(self, mocker: MockerFixture, effort: ReasoningEffort):
        """Any reasoning_effort value should raise LLMCapabilityError for Bedrock."""
        job_params = LLMJobParams(temperature=0.5, reasoning_effort=effort)
        with pytest.raises(LLMCapabilityError, match="does not support reasoning parameters"):
            BedrockLLMWorker.check_request(inference_model=_make_model(mocker), job_params=job_params, is_structured=False)

    def test_reasoning_budget_raises_capability_error(self, mocker: MockerFixture):
        """reasoning_budget should raise LLMCapabilityError for Bedrock."""
        job_params = LLMJobParams(temperature=0.5, reasoning_budget=4096)
        with pytest.raises(LLMCapabilityError, match="does not support reasoning parameters"):
            BedrockLLMWorker.check_request(inference_model=_make_model(mocker), job_params=job_params, is_structured=False)

    def test_structured_output_raises_capability_error(self, mocker: MockerFixture):
        """A structured output is refused, with or without a reasoning setting: the worker cannot generate objects."""
        job_params = LLMJobParams(temperature=0.5)
        with pytest.raises(LLMCapabilityError, match="It is not possible to generate objects with a BedrockLLMWorker"):
            BedrockLLMWorker.check_request(inference_model=_make_model(mocker), job_params=job_params, is_structured=True)
