import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.exceptions import LLMCapabilityError
from pipelex.cogt.llm.llm_job_components import LLMJobParams, ReasoningEffort
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.providers.openai.openai_completions_llm_worker import OpenAICompletionsLLMWorker

_OPENAI_LEVEL_MAP: dict[str, str] = {
    "none": "none",
    "minimal": "minimal",
    "low": "low",
    "medium": "medium",
    "high": "high",
    "xhigh": "xhigh",
    "max": "xhigh",
}


def _make_worker(mocker: MockerFixture, thinking_mode: ThinkingMode) -> OpenAICompletionsLLMWorker:
    """Create a minimal OpenAICompletionsLLMWorker with a mocked inference_model."""
    worker = object.__new__(OpenAICompletionsLLMWorker)
    mock_model = mocker.MagicMock()
    mock_model.thinking_mode = thinking_mode
    mock_model.desc = "test-model"
    worker.inference_model = mock_model
    return worker


def _mock_config(mocker: MockerFixture) -> None:
    """Mock get_config() to return an openai_config with the effort_to_level_map."""
    from pipelex.providers.openai.openai_config import OpenAIConfig  # ruff: ignore[import-outside-top-level]

    openai_config = OpenAIConfig(effort_to_level_map=_OPENAI_LEVEL_MAP)
    mocker.patch(
        "pipelex.providers.openai.openai_completions_llm_worker.get_config",
        return_value=mocker.MagicMock(
            inference=mocker.MagicMock(
                llm=mocker.MagicMock(
                    openai=openai_config,
                ),
            ),
        ),
    )


class TestOpenAICompletionsReasoning:
    """Tests for _resolve_reasoning_effort on OpenAICompletionsLLMWorker."""

    @pytest.mark.parametrize(
        ("effort", "expected_openai_effort"),
        [
            (ReasoningEffort.NONE, "none"),
            (ReasoningEffort.MINIMAL, "minimal"),
            (ReasoningEffort.LOW, "low"),
            (ReasoningEffort.MEDIUM, "medium"),
            (ReasoningEffort.HIGH, "high"),
            (ReasoningEffort.XHIGH, "xhigh"),
            (ReasoningEffort.MAX, "xhigh"),
        ],
    )
    def test_reasoning_effort_maps_correctly(
        self,
        mocker: MockerFixture,
        effort: ReasoningEffort,
        expected_openai_effort: str,
    ):
        """Each ReasoningEffort value maps to the correct OpenAI effort string."""
        worker = _make_worker(mocker, thinking_mode=ThinkingMode.MANUAL)
        _mock_config(mocker)
        job_params = LLMJobParams(temperature=0.5, reasoning_effort=effort)
        result = worker._resolve_reasoning_effort(job_params=job_params)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
        assert result == expected_openai_effort

    def test_no_reasoning_params_returns_none(self, mocker: MockerFixture):
        """When neither reasoning_effort nor reasoning_budget is set, returns None."""
        worker = _make_worker(mocker, thinking_mode=ThinkingMode.MANUAL)
        job_params = LLMJobParams(temperature=0.5)
        result = worker._resolve_reasoning_effort(job_params=job_params)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
        assert result is None

    def test_reasoning_budget_raises_capability_error(self, mocker: MockerFixture):
        """OpenAI does not support reasoning_budget, should raise LLMCapabilityError."""
        worker = _make_worker(mocker, thinking_mode=ThinkingMode.MANUAL)
        job_params = LLMJobParams(temperature=0.5, reasoning_budget=4096)
        with pytest.raises(LLMCapabilityError, match="reasoning_budget"):
            worker._resolve_reasoning_effort(job_params=job_params)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

    def test_thinking_mode_none_raises_capability_error(self, mocker: MockerFixture):
        """Models with thinking_mode=none should raise LLMCapabilityError."""
        worker = _make_worker(mocker, thinking_mode=ThinkingMode.NONE)
        job_params = LLMJobParams(temperature=0.5, reasoning_effort=ReasoningEffort.HIGH)
        with pytest.raises(LLMCapabilityError, match="does not support reasoning"):
            worker._resolve_reasoning_effort(job_params=job_params)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

    def test_thinking_mode_adaptive_raises_capability_error(self, mocker: MockerFixture):
        """Adaptive thinking mode is not applicable to OpenAI models."""
        worker = _make_worker(mocker, thinking_mode=ThinkingMode.ADAPTIVE)
        job_params = LLMJobParams(temperature=0.5, reasoning_effort=ReasoningEffort.HIGH)
        with pytest.raises(LLMCapabilityError, match="adaptive"):
            worker._resolve_reasoning_effort(job_params=job_params)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

    def test_reasoning_budget_with_thinking_mode_none_raises(self, mocker: MockerFixture):
        """reasoning_budget with thinking_mode=none gives an accurate 'does not support reasoning' error."""
        worker = _make_worker(mocker, thinking_mode=ThinkingMode.NONE)
        job_params = LLMJobParams(temperature=0.5, reasoning_budget=4096)
        with pytest.raises(LLMCapabilityError, match="does not support reasoning"):
            worker._resolve_reasoning_effort(job_params=job_params)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
