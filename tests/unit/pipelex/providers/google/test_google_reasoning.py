import pytest
from google.genai import types as genai_types
from pytest_mock import MockerFixture

from pipelex.cogt.exceptions import LLMCapabilityError
from pipelex.cogt.llm.llm_job_components import LLMJobParams, ReasoningEffort
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.cogt.model_backends.constraints import ListedConstraint
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


def _make_worker(
    mocker: MockerFixture,
    thinking_mode: ThinkingMode,
    *,
    min_thinking_budget: int | None = None,
    max_thinking_budget: int | None = None,
    listed_constraints: list[ListedConstraint] | None = None,
) -> GoogleLLMWorker:
    """Create a minimal GoogleLLMWorker with a mocked inference_model, declaring no thinking budget bounds or constraints by default."""
    worker = object.__new__(GoogleLLMWorker)
    mock_model = mocker.MagicMock()
    mock_model.thinking_mode = thinking_mode
    mock_model.desc = "test-model"
    mock_model.listed_constraints = listed_constraints or []
    mock_model.min_thinking_budget = min_thinking_budget
    mock_model.max_thinking_budget = max_thinking_budget
    worker.inference_model = mock_model
    return worker


def _mock_config_for_adaptive(mocker: MockerFixture) -> None:
    """Mock get_config() to return a google_config with the effort_to_level_map."""
    google_config = GoogleConfig(effort_to_level_map=_GOOGLE_LEVEL_MAP)
    mocker.patch(
        "pipelex.providers.google.google_llm_worker.get_config",
        return_value=mocker.MagicMock(
            inference=mocker.MagicMock(
                llm=mocker.MagicMock(
                    google=google_config,
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
        """MANUAL mode maps each non-NONE ReasoningEffort to the correct thinking_budget, keyed by the worker-owned family."""
        worker = _make_worker(mocker, thinking_mode=ThinkingMode.MANUAL)
        google_config = GoogleConfig(effort_to_level_map=_GOOGLE_LEVEL_MAP)
        budget_mock = mocker.MagicMock(return_value=expected_budget)
        mocker.patch(
            "pipelex.providers.google.google_llm_worker.get_config",
            return_value=mocker.MagicMock(
                inference=mocker.MagicMock(
                    llm=mocker.MagicMock(
                        get_reasoning_budget=budget_mock,
                        google=google_config,
                    ),
                ),
            ),
        )
        job_params = LLMJobParams(temperature=0.5, reasoning_effort=effort)
        result = worker._build_thinking_config(inference_model=worker.inference_model, job_params=job_params, max_tokens=100000)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
        assert result is not None
        assert result.thinking_budget == expected_budget
        budget_mock.assert_called_once_with(family="gemini", effort=effort)

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
        result = worker._build_thinking_config(inference_model=worker.inference_model, job_params=job_params, max_tokens=100000)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
        assert result is not None
        assert result.thinking_level == expected_level

    def test_manual_mode_effort_none_disables_thinking(self, mocker: MockerFixture):
        """MANUAL mode with NONE effort disables thinking with budget=0 via config-driven gate."""
        worker = _make_worker(mocker, thinking_mode=ThinkingMode.MANUAL)
        google_config = GoogleConfig(effort_to_level_map=_GOOGLE_LEVEL_MAP)
        mocker.patch(
            "pipelex.providers.google.google_llm_worker.get_config",
            return_value=mocker.MagicMock(
                inference=mocker.MagicMock(
                    llm=mocker.MagicMock(
                        google=google_config,
                    ),
                ),
            ),
        )
        job_params = LLMJobParams(temperature=0.5, reasoning_effort=ReasoningEffort.NONE)
        result = worker._build_thinking_config(inference_model=worker.inference_model, job_params=job_params, max_tokens=100000)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
        assert result is not None
        assert result.thinking_budget == 0

    def test_adaptive_mode_effort_none_disables_thinking(self, mocker: MockerFixture):
        """ADAPTIVE mode with NONE effort disables thinking with budget=0."""
        worker = _make_worker(mocker, thinking_mode=ThinkingMode.ADAPTIVE)
        _mock_config_for_adaptive(mocker)
        job_params = LLMJobParams(temperature=0.5, reasoning_effort=ReasoningEffort.NONE)
        result = worker._build_thinking_config(inference_model=worker.inference_model, job_params=job_params, max_tokens=100000)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
        assert result is not None
        assert result.thinking_budget == 0

    @pytest.mark.parametrize("thinking_mode", [ThinkingMode.MANUAL, ThinkingMode.ADAPTIVE])
    def test_effort_none_is_refused_on_a_model_that_cannot_turn_thinking_off(self, mocker: MockerFixture, thinking_mode: ThinkingMode):
        """Gemini 2.5 Pro and 3.1 Pro answer a budget of 0 with a 400, so the worker refuses before sending it."""
        worker = _make_worker(mocker, thinking_mode=thinking_mode, listed_constraints=[ListedConstraint.THINKING_CANNOT_BE_DISABLED])
        _mock_config_for_adaptive(mocker)
        job_params = LLMJobParams(temperature=0.5, reasoning_effort=ReasoningEffort.NONE)
        with pytest.raises(LLMCapabilityError, match="cannot turn thinking off"):
            worker._build_thinking_config(inference_model=worker.inference_model, job_params=job_params, max_tokens=100000)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

    def test_another_effort_still_thinks_on_a_model_that_cannot_turn_thinking_off(self, mocker: MockerFixture):
        worker = _make_worker(mocker, thinking_mode=ThinkingMode.ADAPTIVE, listed_constraints=[ListedConstraint.THINKING_CANNOT_BE_DISABLED])
        _mock_config_for_adaptive(mocker)
        job_params = LLMJobParams(temperature=0.5, reasoning_effort=ReasoningEffort.LOW)
        result = worker._build_thinking_config(inference_model=worker.inference_model, job_params=job_params, max_tokens=100000)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
        assert result is not None
        assert result.thinking_level == genai_types.ThinkingLevel.LOW

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
        result = worker._build_thinking_config(inference_model=worker.inference_model, job_params=job_params, max_tokens=100000)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
        assert result is not None
        assert result.thinking_budget == 8192

    def test_no_reasoning_params_returns_none(self, mocker: MockerFixture):
        """When neither reasoning_effort nor reasoning_budget is set, returns None."""
        worker = _make_worker(mocker, thinking_mode=ThinkingMode.MANUAL)
        job_params = LLMJobParams(temperature=0.5)
        result = worker._build_thinking_config(inference_model=worker.inference_model, job_params=job_params, max_tokens=100000)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
        assert result is None

    def test_thinking_mode_none_raises_capability_error(self, mocker: MockerFixture):
        """Models with thinking_mode=none should raise LLMCapabilityError."""
        worker = _make_worker(mocker, thinking_mode=ThinkingMode.NONE)
        job_params = LLMJobParams(temperature=0.5, reasoning_effort=ReasoningEffort.HIGH)
        with pytest.raises(LLMCapabilityError, match="does not support reasoning"):
            worker._build_thinking_config(inference_model=worker.inference_model, job_params=job_params, max_tokens=100000)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

    def test_reasoning_budget_with_thinking_mode_none_raises(self, mocker: MockerFixture):
        """reasoning_budget with thinking_mode=none should raise LLMCapabilityError."""
        worker = _make_worker(mocker, thinking_mode=ThinkingMode.NONE)
        job_params = LLMJobParams(temperature=0.5, reasoning_budget=4096)
        with pytest.raises(LLMCapabilityError, match="does not support reasoning"):
            worker._build_thinking_config(inference_model=worker.inference_model, job_params=job_params, max_tokens=100000)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

    def test_explicit_budget_capped_by_max_tokens(self, mocker: MockerFixture):
        """Explicit reasoning_budget is capped to leave a quarter of max_tokens for the answer."""
        worker = _make_worker(mocker, thinking_mode=ThinkingMode.MANUAL)
        job_params = LLMJobParams(temperature=0.5, reasoning_budget=8192)
        result = worker._build_thinking_config(inference_model=worker.inference_model, job_params=job_params, max_tokens=4000)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
        assert result is not None
        assert result.thinking_budget == 3000

    def test_effort_budget_capped_by_max_tokens(self, mocker: MockerFixture):
        """Effort-resolved budget is capped to leave a quarter of max_tokens for the answer when max_tokens is small."""
        worker = _make_worker(mocker, thinking_mode=ThinkingMode.MANUAL)
        google_config = GoogleConfig(effort_to_level_map=_GOOGLE_LEVEL_MAP)
        mocker.patch(
            "pipelex.providers.google.google_llm_worker.get_config",
            return_value=mocker.MagicMock(
                inference=mocker.MagicMock(
                    llm=mocker.MagicMock(
                        get_reasoning_budget=mocker.MagicMock(return_value=16384),
                        google=google_config,
                    ),
                ),
            ),
        )
        job_params = LLMJobParams(temperature=0.5, reasoning_effort=ReasoningEffort.HIGH)
        result = worker._build_thinking_config(inference_model=worker.inference_model, job_params=job_params, max_tokens=2000)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
        assert result is not None
        assert result.thinking_budget == 1500

    @pytest.mark.parametrize(
        ("min_thinking_budget", "max_thinking_budget", "reasoning_budget", "max_tokens", "expected_budget"),
        [
            # gemini-2.5-flash-lite takes 512 to 24576: a budget under it is raised to it
            (512, 24576, 200, 100000, 512),
            # and a max_tokens of 800 leaves 600 after the answer reserve, inside the range
            (512, 24576, 1024, 800, 600),
            # gemini-2.5-pro takes 128 to 32768
            (128, 32768, 64, 100000, 128),
            # gemini-2.5-flash takes at most 24576, with or without a max_tokens to fit in
            (None, 24576, 32768, None, 24576),
            (None, 24576, 65536, 100000, 24576),
        ],
    )
    def test_explicit_budget_held_within_the_model_bounds(
        self,
        mocker: MockerFixture,
        min_thinking_budget: int | None,
        max_thinking_budget: int | None,
        reasoning_budget: int,
        max_tokens: int | None,
        expected_budget: int,
    ):
        worker = _make_worker(
            mocker, thinking_mode=ThinkingMode.MANUAL, min_thinking_budget=min_thinking_budget, max_thinking_budget=max_thinking_budget
        )
        job_params = LLMJobParams(temperature=0.5, reasoning_budget=reasoning_budget)
        result = worker._build_thinking_config(inference_model=worker.inference_model, job_params=job_params, max_tokens=max_tokens)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
        assert result is not None
        assert result.thinking_budget == expected_budget

    def test_effort_budget_without_max_tokens_is_cut_to_the_model_maximum(self, mocker: MockerFixture):
        """`max` effort's 65,536 is beyond every Gemini 2.5 model, so a model's declared maximum applies when no max_tokens is set."""
        worker = _make_worker(mocker, thinking_mode=ThinkingMode.MANUAL, min_thinking_budget=128, max_thinking_budget=32768)
        google_config = GoogleConfig(effort_to_level_map=_GOOGLE_LEVEL_MAP)
        mocker.patch(
            "pipelex.providers.google.google_llm_worker.get_config",
            return_value=mocker.MagicMock(
                inference=mocker.MagicMock(
                    llm=mocker.MagicMock(
                        get_reasoning_budget=mocker.MagicMock(return_value=65536),
                        google=google_config,
                    ),
                ),
            ),
        )
        job_params = LLMJobParams(temperature=0.5, reasoning_effort=ReasoningEffort.MAX)
        result = worker._build_thinking_config(inference_model=worker.inference_model, job_params=job_params, max_tokens=None)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
        assert result is not None
        assert result.thinking_budget == 32768

    def test_max_tokens_too_small_for_the_model_minimum_is_refused(self, mocker: MockerFixture):
        """gemini-2.5-flash-lite takes no budget under 512, and 600 output tokens leave 450 after the answer reserve."""
        worker = _make_worker(mocker, thinking_mode=ThinkingMode.MANUAL, min_thinking_budget=512, max_thinking_budget=24576)
        job_params = LLMJobParams(temperature=0.5, reasoning_budget=1024)
        with pytest.raises(LLMCapabilityError, match="max_tokens=600"):
            worker._build_thinking_config(inference_model=worker.inference_model, job_params=job_params, max_tokens=600)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
