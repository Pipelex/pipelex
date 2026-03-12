"""Unit tests for the agent CLI pipe command — non-nominal / tolerance cases."""

from __future__ import annotations

from typing import Any, ClassVar

import pytest
from pydantic import ValidationError

from pipelex.builder.operations.pipe_ops import (
    LLM_TALENT_TO_MODEL,
    MODEL_TO_EXTRACT_TALENT,
    MODEL_TO_IMG_GEN_TALENT,
    MODEL_TO_LLM_TALENT,
    parse_pipe_spec,
    pipe_spec_to_toml,
    resolve_talent_value,
)

# ---------------------------------------------------------------------------
# Reverse talent mappings
# ---------------------------------------------------------------------------


class TestReverseTalentMappings:
    """Verify the module-level reverse mappings are built correctly."""

    def test_llm_preset_with_prefix(self) -> None:
        assert MODEL_TO_LLM_TALENT["$writing-creative"] == "creative-writer"

    def test_llm_preset_without_prefix(self) -> None:
        assert MODEL_TO_LLM_TALENT["writing-creative"] == "creative-writer"

    def test_llm_all_presets_have_reverse_entries(self) -> None:
        for talent, preset in LLM_TALENT_TO_MODEL.items():
            assert MODEL_TO_LLM_TALENT[preset] == talent or MODEL_TO_LLM_TALENT[preset] in LLM_TALENT_TO_MODEL
            assert MODEL_TO_LLM_TALENT[preset.lstrip("$@")] == talent or MODEL_TO_LLM_TALENT[preset.lstrip("$@")] in LLM_TALENT_TO_MODEL

    def test_img_gen_preset_with_prefix(self) -> None:
        assert MODEL_TO_IMG_GEN_TALENT["$gen-image"] == "gen-image"

    def test_img_gen_preset_without_prefix(self) -> None:
        assert MODEL_TO_IMG_GEN_TALENT["gen-image"] == "gen-image"

    def test_extract_preset_with_prefix(self) -> None:
        assert MODEL_TO_EXTRACT_TALENT["@default-text-from-pdf"] == "pdf-basic-text-extractor"

    def test_extract_preset_without_prefix(self) -> None:
        assert MODEL_TO_EXTRACT_TALENT["default-text-from-pdf"] == "pdf-basic-text-extractor"


# ---------------------------------------------------------------------------
# resolve_talent_value
# ---------------------------------------------------------------------------


class TestResolveTalentValue:
    """Tests for the preset-to-talent resolution helper."""

    # --- PipeLLM ---

    def test_valid_talent_passes_through(self) -> None:
        assert resolve_talent_value("PipeLLM", "creative-writer") == "creative-writer"

    def test_preset_without_prefix_resolves(self) -> None:
        assert resolve_talent_value("PipeLLM", "writing-creative") == "creative-writer"

    def test_preset_with_dollar_prefix_resolves(self) -> None:
        assert resolve_talent_value("PipeLLM", "$writing-creative") == "creative-writer"

    def test_invalid_talent_passes_through(self) -> None:
        """Unknown values pass through so Pydantic can produce a clear error."""
        assert resolve_talent_value("PipeLLM", "totally-wrong") == "totally-wrong"

    def test_engineering_code_resolves(self) -> None:
        assert resolve_talent_value("PipeLLM", "engineering-code") == "coder"

    def test_retrieval_resolves(self) -> None:
        assert resolve_talent_value("PipeLLM", "retrieval") == "data-retrieval"

    # --- PipeImgGen ---

    def test_img_gen_preset_resolves(self) -> None:
        assert resolve_talent_value("PipeImgGen", "$gen-image-fast") == "gen-image-fast"

    def test_img_gen_valid_talent_passes_through(self) -> None:
        assert resolve_talent_value("PipeImgGen", "gen-image-high-quality") == "gen-image-high-quality"

    # --- PipeExtract ---

    def test_extract_preset_resolves(self) -> None:
        assert resolve_talent_value("PipeExtract", "default-extract-document") == "full-document-extractor"

    def test_extract_preset_with_at_resolves(self) -> None:
        assert resolve_talent_value("PipeExtract", "@default-extract-image") == "image-text-extractor"

    # --- Unknown pipe types ---

    def test_unknown_pipe_type_passes_through(self) -> None:
        assert resolve_talent_value("PipeCompose", "anything") == "anything"

    def test_pipe_search_passes_through(self) -> None:
        """PipeSearch has no reverse mapping; values pass through."""
        assert resolve_talent_value("PipeSearch", "web-search") == "web-search"

    def test_dict_value_passes_through(self) -> None:
        """Non-string values (dict) should pass through without crashing."""
        result = resolve_talent_value("PipeLLM", {"name": "creative-writer"})
        assert result == {"name": "creative-writer"}

    def test_list_value_passes_through(self) -> None:
        """Non-string values (list) should pass through without crashing."""
        result = resolve_talent_value("PipeLLM", ["creative-writer"])
        assert result == ["creative-writer"]

    def test_int_value_passes_through(self) -> None:
        """Non-string values (int) should pass through without crashing."""
        result = resolve_talent_value("PipeLLM", 42)
        assert result == 42


