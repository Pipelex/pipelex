import pytest
from pydantic import ValidationError

from pipelex.cogt.llm.llm_job_components import LLMJobParams, ReasoningEffort


class TestLLMJobParamsReasoning:
    """Tests for reasoning_effort and reasoning_budget mutual exclusivity on LLMJobParams."""

    def test_both_none_is_valid(self):
        params = LLMJobParams(temperature=0.5)
        assert params.reasoning_effort is None
        assert params.reasoning_budget is None

    def test_reasoning_effort_alone_is_valid(self):
        params = LLMJobParams(temperature=0.5, reasoning_effort=ReasoningEffort.HIGH)
        assert params.reasoning_effort == ReasoningEffort.HIGH
        assert params.reasoning_budget is None

    def test_reasoning_budget_alone_is_valid(self):
        params = LLMJobParams(temperature=0.5, reasoning_budget=16384)
        assert params.reasoning_effort is None
        assert params.reasoning_budget == 16384

    def test_both_set_raises_error(self):
        with pytest.raises(ValidationError, match="cannot have both"):
            LLMJobParams(
                temperature=0.5,
                reasoning_effort=ReasoningEffort.HIGH,
                reasoning_budget=16384,
            )
