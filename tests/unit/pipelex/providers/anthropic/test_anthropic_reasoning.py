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


def _make_worker(mocker: MockerFixture, thinking_mode: ThinkingMode, *, min_thinking_budget: int | None = 1024) -> AnthropicLLMWorker:
    """Create a minimal AnthropicLLMWorker with a mocked inference_model, by default declaring Anthropic's minimum budget."""
    worker = object.__new__(AnthropicLLMWorker)
    worker.extras_factory = None
    mock_model = mocker.MagicMock()
    mock_model.thinking_mode = thinking_mode
    mock_model.desc = "test-model"
    mock_model.min_thinking_budget = min_thinking_budget
    mock_model.max_thinking_budget = None
    worker.inference_model = mock_model
    return worker


def _mock_config(mocker: MockerFixture, budget_mock: object | None = None) -> None:
    """Mock get_config() with a real anthropic_config and an optional get_reasoning_budget mock."""
    anthropic_config = AnthropicConfig(structured_output_timeout_seconds=1200, effort_to_level_map=_ANTHROPIC_LEVEL_MAP)
    llm_config = mocker.MagicMock(anthropic=anthropic_config)
    if budget_mock is not None:
        llm_config.get_reasoning_budget = budget_mock
    mocker.patch(
        "pipelex.providers.anthropic.anthropic_llm_worker.get_config",
        return_value=mocker.MagicMock(inference=mocker.MagicMock(llm=llm_config)),
    )


