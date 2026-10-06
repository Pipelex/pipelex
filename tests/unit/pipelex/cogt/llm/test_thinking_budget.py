import pytest

from pipelex.cogt.exceptions import LLMCapabilityError
from pipelex.cogt.llm.thinking_budget import fit_thinking_budget


class TestFitThinkingBudget:
    """A manual thinking budget is fitted inside max_tokens, leaving a quarter of it for the answer, and held within the model's bounds."""

    def test_a_budget_within_the_ceiling_passes_through(self):
        assert fit_thinking_budget(budget=5000, max_tokens=64000, min_budget=None, max_budget=None, model_desc="test-model") == 5000

    def test_a_budget_at_the_ceiling_passes_through(self):
        assert fit_thinking_budget(budget=3000, max_tokens=4000, min_budget=None, max_budget=None, model_desc="test-model") == 3000

    def test_a_budget_over_the_ceiling_is_cut_to_max_tokens_minus_the_reserve(self):
        assert fit_thinking_budget(budget=16384, max_tokens=2000, min_budget=None, max_budget=None, model_desc="test-model") == 1500

    def test_the_timeout_capped_anthropic_structured_call_leaves_a_quarter_for_the_answer(self):
        """The structured Anthropic path caps max_tokens at 42,666 for its timeout, and `max` effort asks 65,536."""
        assert fit_thinking_budget(budget=65536, max_tokens=42666, min_budget=1024, max_budget=None, model_desc="test-model") == 32000

    def test_a_budget_under_the_floor_is_raised_to_it(self):
        assert fit_thinking_budget(budget=512, max_tokens=64000, min_budget=1024, max_budget=None, model_desc="test-model") == 1024

    def test_the_floor_holds_when_the_ceiling_is_exactly_the_floor(self):
        # 1365 // 4 = 341 reserved, leaving 1024 for thinking
        assert fit_thinking_budget(budget=16384, max_tokens=1365, min_budget=1024, max_budget=None, model_desc="test-model") == 1024

    def test_a_max_tokens_that_cannot_hold_the_floor_and_the_reserve_is_refused(self):
        with pytest.raises(LLMCapabilityError) as exc_info:
            fit_thinking_budget(budget=1024, max_tokens=1200, min_budget=1024, max_budget=None, model_desc="test-model")
        message = str(exc_info.value)
        assert "test-model" in message
        assert "max_tokens=1200" in message
        assert "1024" in message
        assert "300" in message

    def test_without_a_floor_a_small_max_tokens_cuts_the_budget_without_refusing(self):
        """A model that declares no minimum, such as Gemini 2.5 Flash, has its budget cut rather than refused."""
        assert fit_thinking_budget(budget=1024, max_tokens=100, min_budget=None, max_budget=None, model_desc="test-model") == 75

    def test_a_tiny_max_tokens_still_keeps_a_token_for_the_answer(self):
        """A quarter of max_tokens rounds down to nothing below 4, so the reserve is never less than one token."""
        assert fit_thinking_budget(budget=5000, max_tokens=3, min_budget=None, max_budget=None, model_desc="test-model") == 2

    def test_a_max_tokens_with_no_room_to_think_is_refused_without_a_floor(self):
        with pytest.raises(LLMCapabilityError) as exc_info:
            fit_thinking_budget(budget=5000, max_tokens=1, min_budget=None, max_budget=None, model_desc="test-model")
        assert "max_tokens=1" in str(exc_info.value)

    def test_a_budget_over_the_model_maximum_is_cut_to_it(self):
        assert fit_thinking_budget(budget=65536, max_tokens=100000, min_budget=128, max_budget=32768, model_desc="test-model") == 32768

    def test_without_max_tokens_only_the_model_bounds_apply(self):
        assert fit_thinking_budget(budget=65536, max_tokens=None, min_budget=None, max_budget=24576, model_desc="test-model") == 24576
        assert fit_thinking_budget(budget=200, max_tokens=None, min_budget=512, max_budget=24576, model_desc="test-model") == 512
        assert fit_thinking_budget(budget=8192, max_tokens=None, min_budget=None, max_budget=None, model_desc="test-model") == 8192

    def test_the_answer_reserve_cuts_below_the_model_maximum(self):
        assert fit_thinking_budget(budget=32768, max_tokens=8000, min_budget=128, max_budget=32768, model_desc="test-model") == 6000
