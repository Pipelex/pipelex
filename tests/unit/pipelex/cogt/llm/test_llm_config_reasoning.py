import pytest
from pydantic import ValidationError

from pipelex.cogt.config_cogt import LLMConfig
from pipelex.cogt.llm.llm_job_components import ReasoningEffort
from pipelex.system.exceptions import ConfigValidationError

_DEFAULT_EFFORT_TO_BUDGET_MAPS: dict[str, dict[str, int]] = {
    "anthropic": {"none": 0, "minimal": 512, "low": 1024, "medium": 5000, "high": 16384, "xhigh": 32768, "max": 65536},
    "gemini": {"none": 0, "minimal": 512, "low": 1024, "medium": 5000, "high": 16384, "xhigh": 32768, "max": 65536},
}

_DEFAULT_OPENAI_LEVEL_MAP: dict[str, str] = {
    "none": "none",
    "minimal": "minimal",
    "low": "low",
    "medium": "medium",
    "high": "high",
    "xhigh": "xhigh",
    "max": "xhigh",
}

_DEFAULT_ANTHROPIC_LEVEL_MAP: dict[str, str] = {
    "none": "disabled",
    "minimal": "low",
    "low": "low",
    "medium": "medium",
    "high": "high",
    "xhigh": "xhigh",
    "max": "max",
}

_DEFAULT_GOOGLE_LEVEL_MAP: dict[str, str] = {
    "none": "disabled",
    "minimal": "minimal",
    "low": "low",
    "medium": "medium",
    "high": "high",
    "xhigh": "high",
    "max": "high",
}

_DEFAULT_MISTRAL_LEVEL_MAP: dict[str, str] = {
    "none": "disabled",
    "minimal": "reasoning",
    "low": "reasoning",
    "medium": "reasoning",
    "high": "reasoning",
    "xhigh": "reasoning",
    "max": "reasoning",
}


def _make_llm_config(
    effort_to_budget_maps: dict[str, dict[str, int]] | None = None,
    openai_level_map: dict[str, str] | None = None,
    anthropic_level_map: dict[str, str] | None = None,
    google_level_map: dict[str, str] | None = None,
    mistral_level_map: dict[str, str] | None = None,
    schema_reask_max_attempts: int = 3,
) -> LLMConfig:
    """Helper to build a minimal LLMConfig for testing."""
    maps: dict[str, dict[str, int]] = _DEFAULT_EFFORT_TO_BUDGET_MAPS if effort_to_budget_maps is None else effort_to_budget_maps
    return LLMConfig(
        instructor={  # type: ignore[arg-type]
            "is_dump_kwargs_enabled": False,
            "is_dump_response_enabled": False,
            "is_dump_error_enabled": False,
        },
        openai={"effort_to_level_map": openai_level_map or _DEFAULT_OPENAI_LEVEL_MAP},  # type: ignore[arg-type]
        anthropic={  # type: ignore[arg-type]
            "structured_output_timeout_seconds": 1200,
            "effort_to_level_map": anthropic_level_map or _DEFAULT_ANTHROPIC_LEVEL_MAP,
        },
        google={"effort_to_level_map": google_level_map or _DEFAULT_GOOGLE_LEVEL_MAP},  # type: ignore[arg-type]
        mistral={"effort_to_level_map": mistral_level_map or _DEFAULT_MISTRAL_LEVEL_MAP},  # type: ignore[arg-type]
        schema_reask_max_attempts=schema_reask_max_attempts,
        is_structure_prompt_enabled=True,
        default_max_images=100,
        is_dump_text_prompts_enabled=False,
        is_dump_response_text_enabled=False,
        generic_templates={},
        effort_to_budget_maps=maps,
    )


