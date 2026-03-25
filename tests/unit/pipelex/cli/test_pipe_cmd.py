"""Unit tests for the agent CLI pipe command — non-nominal / tolerance cases."""

from __future__ import annotations

from typing import Any, ClassVar

import pytest
from pydantic import ValidationError

from pipelex.cli.agent_cli.commands.pipe_cmd import (
    _parse_pipe_spec_from_json,  # noqa: PLC2701 # pyright: ignore[reportPrivateUsage]
    _pipe_spec_to_toml,  # noqa: PLC2701 # pyright: ignore[reportPrivateUsage]
)

# ---------------------------------------------------------------------------
# _parse_pipe_spec_from_json — pipe_code aliases
# ---------------------------------------------------------------------------


class TestPipeCodeAliases:
    """The parser should accept 'code', 'the_pipe_code', and 'name' as aliases for 'pipe_code'."""

    _BASE_LLM: ClassVar[dict[str, Any]] = {
        "description": "Test pipe",
        "model": "$writing-creative",
        "inputs": {"text": "Text"},
        "output": "Text",
        "prompt": "Write something about @text",
    }

    def test_canonical_pipe_code(self) -> None:
        spec = {**self._BASE_LLM, "pipe_code": "my_pipe"}
        result = _parse_pipe_spec_from_json("PipeLLM", spec)
        assert result.pipe_code == "my_pipe"

    def test_alias_code(self) -> None:
        spec = {**self._BASE_LLM, "code": "my_pipe"}
        result = _parse_pipe_spec_from_json("PipeLLM", spec)
        assert result.pipe_code == "my_pipe"

    def test_alias_the_pipe_code(self) -> None:
        spec = {**self._BASE_LLM, "the_pipe_code": "my_pipe"}
        result = _parse_pipe_spec_from_json("PipeLLM", spec)
        assert result.pipe_code == "my_pipe"

    def test_alias_name(self) -> None:
        spec = {**self._BASE_LLM, "name": "my_pipe"}
        result = _parse_pipe_spec_from_json("PipeLLM", spec)
        assert result.pipe_code == "my_pipe"

    def test_canonical_ignores_alias(self) -> None:
        """When pipe_code is present, alias keys are removed so Pydantic doesn't reject them."""
        spec = {**self._BASE_LLM, "pipe_code": "canonical", "code": "alias"}
        result = _parse_pipe_spec_from_json("PipeLLM", spec)
        assert result.pipe_code == "canonical"

    def test_multiple_aliases_all_cleaned_up(self) -> None:
        """When pipe_code and multiple aliases are present, all aliases are removed."""
        spec = {**self._BASE_LLM, "code": "my_pipe", "name": "alt"}
        result = _parse_pipe_spec_from_json("PipeLLM", spec)
        assert result.pipe_code == "my_pipe"

    def test_three_aliases_all_cleaned_up(self) -> None:
        """When pipe_code and all aliases are present, all aliases are removed."""
        spec = {**self._BASE_LLM, "code": "my_pipe", "the_pipe_code": "alt", "name": "alt2"}
        result = _parse_pipe_spec_from_json("PipeLLM", spec)
        assert result.pipe_code == "my_pipe"


# ---------------------------------------------------------------------------
# _parse_pipe_spec_from_json — output dict tolerance
# ---------------------------------------------------------------------------


class TestOutputDictTolerance:
    """The parser should accept output as {"type": "ConceptName"} and extract the string."""

    _BASE_LLM: ClassVar[dict[str, Any]] = {
        "pipe_code": "test_pipe",
        "description": "Test pipe",
        "model": "$writing-creative",
        "inputs": {"text": "Text"},
        "prompt": "Write about @text",
    }

    def test_output_as_string(self) -> None:
        spec = {**self._BASE_LLM, "output": "ImgGenPrompt"}
        result = _parse_pipe_spec_from_json("PipeLLM", spec)
        assert result.output == "ImgGenPrompt"

    def test_output_as_dict_with_type_key(self) -> None:
        spec = {**self._BASE_LLM, "output": {"type": "ImgGenPrompt"}}
        result = _parse_pipe_spec_from_json("PipeLLM", spec)
        assert result.output == "ImgGenPrompt"

    def test_output_dict_without_type_key_passes_through(self) -> None:
        """If the dict has no 'type' key, let Pydantic handle the error."""
        spec = {**self._BASE_LLM, "output": {"name": "ImgGenPrompt"}}
        with pytest.raises(ValidationError):
            _parse_pipe_spec_from_json("PipeLLM", spec)


# ---------------------------------------------------------------------------
# _parse_pipe_spec_from_json — steps/branches 'pipe' → 'pipe_code' alias
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
        result = _parse_pipe_spec_from_json("PipeSequence", spec)
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
        result = _parse_pipe_spec_from_json("PipeSequence", spec)
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
        result = _parse_pipe_spec_from_json("PipeParallel", spec)
        assert result.branches[0].pipe_code == "branch_a"  # type: ignore[attr-defined]
        assert result.branches[1].pipe_code == "branch_b"  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# _parse_pipe_spec_from_json — PipeCondition expression alias
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
        result = _parse_pipe_spec_from_json("PipeCondition", spec)
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
        result = _parse_pipe_spec_from_json("PipeCondition", spec)
        assert result.jinja2_expression_template == "{{ status }}"  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# _parse_pipe_spec_from_json — pipe_type alias in JSON
# ---------------------------------------------------------------------------