# ---------------------------------------------------------------------------
# parse_pipe_spec — pipe_code aliases
# ---------------------------------------------------------------------------


class TestPipeCodeAliases:
    """The parser should accept 'code', 'the_pipe_code', and 'name' as aliases for 'pipe_code'."""

    _BASE_LLM: ClassVar[dict[str, Any]] = {
        "description": "Test pipe",
        "llm_talent": "creative-writer",
        "inputs": {"text": "Text"},
        "output": "Text",
        "prompt": "Write something about @text",
    }

    def test_canonical_pipe_code(self) -> None:
        spec = {**self._BASE_LLM, "pipe_code": "my_pipe"}
        result = parse_pipe_spec("PipeLLM", spec)
        assert result.pipe_code == "my_pipe"

    def test_alias_code(self) -> None:
        spec = {**self._BASE_LLM, "code": "my_pipe"}
        result = parse_pipe_spec("PipeLLM", spec)
        assert result.pipe_code == "my_pipe"

    def test_alias_the_pipe_code(self) -> None:
        spec = {**self._BASE_LLM, "the_pipe_code": "my_pipe"}
        result = parse_pipe_spec("PipeLLM", spec)
        assert result.pipe_code == "my_pipe"

    def test_alias_name(self) -> None:
        spec = {**self._BASE_LLM, "name": "my_pipe"}
        result = parse_pipe_spec("PipeLLM", spec)
        assert result.pipe_code == "my_pipe"

    def test_canonical_ignores_alias(self) -> None:
        """When pipe_code is present, alias keys are removed so Pydantic doesn't reject them."""
        spec = {**self._BASE_LLM, "pipe_code": "canonical", "code": "alias"}
        result = parse_pipe_spec("PipeLLM", spec)
        assert result.pipe_code == "canonical"

    def test_multiple_aliases_all_cleaned_up(self) -> None:
        """When pipe_code and multiple aliases are present, all aliases are removed."""
        spec = {**self._BASE_LLM, "code": "my_pipe", "name": "alt"}
        result = parse_pipe_spec("PipeLLM", spec)
        assert result.pipe_code == "my_pipe"

    def test_three_aliases_all_cleaned_up(self) -> None:
        """When pipe_code and all aliases are present, all aliases are removed."""
        spec = {**self._BASE_LLM, "code": "my_pipe", "the_pipe_code": "alt", "name": "alt2"}
        result = parse_pipe_spec("PipeLLM", spec)
        assert result.pipe_code == "my_pipe"


# ---------------------------------------------------------------------------
# parse_pipe_spec — talent field aliases
# ---------------------------------------------------------------------------


