import pytest
from google.genai import types as genai_types
from pytest_mock import MockerFixture

from pipelex.cogt.exceptions import LLMCapabilityError
from pipelex.cogt.llm.llm_job_components import LLMJobParams, ReasoningEffort
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.providers.google.google_config import GoogleConfig
from pipelex.providers.google.google_llm_worker import GoogleLLMWorker

_GOOGLE_LEVEL_MAP: dict[str, str] = {
    "none": "disabled",
    "minimal": "minimal",
    "low": "low",
    "medium": "medium",
    "high": "high",
    "xhigh": "high",
    "max": "high",
}


def _make_worker(mocker: MockerFixture, thinking_mode: ThinkingMode, prompting_target: str = "gemini") -> GoogleLLMWorker:
    """Create a minimal GoogleLLMWorker with a mocked inference_model."""
    worker = object.__new__(GoogleLLMWorker)
    mock_model = mocker.MagicMock()
    mock_model.thinking_mode = thinking_mode
    mock_model.prompting_target = prompting_target
    mock_model.desc = "test-model"
    worker.inference_model = mock_model
    return worker


def _mock_config_for_adaptive(mocker: MockerFixture) -> None:
    """Mock get_config() to return a google_config with the effort_to_level_map."""
    google_config = GoogleConfig(effort_to_level_map=_GOOGLE_LEVEL_MAP)
    mocker.patch(
        "pipelex.providers.google.google_llm_worker.get_config",
        return_value=mocker.MagicMock(
            cogt=mocker.MagicMock(
                llm_config=mocker.MagicMock(
                    google_config=google_config,
                ),
            ),
        ),
    )


