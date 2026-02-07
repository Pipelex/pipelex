import pytest

from pipelex.cogt.config_cogt import LLMConfig
from pipelex.cogt.llm.llm_job_components import LLMJobConfig, ReasoningEffort
from pipelex.system.exceptions import ConfigValidationError

_DEFAULT_EFFORT_TO_BUDGET_MAPS: dict[str, dict[str, int]] = {
    "anthropic": {"none": 0, "low": 1024, "medium": 5000, "high": 16384, "max": 65536},
    "gemini": {"none": 0, "low": 1024, "medium": 5000, "high": 16384, "max": 65536},
}


def _make_llm_config(effort_to_budget_maps: dict[str, dict[str, int]] | None = None) -> LLMConfig:
    """Helper to build a minimal LLMConfig for testing."""
    maps: dict[str, dict[str, int]] = _DEFAULT_EFFORT_TO_BUDGET_MAPS if effort_to_budget_maps is None else effort_to_budget_maps
    return LLMConfig(
        instructor_config={  # type: ignore[arg-type]
            "is_dump_kwargs_enabled": False,
            "is_dump_response_enabled": False,
            "is_dump_error_enabled": False,
        },
        anthropic_config={"structured_output_timeout_seconds": 1200},  # type: ignore[arg-type]
        llm_job_config=LLMJobConfig(max_retries=3),
        is_structure_prompt_enabled=True,
        default_max_images=100,
        is_dump_text_prompts_enabled=False,
        is_dump_response_text_enabled=False,
        generic_templates={},
        effort_to_budget_maps=maps,
    )


class TestLLMConfigReasoning:
    """Tests for effort_to_budget_maps validation and get_reasoning_budget."""

    def test_get_reasoning_budget_valid(self):
        config = _make_llm_config()
        assert config.get_reasoning_budget("anthropic", ReasoningEffort.HIGH) == 16384

    def test_get_reasoning_budget_none_effort(self):
        config = _make_llm_config()
        assert config.get_reasoning_budget("gemini", ReasoningEffort.NONE) == 0

    def test_get_reasoning_budget_max_effort(self):
        config = _make_llm_config()
        assert config.get_reasoning_budget("anthropic", ReasoningEffort.MAX) == 65536

    def test_get_reasoning_budget_unknown_target_raises(self):
        config = _make_llm_config()
        with pytest.raises(ConfigValidationError, match="No effort-to-budget map found"):
            config.get_reasoning_budget("unknown_target", ReasoningEffort.HIGH)

    def test_validator_missing_effort_level_raises(self):
        incomplete_maps = {
            "anthropic": {"none": 0, "low": 1024, "medium": 5000, "high": 16384},
            # missing "max"
        }
        with pytest.raises(ConfigValidationError, match="Missing reasoning effort levels"):
            _make_llm_config(effort_to_budget_maps=incomplete_maps)

    def test_validator_invalid_effort_level_raises(self):
        invalid_maps = {
            "anthropic": {"none": 0, "low": 1024, "medium": 5000, "high": 16384, "max": 65536, "ultra": 999999},
        }
        with pytest.raises(ConfigValidationError, match="Invalid reasoning effort levels"):
            _make_llm_config(effort_to_budget_maps=invalid_maps)

    def test_validator_missing_and_invalid_effort_levels_raises(self):
        bad_maps = {
            "anthropic": {"none": 0, "low": 1024, "medium": 5000, "high": 16384, "ultra": 999999},
            # missing "max", invalid "ultra"
        }
        with pytest.raises(ConfigValidationError, match=r"Missing.*and invalid"):
            _make_llm_config(effort_to_budget_maps=bad_maps)

    def test_validator_empty_maps_is_valid(self):
        """An empty dict of maps is valid — no targets means nothing to validate."""
        config = _make_llm_config(effort_to_budget_maps={})
        assert config.effort_to_budget_maps == {}

    @pytest.mark.parametrize(
        "effort",
        [
            ReasoningEffort.NONE,
            ReasoningEffort.LOW,
            ReasoningEffort.MEDIUM,
            ReasoningEffort.HIGH,
            ReasoningEffort.MAX,
        ],
    )
    def test_all_effort_levels_retrievable(self, effort: ReasoningEffort):
        config = _make_llm_config()
        budget = config.get_reasoning_budget("anthropic", effort)
        assert isinstance(budget, int)
        assert budget >= 0