class TestTalentFieldAliases:
    """The parser should accept 'talent_name' and 'talent' as generic talent aliases."""

    _BASE: ClassVar[dict[str, Any]] = {
        "pipe_code": "test_pipe",
        "description": "Test pipe",
        "inputs": {"text": "Text"},
        "output": "Text",
        "prompt": "Write about @text",
    }

    def test_talent_name_alias_for_llm(self) -> None:
        spec = {**self._BASE, "talent_name": "creative-writer"}
        result = parse_pipe_spec("PipeLLM", spec)
        assert result.llm_talent == "creative-writer"  # type: ignore[attr-defined]

    def test_talent_alias_for_llm(self) -> None:
        spec = {**self._BASE, "talent": "engineer"}
        result = parse_pipe_spec("PipeLLM", spec)
        assert result.llm_talent == "engineer"  # type: ignore[attr-defined]

    def test_canonical_talent_field_ignores_alias(self) -> None:
        """When llm_talent is present, generic alias is removed so Pydantic doesn't reject it."""
        spec = {**self._BASE, "llm_talent": "coder", "talent_name": "engineer"}
        result = parse_pipe_spec("PipeLLM", spec)
        assert result.llm_talent == "coder"  # type: ignore[attr-defined]

    def test_talent_alias_for_extract(self) -> None:
        spec = {
            "pipe_code": "test_extract",
            "description": "Extract pipe",
            "inputs": {"doc": "Document"},
            "output": "Page[]",
            "talent_name": "full-document-extractor",
        }
        result = parse_pipe_spec("PipeExtract", spec)
        assert result.extract_talent == "full-document-extractor"  # type: ignore[attr-defined]

    def test_talent_alias_for_img_gen(self) -> None:
        spec = {
            "pipe_code": "test_img_gen",
            "description": "Image gen pipe",
            "inputs": {"prompt_text": "ImgGenPrompt"},
            "output": "Image",
            "talent": "gen-image",
            "prompt": "Generate: $prompt_text",
        }
        result = parse_pipe_spec("PipeImgGen", spec)
        assert result.img_gen_talent == "gen-image"  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# parse_pipe_spec — preset-to-talent resolution
# ---------------------------------------------------------------------------


class TestPresetToTalentResolution:
    """Preset names used where talent names are expected should be auto-resolved."""

    _BASE_LLM: ClassVar[dict[str, Any]] = {
        "pipe_code": "test_pipe",
        "description": "Test pipe",
        "inputs": {"text": "Text"},
        "output": "Text",
        "prompt": "Write about @text",
    }

    def test_preset_name_resolved_to_talent_for_llm(self) -> None:
        spec = {**self._BASE_LLM, "llm_talent": "writing-creative"}
        result = parse_pipe_spec("PipeLLM", spec)
        assert result.llm_talent == "creative-writer"  # type: ignore[attr-defined]

    def test_preset_with_dollar_resolved_for_llm(self) -> None:
        spec = {**self._BASE_LLM, "llm_talent": "$writing-creative"}
        result = parse_pipe_spec("PipeLLM", spec)
        assert result.llm_talent == "creative-writer"  # type: ignore[attr-defined]

    def test_valid_talent_unchanged_for_llm(self) -> None:
        spec = {**self._BASE_LLM, "llm_talent": "creative-writer"}
        result = parse_pipe_spec("PipeLLM", spec)
        assert result.llm_talent == "creative-writer"  # type: ignore[attr-defined]

    def test_invalid_talent_raises_validation_error(self) -> None:
        spec = {**self._BASE_LLM, "llm_talent": "totally-invalid"}
        with pytest.raises(ValidationError):
            parse_pipe_spec("PipeLLM", spec)

    def test_preset_via_generic_alias_also_resolved(self) -> None:
        """talent_name alias + preset value should both be handled."""
        spec = {**self._BASE_LLM, "talent_name": "engineering-code"}
        result = parse_pipe_spec("PipeLLM", spec)
        assert result.llm_talent == "coder"  # type: ignore[attr-defined]

    def test_extract_preset_resolved(self) -> None:
        spec = {
            "pipe_code": "test_extract",
            "description": "Extract pipe",
            "inputs": {"doc": "Document"},
            "output": "Page[]",
            "extract_talent": "default-text-from-pdf",
        }
        result = parse_pipe_spec("PipeExtract", spec)
        assert result.extract_talent == "pdf-basic-text-extractor"  # type: ignore[attr-defined]

    def test_img_gen_preset_resolved(self) -> None:
        spec = {
            "pipe_code": "test_img_gen",
            "description": "Image gen pipe",
            "inputs": {"prompt_text": "ImgGenPrompt"},
            "output": "Image",
            "img_gen_talent": "$gen-image-high-quality",
            "prompt": "Generate: $prompt_text",
        }
        result = parse_pipe_spec("PipeImgGen", spec)
        assert result.img_gen_talent == "gen-image-high-quality"  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# parse_pipe_spec — output dict tolerance
