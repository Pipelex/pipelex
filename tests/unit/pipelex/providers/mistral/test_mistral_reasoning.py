import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.exceptions import LLMCapabilityError
from pipelex.cogt.llm.llm_job_components import LLMJobParams, ReasoningEffort
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.providers.mistral.mistral_llm_worker import MistralLLMWorker

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
    from pipelex.providers.mistral.mistral_config import MistralConfig  # ruff: ignore[import-outside-top-level]

    mistral_config = MistralConfig(effort_to_level_map=_MISTRAL_LEVEL_MAP)
    mocker.patch(
        "pipelex.providers.mistral.mistral_llm_worker.get_config",
        return_value=mocker.MagicMock(
            inference=mocker.MagicMock(
                llm=mocker.MagicMock(
                    mistral=mistral_config,
                ),
            ),
        ),
    )


class TestMistralReasoning:
    """Tests for _resolve_reasoning_effort on MistralLLMWorker."""

    def test_reasoning_budget_with_thinking_mode_none_raises(self, mocker: MockerFixture):
        """reasoning_budget with thinking_mode=none gives an accurate 'does not support reasoning' error."""
        worker = _make_worker(mocker, thinking_mode=ThinkingMode.NONE)
        job_params = LLMJobParams(temperature=0.5, reasoning_budget=4096)
        with pytest.raises(LLMCapabilityError, match="does not support reasoning"):
            worker._resolve_reasoning_effort(inference_model=worker.inference_model, job_params=job_params)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

    def test_reasoning_budget_with_thinking_mode_manual_raises(self, mocker: MockerFixture):
        """reasoning_budget with thinking_mode=manual raises with 'reasoning_effort' guidance."""
        worker = _make_worker(mocker, thinking_mode=ThinkingMode.MANUAL)
        job_params = LLMJobParams(temperature=0.5, reasoning_budget=4096)
        with pytest.raises(LLMCapabilityError, match="does not support reasoning_budget; Mistral uses reasoning_effort instead"):
            worker._resolve_reasoning_effort(inference_model=worker.inference_model, job_params=job_params)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

    @pytest.mark.parametrize(
        ("effort", "expected_mistral_effort"),
        [
            (ReasoningEffort.MINIMAL, "high"),
            (ReasoningEffort.LOW, "high"),
            (ReasoningEffort.MEDIUM, "high"),
            (ReasoningEffort.HIGH, "high"),
            (ReasoningEffort.XHIGH, "high"),
            (ReasoningEffort.MAX, "high"),
        ],
    )
    def test_reasoning_effort_maps_correctly(
        self,
        mocker: MockerFixture,
        effort: ReasoningEffort,
        expected_mistral_effort: str,
    ):
        """Each non-NONE ReasoningEffort maps to the `reasoning` level, which Mistral turns on as reasoning_effort `high`."""
        worker = _make_worker(mocker, thinking_mode=ThinkingMode.MANUAL)
        _mock_config(mocker)
        job_params = LLMJobParams(temperature=0.5, reasoning_effort=effort)
        result = worker._resolve_reasoning_effort(inference_model=worker.inference_model, job_params=job_params)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
        assert result == expected_mistral_effort

    def test_thinking_mode_none_raises_capability_error(self, mocker: MockerFixture):
        """Models with thinking_mode=none should raise LLMCapabilityError."""
        worker = _make_worker(mocker, thinking_mode=ThinkingMode.NONE)
        job_params = LLMJobParams(temperature=0.5, reasoning_effort=ReasoningEffort.HIGH)
        with pytest.raises(LLMCapabilityError, match="does not support reasoning"):
            worker._resolve_reasoning_effort(inference_model=worker.inference_model, job_params=job_params)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

    def test_thinking_mode_adaptive_raises_capability_error(self, mocker: MockerFixture):
        """Adaptive thinking mode is not applicable to Mistral models."""
        worker = _make_worker(mocker, thinking_mode=ThinkingMode.ADAPTIVE)
        job_params = LLMJobParams(temperature=0.5, reasoning_effort=ReasoningEffort.HIGH)
        with pytest.raises(LLMCapabilityError, match="adaptive"):
            worker._resolve_reasoning_effort(inference_model=worker.inference_model, job_params=job_params)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

    def test_none_effort_omits_the_parameter(self, mocker: MockerFixture):
        """NONE maps to disabled, so the parameter is left out and the model does not reason."""
        from mistralai.client.types import UNSET  # ruff: ignore[import-outside-top-level]

        worker = _make_worker(mocker, thinking_mode=ThinkingMode.MANUAL)
        _mock_config(mocker)
        job_params = LLMJobParams(temperature=0.5, reasoning_effort=ReasoningEffort.NONE)
        result = worker._resolve_reasoning_effort(inference_model=worker.inference_model, job_params=job_params)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
        assert result is UNSET

    def test_no_reasoning_params_returns_unset(self, mocker: MockerFixture):
        """When neither reasoning_effort nor reasoning_budget is set, returns UNSET."""
        from mistralai.client.types import UNSET  # ruff: ignore[import-outside-top-level]

        worker = _make_worker(mocker, thinking_mode=ThinkingMode.MANUAL)
        job_params = LLMJobParams(temperature=0.5)
        result = worker._resolve_reasoning_effort(inference_model=worker.inference_model, job_params=job_params)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
        assert result is UNSET