class TestAnthropicReasoning:
    """Tests for _build_thinking_params on AnthropicLLMWorker."""

    @pytest.mark.parametrize(
        ("effort", "expected_budget"),
        [
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
        result = worker._build_thinking_params(inference_model=worker.inference_model, job_params=job_params, max_tokens=100000)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
        assert result.thinking == {"type": "enabled", "budget_tokens": expected_budget}
        assert result.suppress_temperature is True
        budget_mock.assert_called_once_with(family="anthropic", effort=effort)

    def test_manual_mode_budget_under_the_minimum_is_raised_to_it(self, mocker: MockerFixture):
        """Anthropic refuses a budget_tokens below 1,024, so the 512 that MINIMAL maps to is raised to 1,024."""
        worker = _make_worker(mocker, thinking_mode=ThinkingMode.MANUAL)
        _mock_config(mocker, budget_mock=mocker.MagicMock(return_value=512))
        job_params = LLMJobParams(temperature=0.5, reasoning_effort=ReasoningEffort.MINIMAL)
        result = worker._build_thinking_params(inference_model=worker.inference_model, job_params=job_params, max_tokens=100000)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
        assert result.thinking == {"type": "enabled", "budget_tokens": 1024}

    def test_explicit_budget_under_the_minimum_is_raised_to_it(self, mocker: MockerFixture):
        worker = _make_worker(mocker, thinking_mode=ThinkingMode.MANUAL)
        job_params = LLMJobParams(temperature=0.5, reasoning_budget=200)
        result = worker._build_thinking_params(inference_model=worker.inference_model, job_params=job_params, max_tokens=100000)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
        assert result.thinking == {"type": "enabled", "budget_tokens": 1024}

    def test_max_tokens_too_small_for_the_minimum_budget_is_refused(self, mocker: MockerFixture):
        """1,200 output tokens leave 900 for thinking after the answer reserve, under Anthropic's minimum of 1,024."""
        worker = _make_worker(mocker, thinking_mode=ThinkingMode.MANUAL)
        _mock_config(mocker, budget_mock=mocker.MagicMock(return_value=1024))
        job_params = LLMJobParams(temperature=0.5, reasoning_effort=ReasoningEffort.LOW)
        with pytest.raises(LLMCapabilityError, match="max_tokens=1200"):
            worker._build_thinking_params(inference_model=worker.inference_model, job_params=job_params, max_tokens=1200)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

    @pytest.mark.parametrize("is_structured", [False, True])
    @pytest.mark.parametrize(
        ("job_max_tokens", "model_max_tokens"),
        [
            pytest.param(1200, 64000, id="the_job_s_max_tokens"),
            pytest.param(None, 1200, id="the_model_s_max_tokens"),
        ],
    )
    def test_check_request_fits_the_budget_against_the_max_tokens_the_call_sends(
        self, mocker: MockerFixture, is_structured: bool, job_max_tokens: int | None, model_max_tokens: int
    ):
        """The request check refuses what the call would: a minimum budget the call's max_tokens cannot hold beside the answer."""
        worker = _make_worker(mocker, thinking_mode=ThinkingMode.MANUAL)
        worker.inference_model.max_tokens = model_max_tokens
        _mock_config(mocker, budget_mock=mocker.MagicMock(return_value=1024))
        job_params = LLMJobParams(temperature=0.5, max_tokens=job_max_tokens, reasoning_effort=ReasoningEffort.LOW)
        with pytest.raises(LLMCapabilityError, match="max_tokens=1200"):
            AnthropicLLMWorker.check_request(inference_model=worker.inference_model, job_params=job_params, is_structured=is_structured)

    def test_check_request_without_any_max_tokens_fits_no_budget(self, mocker: MockerFixture):
        """A model declaring no max_tokens cannot be built a worker for, so its check fits no budget and leaves the refusal to the build."""
        worker = _make_worker(mocker, thinking_mode=ThinkingMode.MANUAL)
        worker.inference_model.max_tokens = None
        _mock_config(mocker, budget_mock=mocker.MagicMock(return_value=65536))
        job_params = LLMJobParams(temperature=0.5, reasoning_effort=ReasoningEffort.MAX)
        AnthropicLLMWorker.check_request(inference_model=worker.inference_model, job_params=job_params, is_structured=True)

    @pytest.mark.parametrize(
        ("is_structured", "expected_max_tokens"),
        [
            pytest.param(False, 64000, id="text_sends_what_it_asks"),
            pytest.param(True, 42666, id="structured_is_held_to_its_timeout"),
        ],
    )
    def test_a_structured_call_sends_the_max_tokens_its_timeout_allows(self, mocker: MockerFixture, is_structured: bool, expected_max_tokens: int):
        """A structured call's explicit 1,200-second timeout holds its max_tokens to what the SDK's heuristic lets that timeout produce."""
        _mock_config(mocker)
        sent_max_tokens = AnthropicLLMWorker._sent_max_tokens(requested_max_tokens=64000, is_structured=is_structured)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
        assert sent_max_tokens == expected_max_tokens

    def test_a_model_declaring_no_minimum_is_sent_the_fitted_budget(self, mocker: MockerFixture):
        """A server behind the anthropic SDK that declares no minimum, MiniMax among them, is neither raised nor refused."""
        worker = _make_worker(mocker, thinking_mode=ThinkingMode.MANUAL, min_thinking_budget=None)
        _mock_config(mocker, budget_mock=mocker.MagicMock(return_value=1024))
        job_params = LLMJobParams(temperature=0.5, reasoning_effort=ReasoningEffort.LOW)
        result = worker._build_thinking_params(inference_model=worker.inference_model, job_params=job_params, max_tokens=1200)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
        assert result.thinking == {"type": "enabled", "budget_tokens": 900}

    def test_manual_mode_effort_none_disables_thinking(self, mocker: MockerFixture):
        """MANUAL mode with NONE effort disables thinking entirely (no budget lookup)."""
        worker = _make_worker(mocker, thinking_mode=ThinkingMode.MANUAL)
        budget_mock = mocker.MagicMock()
        _mock_config(mocker, budget_mock=budget_mock)
        job_params = LLMJobParams(temperature=0.5, reasoning_effort=ReasoningEffort.NONE)
        result = worker._build_thinking_params(inference_model=worker.inference_model, job_params=job_params, max_tokens=100000)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
        assert result.thinking is None
        assert result.suppress_temperature is False
        budget_mock.assert_not_called()

    def test_effort_budget_capped_by_max_tokens(self, mocker: MockerFixture):
        """Effort-resolved budget is capped to leave a quarter of max_tokens for the answer when max_tokens is small."""
        worker = _make_worker(mocker, thinking_mode=ThinkingMode.MANUAL)
        budget_mock = mocker.MagicMock(return_value=16384)
        _mock_config(mocker, budget_mock=budget_mock)
        job_params = LLMJobParams(temperature=0.5, reasoning_effort=ReasoningEffort.HIGH)
        result = worker._build_thinking_params(inference_model=worker.inference_model, job_params=job_params, max_tokens=2000)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
        assert result.thinking == {"type": "enabled", "budget_tokens": 1500}

    def test_explicit_budget_passes_through(self, mocker: MockerFixture):
        """Explicit reasoning_budget passes through directly as budget_tokens in MANUAL mode."""
        worker = _make_worker(mocker, thinking_mode=ThinkingMode.MANUAL)
        job_params = LLMJobParams(temperature=0.5, reasoning_budget=8192)
        result = worker._build_thinking_params(inference_model=worker.inference_model, job_params=job_params, max_tokens=100000)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
        assert result.thinking == {"type": "enabled", "budget_tokens": 8192}
        assert result.suppress_temperature is True

    def test_thinking_mode_none_raises_capability_error(self, mocker: MockerFixture):
        """Models with thinking_mode=none should raise LLMCapabilityError on reasoning_effort."""
        worker = _make_worker(mocker, thinking_mode=ThinkingMode.NONE)
        job_params = LLMJobParams(temperature=0.5, reasoning_effort=ReasoningEffort.HIGH)
        with pytest.raises(LLMCapabilityError, match="does not support reasoning"):
            worker._build_thinking_params(inference_model=worker.inference_model, job_params=job_params, max_tokens=100000)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