class TestGoogleReasoning:
    """Tests for _build_thinking_config on GoogleLLMWorker."""

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
        """MANUAL mode maps each non-NONE ReasoningEffort to the correct thinking_budget."""
        worker = _make_worker(mocker, thinking_mode=ThinkingMode.MANUAL)
        google_config = GoogleConfig(effort_to_level_map=_GOOGLE_LEVEL_MAP)
        mocker.patch(
            "pipelex.providers.google.google_llm_worker.get_config",
            return_value=mocker.MagicMock(
                cogt=mocker.MagicMock(
                    llm_config=mocker.MagicMock(
                        get_reasoning_budget=mocker.MagicMock(return_value=expected_budget),
                        google_config=google_config,
                    ),
                ),
            ),
        )
        job_params = LLMJobParams(temperature=0.5, reasoning_effort=effort)
        result = worker._build_thinking_config(job_params=job_params, max_tokens=100000)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        assert result is not None
        assert result.thinking_budget == expected_budget

    @pytest.mark.parametrize(
        ("effort", "expected_level"),
        [
            (ReasoningEffort.MINIMAL, genai_types.ThinkingLevel.MINIMAL),
            (ReasoningEffort.LOW, genai_types.ThinkingLevel.LOW),
            (ReasoningEffort.MEDIUM, genai_types.ThinkingLevel.MEDIUM),
            (ReasoningEffort.HIGH, genai_types.ThinkingLevel.HIGH),
            (ReasoningEffort.XHIGH, genai_types.ThinkingLevel.HIGH),
            (ReasoningEffort.MAX, genai_types.ThinkingLevel.HIGH),
        ],
    )
    def test_adaptive_mode_effort_maps_to_thinking_level(
        self,
        mocker: MockerFixture,
        effort: ReasoningEffort,
        expected_level: genai_types.ThinkingLevel,
    ):
        """ADAPTIVE mode maps each ReasoningEffort to the correct ThinkingLevel with auto budget."""
        worker = _make_worker(mocker, thinking_mode=ThinkingMode.ADAPTIVE)
        _mock_config_for_adaptive(mocker)
        job_params = LLMJobParams(temperature=0.5, reasoning_effort=effort)
        result = worker._build_thinking_config(job_params=job_params, max_tokens=100000)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        assert result is not None
        assert result.thinking_level == expected_level

    def test_manual_mode_effort_none_disables_thinking(self, mocker: MockerFixture):
        """MANUAL mode with NONE effort disables thinking with budget=0 via config-driven gate."""
        worker = _make_worker(mocker, thinking_mode=ThinkingMode.MANUAL)
        google_config = GoogleConfig(effort_to_level_map=_GOOGLE_LEVEL_MAP)
        mocker.patch(
            "pipelex.providers.google.google_llm_worker.get_config",
            return_value=mocker.MagicMock(
                cogt=mocker.MagicMock(
                    llm_config=mocker.MagicMock(
                        google_config=google_config,
                    ),
                ),
            ),
        )
        job_params = LLMJobParams(temperature=0.5, reasoning_effort=ReasoningEffort.NONE)
        result = worker._build_thinking_config(job_params=job_params, max_tokens=100000)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        assert result is not None
        assert result.thinking_budget == 0

    def test_adaptive_mode_effort_none_disables_thinking(self, mocker: MockerFixture):
        """ADAPTIVE mode with NONE effort disables thinking with budget=0."""
        worker = _make_worker(mocker, thinking_mode=ThinkingMode.ADAPTIVE)
        _mock_config_for_adaptive(mocker)
        job_params = LLMJobParams(temperature=0.5, reasoning_effort=ReasoningEffort.NONE)
        result = worker._build_thinking_config(job_params=job_params, max_tokens=100000)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        assert result is not None
        assert result.thinking_budget == 0

    @pytest.mark.parametrize(
        "thinking_mode",
        [ThinkingMode.MANUAL, ThinkingMode.ADAPTIVE],
    )
    def test_explicit_budget_passes_through(
        self,
        mocker: MockerFixture,
        thinking_mode: ThinkingMode,
    ):
        """Explicit reasoning_budget passes through directly as thinking_budget."""
        worker = _make_worker(mocker, thinking_mode=thinking_mode)
        job_params = LLMJobParams(temperature=0.5, reasoning_budget=8192)
        result = worker._build_thinking_config(job_params=job_params, max_tokens=100000)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        assert result is not None
        assert result.thinking_budget == 8192

    def test_no_reasoning_params_returns_none(self, mocker: MockerFixture):
        """When neither reasoning_effort nor reasoning_budget is set, returns None."""
        worker = _make_worker(mocker, thinking_mode=ThinkingMode.MANUAL)
        job_params = LLMJobParams(temperature=0.5)
        result = worker._build_thinking_config(job_params=job_params, max_tokens=100000)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        assert result is None

    def test_thinking_mode_none_raises_capability_error(self, mocker: MockerFixture):
        """Models with thinking_mode=none should raise LLMCapabilityError."""
        worker = _make_worker(mocker, thinking_mode=ThinkingMode.NONE)
        job_params = LLMJobParams(temperature=0.5, reasoning_effort=ReasoningEffort.HIGH)
        with pytest.raises(LLMCapabilityError, match="does not support reasoning"):
            worker._build_thinking_config(job_params=job_params, max_tokens=100000)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

    def test_reasoning_budget_with_thinking_mode_none_raises(self, mocker: MockerFixture):
        """reasoning_budget with thinking_mode=none should raise LLMCapabilityError."""
        worker = _make_worker(mocker, thinking_mode=ThinkingMode.NONE)
        job_params = LLMJobParams(temperature=0.5, reasoning_budget=4096)
        with pytest.raises(LLMCapabilityError, match="does not support reasoning"):
            worker._build_thinking_config(job_params=job_params, max_tokens=100000)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

    def test_explicit_budget_capped_by_max_tokens(self, mocker: MockerFixture):
        """Explicit reasoning_budget is capped to max_tokens - 1."""
        worker = _make_worker(mocker, thinking_mode=ThinkingMode.MANUAL)
        job_params = LLMJobParams(temperature=0.5, reasoning_budget=8192)
        result = worker._build_thinking_config(job_params=job_params, max_tokens=4000)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        assert result is not None
        assert result.thinking_budget == 3999

    def test_effort_budget_capped_by_max_tokens(self, mocker: MockerFixture):
        """Effort-resolved budget is capped to max_tokens - 1 when max_tokens is small."""
        worker = _make_worker(mocker, thinking_mode=ThinkingMode.MANUAL)
        google_config = GoogleConfig(effort_to_level_map=_GOOGLE_LEVEL_MAP)
        mocker.patch(
            "pipelex.providers.google.google_llm_worker.get_config",
            return_value=mocker.MagicMock(
                cogt=mocker.MagicMock(
                    llm_config=mocker.MagicMock(
                        get_reasoning_budget=mocker.MagicMock(return_value=16384),
                        google_config=google_config,
                    ),
                ),
            ),
        )
        job_params = LLMJobParams(temperature=0.5, reasoning_effort=ReasoningEffort.HIGH)
        result = worker._build_thinking_config(job_params=job_params, max_tokens=2000)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        assert result is not None
        assert result.thinking_budget == 1999
