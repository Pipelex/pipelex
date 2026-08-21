import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.exceptions import LLMCapabilityError
from pipelex.cogt.llm.llm_job_components import LLMJobParams, ReasoningEffort
from pipelex.providers.bedrock.bedrock_llm_worker import BedrockLLMWorker


def _make_worker(mocker: MockerFixture) -> BedrockLLMWorker:
    """Create a minimal BedrockLLMWorker with a mocked inference_model."""
    worker = object.__new__(BedrockLLMWorker)
    mock_model = mocker.MagicMock()
    mock_model.desc = "test-bedrock-model"
    worker.inference_model = mock_model
    return worker


class TestBedrockReasoning:
    """Tests for reasoning parameter validation on BedrockLLMWorker."""

    def test_no_reasoning_params_passes(self, mocker: MockerFixture):
        """Validation passes when no reasoning params are set."""
        worker = _make_worker(mocker)
        job_params = LLMJobParams(temperature=0.5)
        worker._validate_no_reasoning_params(job_params=job_params)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

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
        worker = _make_worker(mocker)
        job_params = LLMJobParams(temperature=0.5, reasoning_effort=effort)
        with pytest.raises(LLMCapabilityError, match="does not support reasoning parameters"):
            worker._validate_no_reasoning_params(job_params=job_params)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

    def test_reasoning_budget_raises_capability_error(self, mocker: MockerFixture):
        """reasoning_budget should raise LLMCapabilityError for Bedrock."""
        worker = _make_worker(mocker)
        job_params = LLMJobParams(temperature=0.5, reasoning_budget=4096)
        with pytest.raises(LLMCapabilityError, match="does not support reasoning parameters"):
            worker._validate_no_reasoning_params(job_params=job_params)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
