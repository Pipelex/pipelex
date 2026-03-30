"""Unit tests for parse_pipe_spec from pipelex.builder.operations.pipe_ops."""

from __future__ import annotations

from typing import Any, ClassVar

import pytest
from pydantic import ValidationError

from pipelex.builder.operations.pipe_ops import parse_pipe_spec
from pipelex.builder.pipe.pipe_batch_spec import PipeBatchSpec
from pipelex.builder.pipe.pipe_condition_spec import PipeConditionSpec
from pipelex.builder.pipe.pipe_extract_spec import PipeExtractSpec
from pipelex.builder.pipe.pipe_func_spec import PipeFuncSpec
from pipelex.builder.pipe.pipe_img_gen_spec import PipeImgGenSpec
from pipelex.builder.pipe.pipe_llm_spec import PipeLLMSpec
from pipelex.builder.pipe.pipe_parallel_spec import PipeParallelSpec
from pipelex.builder.pipe.pipe_search_spec import PipeSearchSpec
from pipelex.builder.pipe.pipe_sequence_spec import PipeSequenceSpec
from tests.unit.pipelex.builder.operations.test_data import PipeOpsTestData

_BASE_LLM = PipeOpsTestData.BASE_LLM_SPEC


class TestParsePipeSpec:
    """Comprehensive tests for parse_pipe_spec: validation, aliases, tolerance, and dispatch."""

    # -- invalid pipe type ------------------------------------------------

    def test_unknown_type_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid pipe type"):
            parse_pipe_spec("PipeNonExistent", {"pipe_code": "x", "description": "x"})

    def test_error_lists_valid_types(self) -> None:
        with pytest.raises(ValueError, match="PipeLLM"):
            parse_pipe_spec("PipeBogus", {"pipe_code": "x", "description": "x"})

    # -- pipe_code aliases ------------------------------------------------

    def test_canonical_pipe_code(self) -> None:
        result = parse_pipe_spec("PipeLLM", {**_BASE_LLM})
        assert result.pipe_code == "test_pipe"

    @pytest.mark.parametrize("alias", ["the_pipe_code", "code", "name", "pipe_name", "pipe_ref"])
    def test_pipe_code_alias_accepted(self, alias: str) -> None:
        spec = {key: val for key, val in _BASE_LLM.items() if key != "pipe_code"}
        spec[alias] = "via_alias"
        result = parse_pipe_spec("PipeLLM", spec)
        assert result.pipe_code == "via_alias"

    def test_canonical_pipe_code_takes_precedence_over_alias(self) -> None:
        """When pipe_code is present, aliases are ignored and cleaned up."""
        spec = {**_BASE_LLM, "code": "alias_value", "name": "another_alias"}
        result = parse_pipe_spec("PipeLLM", spec)
        assert result.pipe_code == "test_pipe"

    def test_first_alias_wins_when_no_canonical(self) -> None:
        """When multiple aliases are present without pipe_code, iteration order wins (the_pipe_code first)."""
        spec = {key: val for key, val in _BASE_LLM.items() if key != "pipe_code"}
        spec["code"] = "second"
        spec["the_pipe_code"] = "first"
        spec["name"] = "third"
        result = parse_pipe_spec("PipeLLM", spec)
        assert result.pipe_code == "first"

    # -- output dict tolerance --------------------------------------------

    def test_output_as_string(self) -> None:
        result = parse_pipe_spec("PipeLLM", {**_BASE_LLM, "output": "Article"})
        assert result.output == "Article"

    def test_output_dict_with_type_key(self) -> None:
        result = parse_pipe_spec("PipeLLM", {**_BASE_LLM, "output": {"type": "Article"}})
        assert result.output == "Article"

    def test_output_single_item_dict(self) -> None:
        """A single-item dict is unambiguous — extract the value."""
        result = parse_pipe_spec("PipeLLM", {**_BASE_LLM, "output": {"result": "Article"}})
        assert result.output == "Article"

    def test_output_multi_item_dict_raises(self) -> None:
        """A multi-item dict is ambiguous — validation fails."""
        with pytest.raises(ValidationError):
            parse_pipe_spec("PipeLLM", {**_BASE_LLM, "output": {"a": "Text", "b": "Image"}})

    def test_output_type_key_takes_precedence_in_dict(self) -> None:
        """When 'type' key is present in output dict, it wins even if other keys exist."""
        result = parse_pipe_spec("PipeLLM", {**_BASE_LLM, "output": {"type": "Article", "extra": "ignored"}})
        assert result.output == "Article"

    # -- steps/branches 'pipe' → 'pipe_code' alias -----------------------

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
        assert isinstance(result, PipeSequenceSpec)
        assert result.steps[0].pipe_code == "step_one"
        assert result.steps[1].pipe_code == "step_two"

    def test_sequence_steps_canonical_pipe_code(self) -> None:
        spec: dict[str, Any] = {
            "pipe_code": "my_seq",
            "description": "A sequence",
            "inputs": {"doc": "Document"},
            "output": "Text",
            "steps": [{"pipe_code": "step_one", "result": "intermediate"}],
        }
        result = parse_pipe_spec("PipeSequence", spec)
        assert isinstance(result, PipeSequenceSpec)
        assert result.steps[0].pipe_code == "step_one"

    def test_parallel_branches_pipe_alias(self) -> None:
        spec: dict[str, Any] = {
            "pipe_code": "my_par",
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
        assert isinstance(result, PipeParallelSpec)
        assert result.branches[0].pipe_code == "branch_a"
        assert result.branches[1].pipe_code == "branch_b"

    @pytest.mark.parametrize("alias", ["pipe_ref", "the_pipe_code", "code", "name", "pipe_name"])
    def test_sequence_steps_all_aliases(self, alias: str) -> None:
        """All pipe_code aliases must work inside step dicts, not just 'pipe'."""
        spec: dict[str, Any] = {
            "pipe_code": "my_seq",
            "description": "A sequence",
            "inputs": {"doc": "Document"},
            "output": "Text",
            "steps": [
                {alias: "step_one", "result": "intermediate"},
                {alias: "step_two", "result": "final"},
            ],
        }
        result = parse_pipe_spec("PipeSequence", spec)
        assert isinstance(result, PipeSequenceSpec)
        assert result.steps[0].pipe_code == "step_one"
        assert result.steps[1].pipe_code == "step_two"

    @pytest.mark.parametrize("alias", ["pipe_ref", "the_pipe_code", "code", "name", "pipe_name"])
    def test_parallel_branches_all_aliases(self, alias: str) -> None:
        """All pipe_code aliases must work inside branch dicts, not just 'pipe'."""
        spec: dict[str, Any] = {
            "pipe_code": "my_par",
            "description": "Parallel branches",
            "inputs": {"doc": "Document"},
            "output": "Text",
            "add_each_output": True,
            "branches": [
                {alias: "branch_a", "result": "result_a"},
                {alias: "branch_b", "result": "result_b"},
            ],
        }
        result = parse_pipe_spec("PipeParallel", spec)
        assert isinstance(result, PipeParallelSpec)
        assert result.branches[0].pipe_code == "branch_a"
        assert result.branches[1].pipe_code == "branch_b"

    # -- PipeCondition expression alias -----------------------------------

    _BASE_CONDITION: ClassVar[dict[str, Any]] = {
        "pipe_code": "my_cond",
        "description": "Route by status",
        "inputs": {"status": "Text"},
        "output": "Text",
        "outcomes": {"high": "handle_high", "low": "handle_low"},
        "default_outcome": "handle_default",
    }

    def test_condition_expression_alias(self) -> None:
        spec = {**self._BASE_CONDITION, "expression": "{{ status }}"}
        result = parse_pipe_spec("PipeCondition", spec)
        assert isinstance(result, PipeConditionSpec)
        assert result.jinja2_expression_template == "{{ status }}"

    def test_condition_canonical_jinja2_field(self) -> None:
        spec = {**self._BASE_CONDITION, "jinja2_expression_template": "{{ status }}"}
        result = parse_pipe_spec("PipeCondition", spec)
        assert isinstance(result, PipeConditionSpec)
        assert result.jinja2_expression_template == "{{ status }}"

    def test_condition_canonical_takes_precedence(self) -> None:
        spec = {**self._BASE_CONDITION, "jinja2_expression_template": "{{ canonical }}", "expression": "{{ alias }}"}
        result = parse_pipe_spec("PipeCondition", spec)
        assert isinstance(result, PipeConditionSpec)
        assert result.jinja2_expression_template == "{{ canonical }}"

    # -- does not mutate caller's dict ------------------------------------

    def test_original_dict_unchanged(self) -> None:
        original: dict[str, Any] = {
            "code": "my_pipe",
            "description": "Test",
            "model": "$writing-creative",
            "inputs": {"text": "Text"},
            "output": "Text",
            "prompt": "Write about @text",
        }
        snapshot = dict(original)
        parse_pipe_spec("PipeLLM", original)
        assert original == snapshot

    def test_nested_step_dicts_not_mutated(self) -> None:
        step = {"pipe": "step_one", "result": "intermediate"}
        spec: dict[str, Any] = {
            "pipe_code": "my_seq",
            "description": "A sequence",
            "inputs": {"doc": "Document"},
            "output": "Text",
            "steps": [step],
        }
        step_snapshot = dict(step)
        parse_pipe_spec("PipeSequence", spec)
        assert step == step_snapshot

    # -- returns correct subclass -----------------------------------------

    @pytest.mark.parametrize(
        ("pipe_type", "spec_data", "expected_class"),
        [
            (
                "PipeLLM",
                {**_BASE_LLM},
                PipeLLMSpec,
            ),
            (
                "PipeFunc",
                {"pipe_code": "my_func", "description": "A function", "inputs": {"data": "Text"}, "output": "Text", "function_name": "process_data"},
                PipeFuncSpec,
            ),
            (
                "PipeImgGen",
                {
                    "pipe_code": "my_img",
                    "description": "Generate image",
                    "inputs": {"prompt_text": "ImgGenPrompt"},
                    "output": "Image",
                    "prompt": "Generate: $prompt_text",
                },
                PipeImgGenSpec,
            ),
            (
                "PipeExtract",
                {"pipe_code": "my_extract", "description": "Extract text", "inputs": {"doc": "Document"}, "output": "Page[]"},
                PipeExtractSpec,
            ),
            (
                "PipeSearch",
                {
                    "pipe_code": "my_search",
                    "description": "Search the web",
                    "inputs": {"query_text": "Text"},
                    "output": "Text",
                    "prompt": "Search for @query_text",
                },
                PipeSearchSpec,
            ),
            (
                "PipeBatch",
                {
                    "pipe_code": "my_batch",
                    "description": "Batch process",
                    "inputs": {"items": "Text[]"},
                    "output": "Text[]",
                    "branch_pipe_code": "process_one",
                    "input_list_name": "items",
                    "input_item_name": "item",
                },
                PipeBatchSpec,
            ),
        ],
    )
    def test_correct_subclass(self, pipe_type: str, spec_data: dict[str, Any], expected_class: type) -> None:
        result = parse_pipe_spec(pipe_type, spec_data)
        assert isinstance(result, expected_class)