# ---------------------------------------------------------------------------


class TestOutputDictTolerance:
    """The parser should accept output as {"type": "ConceptName"} and extract the string."""

    _BASE_LLM: ClassVar[dict[str, Any]] = {
        "pipe_code": "test_pipe",
        "description": "Test pipe",
        "llm_talent": "creative-writer",
        "inputs": {"text": "Text"},
        "prompt": "Write about @text",
    }

    def test_output_as_string(self) -> None:
        spec = {**self._BASE_LLM, "output": "ImgGenPrompt"}
        result = parse_pipe_spec("PipeLLM", spec)
        assert result.output == "ImgGenPrompt"

    def test_output_as_dict_with_type_key(self) -> None:
        spec = {**self._BASE_LLM, "output": {"type": "ImgGenPrompt"}}
        result = parse_pipe_spec("PipeLLM", spec)
        assert result.output == "ImgGenPrompt"

    def test_output_dict_without_type_key_passes_through(self) -> None:
        """If the dict has no 'type' key, let Pydantic handle the error."""
        spec = {**self._BASE_LLM, "output": {"name": "ImgGenPrompt"}}
        with pytest.raises(ValidationError):
            parse_pipe_spec("PipeLLM", spec)


# ---------------------------------------------------------------------------
# parse_pipe_spec — steps/branches 'pipe' → 'pipe_code' alias
# ---------------------------------------------------------------------------


class TestStepsBranchesAlias:
    """Steps and branches should accept 'pipe' as an alias for 'pipe_code'."""

    def test_sequence_steps_pipe_alias(self) -> None:
        spec: dict[str, Any] = {
            "pipe_code": "my_seq",
            "description": "A sequence",
            "inputs": {"doc": "Document"},
            "output": "Text",
            "steps": [
                {"pipe": "step_one", "result": "intermediate"},
                {"pipe": "step_two", "result": "final"},
            ],
        }
        result = parse_pipe_spec("PipeSequence", spec)
        assert result.steps[0].pipe_code == "step_one"  # type: ignore[attr-defined]
        assert result.steps[1].pipe_code == "step_two"  # type: ignore[attr-defined]

    def test_sequence_steps_pipe_code_canonical(self) -> None:
        spec: dict[str, Any] = {
            "pipe_code": "my_seq",
            "description": "A sequence",
            "inputs": {"doc": "Document"},
            "output": "Text",
            "steps": [
                {"pipe_code": "step_one", "result": "intermediate"},
            ],
        }
        result = parse_pipe_spec("PipeSequence", spec)
        assert result.steps[0].pipe_code == "step_one"  # type: ignore[attr-defined]

    def test_parallel_branches_pipe_alias(self) -> None:
        spec: dict[str, Any] = {
            "pipe_code": "my_parallel",
            "description": "Parallel branches",
            "inputs": {"doc": "Document"},
            "output": "Text",
            "add_each_output": True,
            "branches": [
                {"pipe": "branch_a", "result": "result_a"},
                {"pipe": "branch_b", "result": "result_b"},
            ],
        }
        result = parse_pipe_spec("PipeParallel", spec)
        assert result.branches[0].pipe_code == "branch_a"  # type: ignore[attr-defined]
        assert result.branches[1].pipe_code == "branch_b"  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# parse_pipe_spec — PipeCondition expression alias
