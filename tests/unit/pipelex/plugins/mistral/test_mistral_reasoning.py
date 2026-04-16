import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.exceptions import LLMCapabilityError
from pipelex.cogt.llm.llm_job_components import LLMJobParams, ReasoningEffort
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.plugins.mistral.mistral_llm_worker import MistralLLMWorker

_MISTRAL_LEVEL_MAP: dict[str, str] = {
    "none": "disabled",
    "minimal": "reasoning",
    "low": "reasoning",
    "medium": "reasoning",
    "high": "reasoning",
    "xhigh": "reasoning",
    "max": "reasoning",
}


def _make_worker(mocker: MockerFixture, thinking_mode: ThinkingMode) -> MistralLLMWorker:
    """Create a minimal MistralLLMWorker with a mocked inference_model."""
    worker = object.__new__(MistralLLMWorker)
    mock_model = mocker.MagicMock()
    mock_model.thinking_mode = thinking_mode
    mock_model.desc = "test-model"
    worker.inference_model = mock_model
    return worker


def _mock_config(mocker: MockerFixture) -> None:
    """Mock get_config() to return a mistral_config with the effort_to_level_map."""
    from pipelex.plugins.mistral.mistral_config import MistralConfig  # noqa: PLC0415

    mistral_config = MistralConfig(effort_to_level_map=_MISTRAL_LEVEL_MAP)
    mocker.patch(
        "pipelex.plugins.mistral.mistral_llm_worker.get_config",
        return_value=mocker.MagicMock(
            cogt=mocker.MagicMock(
                llm_config=mocker.MagicMock(
                    mistral_config=mistral_config,
                ),
            ),
        ),
    )


class TestMistralReasoning:
    """Tests for _resolve_prompt_mode on MistralLLMWorker."""

    def test_reasoning_budget_with_thinking_mode_none_raises(self, mocker: MockerFixture):
        """reasoning_budget with thinking_mode=none gives an accurate 'does not support reasoning' error."""
        worker = _make_worker(mocker, thinking_mode=ThinkingMode.NONE)
        job_params = LLMJobParams(temperature=0.5, reasoning_budget=4096)
        with pytest.raises(LLMCapabilityError, match="does not support reasoning"):
            worker._resolve_prompt_mode(job_params=job_params)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

    def test_reasoning_budget_with_thinking_mode_manual_raises(self, mocker: MockerFixture):
        """reasoning_budget with thinking_mode=manual raises with 'prompt_mode' guidance."""
        worker = _make_worker(mocker, thinking_mode=ThinkingMode.MANUAL)
        job_params = LLMJobParams(temperature=0.5, reasoning_budget=4096)
        with pytest.raises(LLMCapabilityError, match="reasoning_budget"):
            worker._resolve_prompt_mode(job_params=job_params)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

    @pytest.mark.parametrize(
        ("effort", "expected_prompt_mode"),
        [
            (ReasoningEffort.MINIMAL, "reasoning"),
            (ReasoningEffort.LOW, "reasoning"),
            (ReasoningEffort.MEDIUM, "reasoning"),
            (ReasoningEffort.HIGH, "reasoning"),
            (ReasoningEffort.XHIGH, "reasoning"),
            (ReasoningEffort.MAX, "reasoning"),
        ],
    )
    def test_reasoning_effort_maps_correctly(
        self,
        mocker: MockerFixture,
        effort: ReasoningEffort,
        expected_prompt_mode: str,
    ):
        """Each non-NONE ReasoningEffort maps to prompt_mode='reasoning'."""
        worker = _make_worker(mocker, thinking_mode=ThinkingMode.MANUAL)
        _mock_config(mocker)
        job_params = LLMJobParams(temperature=0.5, reasoning_effort=effort)
        result = worker._resolve_prompt_mode(job_params=job_params)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        assert result == expected_prompt_mode

    def test_thinking_mode_none_raises_capability_error(self, mocker: MockerFixture):
        """Models with thinking_mode=none should raise LLMCapabilityError."""
        worker = _make_worker(mocker, thinking_mode=ThinkingMode.NONE)
        job_params = LLMJobParams(temperature=0.5, reasoning_effort=ReasoningEffort.HIGH)
        with pytest.raises(LLMCapabilityError, match="does not support reasoning"):
            worker._resolve_prompt_mode(job_params=job_params)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

    def test_thinking_mode_adaptive_raises_capability_error(self, mocker: MockerFixture):
        """Adaptive thinking mode is not applicable to Mistral models."""
        worker = _make_worker(mocker, thinking_mode=ThinkingMode.ADAPTIVE)
        job_params = LLMJobParams(temperature=0.5, reasoning_effort=ReasoningEffort.HIGH)
        with pytest.raises(LLMCapabilityError, match="adaptive"):
            worker._resolve_prompt_mode(job_params=job_params)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

    def test_no_reasoning_params_returns_unset(self, mocker: MockerFixture):
        """When neither reasoning_effort nor reasoning_budget is set, returns UNSET."""
        from mistralai.types import UNSET  # noqa: PLC0415

        worker = _make_worker(mocker, thinking_mode=ThinkingMode.MANUAL)
        job_params = LLMJobParams(temperature=0.5)
        result = worker._resolve_prompt_mode(job_params=job_params)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        assert result is UNSET
