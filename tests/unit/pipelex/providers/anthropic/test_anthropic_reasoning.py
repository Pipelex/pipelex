import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.exceptions import LLMCapabilityError
from pipelex.cogt.llm.llm_job_components import LLMJobParams, ReasoningEffort
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.providers.anthropic.anthropic_config import AnthropicConfig
from pipelex.providers.anthropic.anthropic_llm_worker import AnthropicLLMWorker

_ANTHROPIC_LEVEL_MAP: dict[str, str] = {
    "none": "disabled",
    "minimal": "low",
    "low": "low",
    "medium": "medium",
    "high": "high",
    "xhigh": "xhigh",
    "max": "max",
}


def _make_worker(mocker: MockerFixture, thinking_mode: ThinkingMode) -> AnthropicLLMWorker:
    """Create a minimal AnthropicLLMWorker with a mocked inference_model."""
    worker = object.__new__(AnthropicLLMWorker)
    mock_model = mocker.MagicMock()
    mock_model.thinking_mode = thinking_mode
    mock_model.desc = "test-model"
    del mock_model.prompting_target  # budget resolution is worker-owned; reading the model spec for it would raise
    worker.inference_model = mock_model
    return worker


def _mock_config(mocker: MockerFixture, budget_mock: object | None = None) -> None:
    """Mock get_config() with a real anthropic_config and an optional get_reasoning_budget mock."""
    anthropic_config = AnthropicConfig(structured_output_timeout_seconds=1200, effort_to_level_map=_ANTHROPIC_LEVEL_MAP)
    llm_config = mocker.MagicMock(anthropic_config=anthropic_config)
    if budget_mock is not None:
        llm_config.get_reasoning_budget = budget_mock
    mocker.patch(
        "pipelex.providers.anthropic.anthropic_llm_worker.get_config",
        return_value=mocker.MagicMock(cogt=mocker.MagicMock(llm_config=llm_config)),
    )


class TestAnthropicReasoning:
    """Tests for _build_thinking_params on AnthropicLLMWorker."""

    @pytest.mark.parametrize(
        ("effort", "expected_budget"),
        [
            (ReasoningEffort.MINIMAL, 512),
            (ReasoningEffort.LOW, 1024),
            (ReasoningEffort.MEDIUM, 5000),
            (ReasoningEffort.HIGH, 16384),
            (ReasoningEffort.XHIGH, 32768),
            (ReasoningEffort.MAX, 65536),
        ],
    )
    def test_manual_mode_effort_maps_to_budget(
        self,
        mocker: MockerFixture,
        effort: ReasoningEffort,
        expected_budget: int,
    ):
        """MANUAL mode maps each non-NONE ReasoningEffort to the correct budget_tokens, keyed by the worker-owned family."""
        worker = _make_worker(mocker, thinking_mode=ThinkingMode.MANUAL)
        budget_mock = mocker.MagicMock(return_value=expected_budget)
        _mock_config(mocker, budget_mock=budget_mock)
        job_params = LLMJobParams(temperature=0.5, reasoning_effort=effort)
        result = worker._build_thinking_params(job_params=job_params, max_tokens=100000)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        assert result.thinking == {"type": "enabled", "budget_tokens": expected_budget}
        assert result.suppress_temperature is True
        budget_mock.assert_called_once_with(family="anthropic", effort=effort)

    def test_manual_mode_effort_none_disables_thinking(self, mocker: MockerFixture):
        """MANUAL mode with NONE effort disables thinking entirely (no budget lookup)."""
        worker = _make_worker(mocker, thinking_mode=ThinkingMode.MANUAL)
        budget_mock = mocker.MagicMock()
        _mock_config(mocker, budget_mock=budget_mock)
        job_params = LLMJobParams(temperature=0.5, reasoning_effort=ReasoningEffort.NONE)
        result = worker._build_thinking_params(job_params=job_params, max_tokens=100000)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        assert result.thinking is None
        assert result.suppress_temperature is False
        budget_mock.assert_not_called()

    def test_effort_budget_capped_by_max_tokens(self, mocker: MockerFixture):
        """Effort-resolved budget is capped to max_tokens - 1 when max_tokens is small."""
        worker = _make_worker(mocker, thinking_mode=ThinkingMode.MANUAL)
        budget_mock = mocker.MagicMock(return_value=16384)
        _mock_config(mocker, budget_mock=budget_mock)
        job_params = LLMJobParams(temperature=0.5, reasoning_effort=ReasoningEffort.HIGH)
        result = worker._build_thinking_params(job_params=job_params, max_tokens=2000)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        assert result.thinking == {"type": "enabled", "budget_tokens": 1999}

    def test_explicit_budget_passes_through(self, mocker: MockerFixture):
        """Explicit reasoning_budget passes through directly as budget_tokens in MANUAL mode."""
        worker = _make_worker(mocker, thinking_mode=ThinkingMode.MANUAL)
        job_params = LLMJobParams(temperature=0.5, reasoning_budget=8192)
        result = worker._build_thinking_params(job_params=job_params, max_tokens=100000)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        assert result.thinking == {"type": "enabled", "budget_tokens": 8192}
        assert result.suppress_temperature is True

    def test_thinking_mode_none_raises_capability_error(self, mocker: MockerFixture):
        """Models with thinking_mode=none should raise LLMCapabilityError on reasoning_effort."""
        worker = _make_worker(mocker, thinking_mode=ThinkingMode.NONE)
        job_params = LLMJobParams(temperature=0.5, reasoning_effort=ReasoningEffort.HIGH)
        with pytest.raises(LLMCapabilityError, match="does not support reasoning"):
            worker._build_thinking_params(job_params=job_params, max_tokens=100000)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