# ---------------------------------------------------------------------------


class TestConditionExpressionAlias:
    """PipeCondition should accept 'expression' as alias for 'jinja2_expression_template'."""

    def test_expression_alias(self) -> None:
        spec: dict[str, Any] = {
            "pipe_code": "my_condition",
            "description": "Route by status",
            "inputs": {"status": "Text"},
            "output": "Text",
            "expression": "{{ status }}",
            "outcomes": {"high": "handle_high", "low": "handle_low"},
            "default_outcome": "handle_default",
        }
        result = parse_pipe_spec("PipeCondition", spec)
        assert result.jinja2_expression_template == "{{ status }}"  # type: ignore[attr-defined]

    def test_canonical_expression_field(self) -> None:
        spec: dict[str, Any] = {
            "pipe_code": "my_condition",
            "description": "Route by status",
            "inputs": {"status": "Text"},
            "output": "Text",
            "jinja2_expression_template": "{{ status }}",
            "outcomes": {"high": "handle_high", "low": "handle_low"},
            "default_outcome": "handle_default",
        }
        result = parse_pipe_spec("PipeCondition", spec)
        assert result.jinja2_expression_template == "{{ status }}"  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# parse_pipe_spec — pipe_type alias in JSON
# ---------------------------------------------------------------------------


class TestPipeTypeAlias:
    """'pipe_type' in spec JSON should be accepted as alias for 'type'."""

    def test_type_extracted_from_spec(self) -> None:
        """When type is in the spec dict it should be used (and popped)."""
        spec: dict[str, Any] = {
            "type": "PipeLLM",
            "pipe_code": "test",
            "description": "Test",
            "llm_talent": "creative-writer",
            "inputs": {"text": "Text"},
            "output": "Text",
            "prompt": "Write about @text",
        }
        # Simulate what pipe_cmd does: pop 'type' and pass it as pipe_type
        pipe_type = spec.pop("type")
        result = parse_pipe_spec(pipe_type, spec)
        assert result.pipe_code == "test"


# ---------------------------------------------------------------------------
# parse_pipe_spec — invalid pipe type
# ---------------------------------------------------------------------------


class TestInvalidPipeType:
    """Invalid pipe types should raise ValueError."""

    def test_invalid_pipe_type(self) -> None:
        with pytest.raises(ValueError, match="Invalid pipe type"):
            parse_pipe_spec("PipeNonExistent", {"pipe_code": "x", "description": "x"})


# ---------------------------------------------------------------------------
# pipe_spec_to_toml — talent-to-model in TOML output
# ---------------------------------------------------------------------------


