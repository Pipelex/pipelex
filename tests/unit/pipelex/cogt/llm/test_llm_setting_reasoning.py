import pytest
from pydantic import ValidationError

from pipelex.cogt.llm.llm_job_components import ReasoningEffort
from pipelex.cogt.llm.llm_setting import LLMSetting


class TestLLMSettingReasoning:
    """Tests for reasoning_effort and reasoning_budget mutual exclusivity and pass-through."""

    def test_both_none_is_valid(self):
        setting = LLMSetting(
            model="test-model",
            temperature=0.5,
        )
        assert setting.reasoning_effort is None
        assert setting.reasoning_budget is None

    def test_reasoning_effort_alone_is_valid(self):
        setting = LLMSetting(
            model="test-model",
            temperature=0.5,
            reasoning_effort=ReasoningEffort.HIGH,
        )
        assert setting.reasoning_effort == ReasoningEffort.HIGH
        assert setting.reasoning_budget is None

    def test_reasoning_budget_alone_is_valid(self):
        setting = LLMSetting(
            model="test-model",
            temperature=0.5,
            reasoning_budget=16384,
        )
        assert setting.reasoning_effort is None
        assert setting.reasoning_budget == 16384

    def test_both_set_raises_error(self):
        with pytest.raises(ValidationError, match="cannot have both"):
            LLMSetting(
                model="test-model",
                temperature=0.5,
                reasoning_effort=ReasoningEffort.HIGH,
                reasoning_budget=16384,
            )

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
    def test_all_effort_values_accepted(self, effort: ReasoningEffort):
        setting = LLMSetting(
            model="test-model",
            temperature=0.5,
            reasoning_effort=effort,
        )
        assert setting.reasoning_effort == effort

    def test_make_llm_job_params_passes_reasoning_effort(self):
        setting = LLMSetting(
            model="test-model",
            temperature=0.5,
            reasoning_effort=ReasoningEffort.HIGH,
        )
        params = setting.make_llm_job_params()
        assert params.reasoning_effort == ReasoningEffort.HIGH
        assert params.reasoning_budget is None

    def test_make_llm_job_params_passes_reasoning_budget(self):
        setting = LLMSetting(
            model="test-model",
            temperature=0.5,
            reasoning_budget=8192,
        )
        params = setting.make_llm_job_params()
        assert params.reasoning_effort is None
        assert params.reasoning_budget == 8192

    def test_make_llm_job_params_passes_none_reasoning(self):
        setting = LLMSetting(
            model="test-model",
            temperature=0.5,
        )
        params = setting.make_llm_job_params()
        assert params.reasoning_effort is None
        assert params.reasoning_budget is None

    def test_desc_includes_reasoning_effort(self):
        setting = LLMSetting(
            model="test-model",
            temperature=0.5,
            reasoning_effort=ReasoningEffort.HIGH,
        )
        desc = setting.desc()
        assert "reasoning_effort=high" in desc

    def test_desc_includes_reasoning_budget(self):
        setting = LLMSetting(
            model="test-model",
            temperature=0.5,
            reasoning_budget=16384,
        )
        desc = setting.desc()
        assert "reasoning_budget=16384" in desc

    def test_desc_omits_reasoning_when_none(self):
        setting = LLMSetting(
            model="test-model",
            temperature=0.5,
        )
        desc = setting.desc()
        assert "reasoning_effort" not in desc
        assert "reasoning_budget" not in desc