class TestLLMConfigReasoning:
    """Tests for LLMConfig validation: effort budget maps, reasoning-level lookup, and schema_reask_max_attempts bounds."""

    def test_get_reasoning_budget_valid(self):
        config = _make_llm_config()
        assert config.get_reasoning_budget(family="anthropic", effort=ReasoningEffort.HIGH) == 16384

    def test_get_reasoning_budget_none_effort(self):
        config = _make_llm_config()
        assert config.get_reasoning_budget(family="gemini", effort=ReasoningEffort.NONE) == 0

    def test_get_reasoning_budget_max_effort(self):
        config = _make_llm_config()
        assert config.get_reasoning_budget(family="anthropic", effort=ReasoningEffort.MAX) == 65536

    def test_get_reasoning_budget_unknown_family_raises(self):
        config = _make_llm_config()
        with pytest.raises(ConfigValidationError, match="No effort-to-budget map found"):
            config.get_reasoning_budget(family="unknown_family", effort=ReasoningEffort.HIGH)

    def test_validator_missing_effort_level_raises(self):
        incomplete_maps = {
            "anthropic": {"none": 0, "low": 1024, "medium": 5000, "high": 16384},
            # missing "minimal" and "max"
        }
        with pytest.raises(ConfigValidationError, match="Missing reasoning effort levels"):
            _make_llm_config(effort_to_budget_maps=incomplete_maps)

    def test_validator_invalid_effort_level_raises(self):
        invalid_maps = {
            "anthropic": {"none": 0, "minimal": 512, "low": 1024, "medium": 5000, "high": 16384, "xhigh": 32768, "max": 65536, "ultra": 999999},
        }
        with pytest.raises(ConfigValidationError, match="Invalid reasoning effort levels"):
            _make_llm_config(effort_to_budget_maps=invalid_maps)

    def test_validator_missing_and_invalid_effort_levels_raises(self):
        bad_maps = {
            "anthropic": {"none": 0, "low": 1024, "medium": 5000, "high": 16384, "ultra": 999999},
            # missing "minimal" and "max", invalid "ultra"
        }
        with pytest.raises(ConfigValidationError, match=r"Missing.*and invalid"):
            _make_llm_config(effort_to_budget_maps=bad_maps)

    def test_validator_empty_maps_is_valid(self):
        """An empty dict of maps is valid — no targets means nothing to validate."""
        config = _make_llm_config(effort_to_budget_maps={})
        assert config.effort_to_budget_maps == {}

    @pytest.mark.parametrize("invalid_attempts", [0, 11, -1])
    def test_schema_reask_max_attempts_out_of_range_raises(self, invalid_attempts: int):
        """schema_reask_max_attempts outside ge=1/le=10 is rejected when the config is built, not deferred to runtime."""
        with pytest.raises(ValidationError, match="schema_reask_max_attempts"):
            _make_llm_config(schema_reask_max_attempts=invalid_attempts)

    @pytest.mark.parametrize(
        "effort",
        [
            ReasoningEffort.NONE,
            ReasoningEffort.MINIMAL,
            ReasoningEffort.LOW,
            ReasoningEffort.MEDIUM,
            ReasoningEffort.HIGH,
            ReasoningEffort.XHIGH,
            ReasoningEffort.MAX,
        ],
    )
    def test_all_effort_levels_retrievable(self, effort: ReasoningEffort):
        config = _make_llm_config()
        budget = config.get_reasoning_budget(family="anthropic", effort=effort)
        assert isinstance(budget, int)
        assert budget >= 0

    # --- effort_to_level_map tests ---

    def test_get_reasoning_level_openai_high(self):
        """OpenAI HIGH maps to 'high'."""
        config = _make_llm_config()
        assert config.openai.get_reasoning_level(ReasoningEffort.HIGH) == "high"

    def test_get_reasoning_level_openai_none_returns_string(self):
        """OpenAI NONE returns 'none' (a valid API value), not None."""
        config = _make_llm_config()
        result = config.openai.get_reasoning_level(ReasoningEffort.NONE)
        assert result == "none"

    def test_get_reasoning_level_openai_max_returns_xhigh(self):
        """OpenAI MAX maps to 'xhigh'."""
        config = _make_llm_config()
        assert config.openai.get_reasoning_level(ReasoningEffort.MAX) == "xhigh"

    def test_get_reasoning_level_anthropic_disabled(self):
        """Anthropic NONE returns None (disabled)."""
        config = _make_llm_config()
        assert config.anthropic.get_reasoning_level(ReasoningEffort.NONE) is None

    def test_get_reasoning_level_anthropic_high(self):
        """Anthropic HIGH maps to 'high'."""
        config = _make_llm_config()
        assert config.anthropic.get_reasoning_level(ReasoningEffort.HIGH) == "high"

    def test_get_reasoning_level_google_disabled(self):
        """Google NONE returns None (disabled)."""
        config = _make_llm_config()
        assert config.google.get_reasoning_level(ReasoningEffort.NONE) is None

    def test_get_reasoning_level_mistral_reasoning(self):
        """Mistral HIGH maps to 'reasoning'."""
        config = _make_llm_config()
        assert config.mistral.get_reasoning_level(ReasoningEffort.HIGH) == "reasoning"

    def test_get_reasoning_level_mistral_disabled(self):
        """Mistral NONE returns None (disabled)."""
        config = _make_llm_config()
        assert config.mistral.get_reasoning_level(ReasoningEffort.NONE) is None

    def test_level_validator_missing_effort_raises(self):
        """Level map missing some effort keys should raise ConfigValidationError."""
        incomplete_level_map = {"none": "none", "low": "low", "medium": "medium"}
        with pytest.raises(ConfigValidationError, match="Missing reasoning effort levels"):
            LLMConfig(
                instructor={  # type: ignore[arg-type]
                    "is_dump_kwargs_enabled": False,
                    "is_dump_response_enabled": False,
                    "is_dump_error_enabled": False,
                },
                openai={"effort_to_level_map": incomplete_level_map},  # type: ignore[arg-type]
                anthropic={  # type: ignore[arg-type]
                    "structured_output_timeout_seconds": 1200,
                    "effort_to_level_map": _DEFAULT_ANTHROPIC_LEVEL_MAP,
                },
                google={"effort_to_level_map": _DEFAULT_GOOGLE_LEVEL_MAP},  # type: ignore[arg-type]
                mistral={"effort_to_level_map": _DEFAULT_MISTRAL_LEVEL_MAP},  # type: ignore[arg-type]
                schema_reask_max_attempts=3,
                is_structure_prompt_enabled=True,
                default_max_images=100,
                is_dump_text_prompts_enabled=False,
                is_dump_response_text_enabled=False,
                generic_templates={},
                effort_to_budget_maps={},
            )

    def test_level_validator_invalid_effort_raises(self):
        """Level map with unknown effort keys should raise ConfigValidationError."""
        invalid_level_map = {
            "none": "none",
            "minimal": "minimal",
            "low": "low",
            "medium": "medium",
            "high": "high",
            "xhigh": "xhigh",
            "max": "xhigh",
            "ultra": "super",
        }
        with pytest.raises(ConfigValidationError, match="Invalid reasoning effort levels"):
            LLMConfig(
                instructor={  # type: ignore[arg-type]
                    "is_dump_kwargs_enabled": False,
                    "is_dump_response_enabled": False,
                    "is_dump_error_enabled": False,
                },
                openai={"effort_to_level_map": invalid_level_map},  # type: ignore[arg-type]
                anthropic={  # type: ignore[arg-type]
                    "structured_output_timeout_seconds": 1200,
                    "effort_to_level_map": _DEFAULT_ANTHROPIC_LEVEL_MAP,
                },
                google={"effort_to_level_map": _DEFAULT_GOOGLE_LEVEL_MAP},  # type: ignore[arg-type]
                mistral={"effort_to_level_map": _DEFAULT_MISTRAL_LEVEL_MAP},  # type: ignore[arg-type]
                schema_reask_max_attempts=3,
                is_structure_prompt_enabled=True,
                default_max_images=100,
                is_dump_text_prompts_enabled=False,
                is_dump_response_text_enabled=False,
                generic_templates={},
                effort_to_budget_maps={},
            )

    # --- level value validation tests ---

    def test_openai_invalid_level_value_rejected(self):
        """OpenAI map with an invalid level value (not in OpenAIReasoningLevel) should raise."""
        bad_map = {**_DEFAULT_OPENAI_LEVEL_MAP, "max": "turbo"}
        with pytest.raises(ConfigValidationError, match="Invalid level value 'turbo'"):
            _make_llm_config(openai_level_map=bad_map)

    def test_anthropic_invalid_level_value_rejected(self):
        """Anthropic map with an invalid level value (not in AnthropicEffortLevel) should raise."""
        bad_map = {**_DEFAULT_ANTHROPIC_LEVEL_MAP, "high": "extreme"}
        with pytest.raises(ConfigValidationError, match="Invalid level value 'extreme'"):
            _make_llm_config(anthropic_level_map=bad_map)

    def test_google_invalid_level_value_rejected(self):
        """Google map with an invalid level value (not in GoogleThinkingLevel) should raise."""
        bad_map = {**_DEFAULT_GOOGLE_LEVEL_MAP, "max": "ultra"}
        with pytest.raises(ConfigValidationError, match="Invalid level value 'ultra'"):
            _make_llm_config(google_level_map=bad_map)

    def test_mistral_invalid_level_value_rejected(self):
        """Mistral map with an invalid level value (not in MistralReasoningLevel) should raise."""
        bad_map = {**_DEFAULT_MISTRAL_LEVEL_MAP, "high": "thinking"}
        with pytest.raises(ConfigValidationError, match="Invalid level value 'thinking'"):
            _make_llm_config(mistral_level_map=bad_map)

    def test_disabled_level_value_always_accepted(self):
        """The 'disabled' value should be accepted by all providers without raising."""
        all_disabled_map: dict[str, str] = {
            "none": "disabled",
            "minimal": "disabled",
            "low": "disabled",
            "medium": "disabled",
            "high": "disabled",
            "xhigh": "disabled",
            "max": "disabled",
        }
        config = _make_llm_config(
            anthropic_level_map=all_disabled_map,
            google_level_map=all_disabled_map,
            mistral_level_map=all_disabled_map,
        )
        assert config.anthropic.get_reasoning_level(ReasoningEffort.HIGH) is None
        assert config.google.get_reasoning_level(ReasoningEffort.HIGH) is None
        assert config.mistral.get_reasoning_level(ReasoningEffort.HIGH) is None