class TestPipeSpecToToml:
    """Verify TOML output maps talents to model presets correctly."""

    _BASE_LLM: ClassVar[dict[str, Any]] = {
        "pipe_code": "my_llm_pipe",
        "description": "Test LLM pipe",
        "llm_talent": "creative-writer",
        "inputs": {"text": "Text"},
        "output": "Text",
        "prompt": "Write about @text",
    }

    def test_llm_talent_becomes_model_preset_in_toml(self) -> None:
        spec = parse_pipe_spec("PipeLLM", {**self._BASE_LLM})
        toml = pipe_spec_to_toml(spec)
        assert 'model = "$writing-creative"' in toml

    def test_llm_preset_input_still_maps_to_correct_model(self) -> None:
        """If the agent provides a preset name, it should resolve and then map to model."""
        spec = parse_pipe_spec("PipeLLM", {**self._BASE_LLM, "llm_talent": "engineering-structured"})
        toml = pipe_spec_to_toml(spec)
        assert 'model = "$engineering-structured"' in toml

    def test_extract_talent_becomes_model_in_toml(self) -> None:
        spec = parse_pipe_spec(
            "PipeExtract",
            {
                "pipe_code": "my_extract",
                "description": "Extract pipe",
                "inputs": {"doc": "Document"},
                "output": "Page[]",
                "extract_talent": "full-document-extractor",
            },
        )
        toml = pipe_spec_to_toml(spec)
        assert 'model = "@default-extract-document"' in toml

    def test_img_gen_talent_becomes_model_in_toml(self) -> None:
        spec = parse_pipe_spec(
            "PipeImgGen",
            {
                "pipe_code": "my_img_gen",
                "description": "Image gen pipe",
                "inputs": {"prompt_text": "ImgGenPrompt"},
                "output": "Image",
                "img_gen_talent": "gen-image",
                "prompt": "Generate: $prompt_text",
            },
        )
        toml = pipe_spec_to_toml(spec)
        assert 'model = "$gen-image"' in toml

    def test_toml_contains_pipe_section(self) -> None:
        spec = parse_pipe_spec("PipeLLM", {**self._BASE_LLM})
        toml = pipe_spec_to_toml(spec)
        assert "[pipe.my_llm_pipe]" in toml
        assert 'type = "PipeLLM"' in toml

    def test_toml_contains_prompt(self) -> None:
        spec = parse_pipe_spec("PipeLLM", {**self._BASE_LLM})
        toml = pipe_spec_to_toml(spec)
        assert 'prompt = "Write about @text"' in toml

    def test_sequence_toml_has_steps(self) -> None:
        spec = parse_pipe_spec(
            "PipeSequence",
            {
                "pipe_code": "my_seq",
                "description": "A sequence",
                "inputs": {"doc": "Document"},
                "output": "Text",
                "steps": [
                    {"pipe": "step_one", "result": "intermediate"},
                    {"pipe": "step_two", "result": "final"},
                ],
            },
        )
        toml = pipe_spec_to_toml(spec)
        assert "step_one" in toml
        assert "step_two" in toml


# ---------------------------------------------------------------------------
# End-to-end: combined tolerance scenarios (the original bug)
# ---------------------------------------------------------------------------


class TestEndToEndTolerance:
    """Reproduce the exact bug scenario that motivated these changes."""

    def test_original_bug_preset_as_talent_with_dict_output(self) -> None:
        """The agent sent 'writing-creative' (preset) and output as dict — both should be tolerated."""
        spec: dict[str, Any] = {
            "pipe_code": "generate_prompt",
            "description": "Generate an image prompt from an idea",
            "llm_talent": "writing-creative",
            "inputs": {"idea": "Text"},
            "output": {"type": "ImgGenPrompt"},
            "prompt": "Generate a creative image prompt based on @idea",
        }
        result = parse_pipe_spec("PipeLLM", spec)
        assert result.llm_talent == "creative-writer"  # type: ignore[attr-defined]
        assert result.output == "ImgGenPrompt"

    def test_original_bug_toml_output_has_correct_model(self) -> None:
        """After resolution, the TOML should contain the correct model preset."""
        spec: dict[str, Any] = {
            "pipe_code": "generate_prompt",
            "description": "Generate an image prompt from an idea",
            "llm_talent": "writing-creative",
            "inputs": {"idea": "Text"},
            "output": {"type": "ImgGenPrompt"},
            "prompt": "Generate a creative image prompt based on @idea",
        }
        result = parse_pipe_spec("PipeLLM", spec)
        toml = pipe_spec_to_toml(result)
        assert 'model = "$writing-creative"' in toml
        assert 'output = "ImgGenPrompt"' in toml