class TestPipeTypeAlias:
    """'pipe_type' in spec JSON should be accepted as alias for 'type'."""

    def test_type_extracted_from_spec(self) -> None:
        """When type is in the spec dict it should be used (and popped)."""
        spec: dict[str, Any] = {
            "type": "PipeLLM",
            "pipe_code": "test",
            "description": "Test",
            "model": "$writing-creative",
            "inputs": {"text": "Text"},
            "output": "Text",
            "prompt": "Write about @text",
        }
        # Simulate what pipe_cmd does: pop 'type' and pass it as pipe_type
        pipe_type = spec.pop("type")
        result = _parse_pipe_spec_from_json(pipe_type, spec)
        assert result.pipe_code == "test"


# ---------------------------------------------------------------------------
# _parse_pipe_spec_from_json — invalid pipe type
# ---------------------------------------------------------------------------


class TestInvalidPipeType:
    """Invalid pipe types should raise ValueError."""

    def test_invalid_pipe_type(self) -> None:
        with pytest.raises(ValueError, match="Invalid pipe type"):
            _parse_pipe_spec_from_json("PipeNonExistent", {"pipe_code": "x", "description": "x"})


# ---------------------------------------------------------------------------
# _pipe_spec_to_toml — model in TOML output
# ---------------------------------------------------------------------------


class TestPipeSpecToToml:
    """Verify TOML output contains model presets correctly."""

    _BASE_LLM: ClassVar[dict[str, Any]] = {
        "pipe_code": "my_llm_pipe",
        "description": "Test LLM pipe",
        "model": "$writing-creative",
        "inputs": {"text": "Text"},
        "output": "Text",
        "prompt": "Write about @text",
    }

    def test_llm_model_appears_in_toml(self) -> None:
        spec = _parse_pipe_spec_from_json("PipeLLM", {**self._BASE_LLM})
        toml = _pipe_spec_to_toml(spec)
        assert 'model = "$writing-creative"' in toml

    def test_llm_different_model_in_toml(self) -> None:
        spec = _parse_pipe_spec_from_json("PipeLLM", {**self._BASE_LLM, "model": "$engineering-structured"})
        toml = _pipe_spec_to_toml(spec)
        assert 'model = "$engineering-structured"' in toml

    def test_extract_model_in_toml(self) -> None:
        spec = _parse_pipe_spec_from_json(
            "PipeExtract",
            {
                "pipe_code": "my_extract",
                "description": "Extract pipe",
                "inputs": {"doc": "Document"},
                "output": "Page[]",
                "model": "@default-extract-document",
            },
        )
        toml = _pipe_spec_to_toml(spec)
        assert 'model = "@default-extract-document"' in toml

    def test_img_gen_model_in_toml(self) -> None:
        spec = _parse_pipe_spec_from_json(
            "PipeImgGen",
            {
                "pipe_code": "my_img_gen",
                "description": "Image gen pipe",
                "inputs": {"prompt_text": "ImgGenPrompt"},
                "output": "Image",
                "model": "$gen-image",
                "prompt": "Generate: $prompt_text",
            },
        )
        toml = _pipe_spec_to_toml(spec)
        assert 'model = "$gen-image"' in toml

    def test_toml_contains_pipe_section(self) -> None:
        spec = _parse_pipe_spec_from_json("PipeLLM", {**self._BASE_LLM})
        toml = _pipe_spec_to_toml(spec)
        assert "[pipe.my_llm_pipe]" in toml
        assert 'type = "PipeLLM"' in toml

    def test_toml_contains_prompt(self) -> None:
        spec = _parse_pipe_spec_from_json("PipeLLM", {**self._BASE_LLM})
        toml = _pipe_spec_to_toml(spec)
        assert 'prompt = "Write about @text"' in toml

    def test_sequence_toml_has_steps(self) -> None:
        spec = _parse_pipe_spec_from_json(
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
        toml = _pipe_spec_to_toml(spec)
        assert "step_one" in toml
        assert "step_two" in toml

    def test_llm_no_model_omits_model_in_toml(self) -> None:
        """When model is None, no model line should appear in the TOML."""
        spec = _parse_pipe_spec_from_json(
            "PipeLLM",
            {
                "pipe_code": "my_pipe",
                "description": "No model specified",
                "inputs": {"text": "Text"},
                "output": "Text",
                "prompt": "Write about @text",
            },
        )
        toml = _pipe_spec_to_toml(spec)
        assert "model =" not in toml


# ---------------------------------------------------------------------------
# End-to-end: combined tolerance scenarios
# ---------------------------------------------------------------------------


class TestEndToEndTolerance:
    """Test combined tolerance scenarios with direct model field."""

    def test_model_with_dict_output_both_tolerated(self) -> None:
        """The agent sends model preset and output as dict — both should be tolerated."""
        spec: dict[str, Any] = {
            "pipe_code": "generate_prompt",
            "description": "Generate an image prompt from an idea",
            "model": "$writing-creative",
            "inputs": {"idea": "Text"},
            "output": {"type": "ImgGenPrompt"},
            "prompt": "Generate a creative image prompt based on @idea",
        }
        result = _parse_pipe_spec_from_json("PipeLLM", spec)
        assert result.model == "$writing-creative"  # type: ignore[attr-defined]
        assert result.output == "ImgGenPrompt"

    def test_toml_output_has_correct_model(self) -> None:
        """The TOML should contain the model preset directly."""
        spec: dict[str, Any] = {
            "pipe_code": "generate_prompt",
            "description": "Generate an image prompt from an idea",
            "model": "$writing-creative",
            "inputs": {"idea": "Text"},
            "output": {"type": "ImgGenPrompt"},
            "prompt": "Generate a creative image prompt based on @idea",
        }
        result = _parse_pipe_spec_from_json("PipeLLM", spec)
        toml = _pipe_spec_to_toml(result)
        assert 'model = "$writing-creative"' in toml
        assert 'output = "ImgGenPrompt"' in toml
