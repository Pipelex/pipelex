"""Unit tests for parse_pipe_spec from pipelex.builder.operations.pipe_ops."""

from __future__ import annotations

from typing import Any, ClassVar

import pytest
from pydantic import ValidationError

from pipelex.base_exceptions import error_domain_is_input
from pipelex.builder.operations.pipe_ops import parse_pipe_spec
from pipelex.builder.pipe.exceptions import PipeSpecError
from pipelex.builder.pipe.pipe_batch_spec import PipeBatchSpec
from pipelex.builder.pipe.pipe_condition_spec import PipeConditionSpec
from pipelex.builder.pipe.pipe_extract_spec import PipeExtractSpec
from pipelex.builder.pipe.pipe_func_spec import PipeFuncSpec
from pipelex.builder.pipe.pipe_img_gen_spec import PipeImgGenSpec
from pipelex.builder.pipe.pipe_llm_spec import PipeLLMSpec
from pipelex.builder.pipe.pipe_parallel_spec import PipeParallelSpec
from pipelex.builder.pipe.pipe_search_spec import PipeSearchSpec
from pipelex.builder.pipe.pipe_sequence_spec import PipeSequenceSpec
from pipelex.builder.pipe.pipe_signature_spec import PipeSignatureSpec
from pipelex.pipe_machinery.pipe_blueprint import PipeType
from tests.unit.pipelex.builder.operations.test_data import PipeOpsTestData

_BASE_LLM = PipeOpsTestData.BASE_LLM_SPEC


class TestParsePipeSpec:
    """Comprehensive tests for parse_pipe_spec: validation, aliases, tolerance, and dispatch."""

    # -- invalid pipe type ------------------------------------------------

    def test_unknown_type_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid pipe type"):
            parse_pipe_spec({"pipe_code": "x", "description": "x"}, pipe_type="PipeNonExistent")

    def test_error_lists_valid_types(self) -> None:
        with pytest.raises(ValueError, match="PipeLLM"):
            parse_pipe_spec({"pipe_code": "x", "description": "x"}, pipe_type="PipeBogus")

    # -- typeless signature (no type) -------------------------------------

    def test_typeless_spec_becomes_signature(self) -> None:
        """A typeless contract-only spec (pipe_type=None) routes to PipeSignatureSpec — omitting the
        type IS the signature.
        """
        result = parse_pipe_spec(
            {"pipe_code": "summarize_doc", "description": "Summarize a doc.", "inputs": {"doc": "Document"}, "output": "Text"},
            pipe_type=None,
        )
        assert isinstance(result, PipeSignatureSpec)
        assert result.to_blueprint().is_signature is True

    def test_typeless_spec_preserves_signature_for_hint(self) -> None:
        result = parse_pipe_spec(
            {"pipe_code": "x", "description": "d", "inputs": {"doc": "Text"}, "output": "Text", "signature_for": "PipeLLM"},
            pipe_type=None,
        )
        assert isinstance(result, PipeSignatureSpec)
        assert result.signature_for is PipeType.PIPE_LLM

    def test_explicit_signature_tag_rejected_with_migration_error(self) -> None:
        """`PipeSignature` is no longer a selectable type: passing it is a migration error (never a
        generic 'Invalid pipe type', and never routed through the spec-class map).
        """
        with pytest.raises(ValueError, match="is no longer a pipe type") as exc_info:
            parse_pipe_spec(
                {"pipe_code": "x", "description": "d", "inputs": {"doc": "Text"}, "output": "Text"},
                pipe_type="PipeSignature",
            )
        assert "Invalid pipe type" not in str(exc_info.value)

    def test_typeless_spec_with_stray_field_raises_teaching_error(self) -> None:
        with pytest.raises(ValueError, match="has no `type` but declares `prompt`"):
            parse_pipe_spec(
                {"pipe_code": "x", "description": "d", "inputs": {"doc": "Text"}, "output": "Text", "prompt": "do it"},
                pipe_type=None,
            )

    @pytest.mark.parametrize("alias", ["output_concept", "output_type"])
    def test_typeless_spec_accepts_output_alias(self, alias: str) -> None:
        """Output aliases are canonicalized before the typeless-signature contract check, so a signature
        authored with `output_concept` / `output_type` is accepted — parity with typed pipes.
        """
        result = parse_pipe_spec(
            {"pipe_code": "x", "description": "d", "inputs": {"doc": "Document"}, alias: "Article"},
            pipe_type=None,
        )
        assert isinstance(result, PipeSignatureSpec)
        assert result.output == "Article"

    def test_typeless_spec_accepts_dict_output(self) -> None:
        """A dict-shaped output (`{"type": ...}`) is flattened before the contract check for a signature."""
        result = parse_pipe_spec(
            {"pipe_code": "x", "description": "d", "inputs": {"doc": "Document"}, "output": {"type": "Article"}},
            pipe_type=None,
        )
        assert isinstance(result, PipeSignatureSpec)
        assert result.output == "Article"

    def test_typeless_spec_stray_impl_field_still_rejected_after_output_normalization(self) -> None:
        """Output normalization must not weaken the teaching error: a genuine implementation field on a
        typeless spec still raises, naming the field.
        """
        with pytest.raises(ValueError, match="has no `type` but declares `model`"):
            parse_pipe_spec(
                {"pipe_code": "x", "description": "d", "inputs": {"doc": "Document"}, "output": "Article", "model": "gpt"},
                pipe_type=None,
            )

    # -- pipe_code aliases ------------------------------------------------

    def test_canonical_pipe_code(self) -> None:
        result = parse_pipe_spec({**_BASE_LLM}, pipe_type="PipeLLM")
        assert result.pipe_code == "test_pipe"

    @pytest.mark.parametrize("alias", ["the_pipe_code", "code", "name", "pipe_name", "pipe_ref"])
    def test_pipe_code_alias_accepted(self, alias: str) -> None:
        spec = {key: val for key, val in _BASE_LLM.items() if key != "pipe_code"}
        spec[alias] = "via_alias"
        result = parse_pipe_spec(spec, pipe_type="PipeLLM")
        assert result.pipe_code == "via_alias"

    def test_canonical_pipe_code_takes_precedence_over_alias(self) -> None:
        """When pipe_code is present, aliases are ignored and cleaned up."""
        spec = {**_BASE_LLM, "code": "alias_value", "name": "another_alias"}
        result = parse_pipe_spec(spec, pipe_type="PipeLLM")
        assert result.pipe_code == "test_pipe"

    def test_first_alias_wins_when_no_canonical(self) -> None:
        """When multiple aliases are present without pipe_code, iteration order wins (the_pipe_code first)."""
        spec = {key: val for key, val in _BASE_LLM.items() if key != "pipe_code"}
        spec["code"] = "second"
        spec["the_pipe_code"] = "first"
        spec["name"] = "third"
        result = parse_pipe_spec(spec, pipe_type="PipeLLM")
        assert result.pipe_code == "first"

    # -- output dict tolerance --------------------------------------------

    def test_output_as_string(self) -> None:
        result = parse_pipe_spec({**_BASE_LLM, "output": "Article"}, pipe_type="PipeLLM")
        assert result.output == "Article"

    def test_output_dict_with_type_key(self) -> None:
        result = parse_pipe_spec({**_BASE_LLM, "output": {"type": "Article"}}, pipe_type="PipeLLM")
        assert result.output == "Article"

    def test_output_single_item_dict(self) -> None:
        """A single-item dict is unambiguous — extract the value."""
        result = parse_pipe_spec({**_BASE_LLM, "output": {"result": "Article"}}, pipe_type="PipeLLM")
        assert result.output == "Article"

    def test_output_multi_item_dict_raises(self) -> None:
        """A multi-item dict is ambiguous — validation fails."""
        with pytest.raises(ValidationError):
            parse_pipe_spec({**_BASE_LLM, "output": {"a": "Text", "b": "Image"}}, pipe_type="PipeLLM")

    def test_output_type_key_takes_precedence_in_dict(self) -> None:
        """When 'type' key is present in output dict, it wins even if other keys exist."""
        result = parse_pipe_spec({**_BASE_LLM, "output": {"type": "Article", "extra": "ignored"}}, pipe_type="PipeLLM")
        assert result.output == "Article"

    # -- output field aliases -----------------------------------------------

    @pytest.mark.parametrize("alias", ["output_concept", "output_type"])
    def test_output_alias_accepted(self, alias: str) -> None:
        """Each output alias resolves to the correct output value."""
        spec = {key: val for key, val in _BASE_LLM.items() if key != "output"}
        spec[alias] = "Article"
        result = parse_pipe_spec(spec, pipe_type="PipeLLM")
        assert result.output == "Article"

    @pytest.mark.parametrize("alias", ["output_concept", "output_type"])
    def test_output_alias_tried_first_when_canonical_present(self, alias: str) -> None:
        """When both output and an alias exist, alias value is tried first."""
        spec = {**_BASE_LLM, alias: "AliasValue"}
        result = parse_pipe_spec(spec, pipe_type="PipeLLM")
        assert result.output == "AliasValue"

    def test_first_output_alias_wins(self) -> None:
        """When multiple output aliases present without canonical, first in tuple order wins."""
        spec = {key: val for key, val in _BASE_LLM.items() if key != "output"}
        spec["output_type"] = "SecondAlias"
        spec["output_concept"] = "FirstAlias"
        result = parse_pipe_spec(spec, pipe_type="PipeLLM")
        assert result.output == "FirstAlias"

    # -- prompt aliases ---------------------------------------------------

    def test_prompt_template_alias_for_llm(self) -> None:
        """`prompt_template` alone is promoted to `prompt` for PipeLLM."""
        spec = {key: val for key, val in _BASE_LLM.items() if key != "prompt"}
        spec["prompt_template"] = "Write about $text"
        result = parse_pipe_spec(spec, pipe_type="PipeLLM")
        assert isinstance(result, PipeLLMSpec)
        assert result.prompt == "Write about $text"

    def test_canonical_prompt_takes_precedence_over_alias(self) -> None:
        """When both `prompt` and `prompt_template` are present, canonical wins and alias is dropped."""
        spec = {**_BASE_LLM, "prompt_template": "alias_value"}
        result = parse_pipe_spec(spec, pipe_type="PipeLLM")
        assert isinstance(result, PipeLLMSpec)
        assert result.prompt == _BASE_LLM["prompt"]

    def test_prompt_template_alias_for_img_gen(self) -> None:
        """`prompt_template` alias also works for PipeImgGen."""
        spec: dict[str, Any] = {
            "pipe_code": "my_img",
            "description": "Generate image",
            "inputs": {"prompt_text": "Text"},
            "output": "Image",
            "prompt_template": "Generate: $prompt_text",
        }
        result = parse_pipe_spec(spec, pipe_type="PipeImgGen")
        assert isinstance(result, PipeImgGenSpec)
        assert result.prompt == "Generate: $prompt_text"

    # -- steps/branches 'pipe' → 'pipe_code' alias -----------------------

    def test_sequence_steps_canonical_pipe_code(self) -> None:
        spec: dict[str, Any] = {
            "pipe_code": "my_seq",
            "description": "A sequence",
            "inputs": {"doc": "Document"},
            "output": "Text",
            "steps": [{"pipe_code": "step_one", "result": "intermediate"}],
        }
        result = parse_pipe_spec(spec, pipe_type="PipeSequence")
        assert isinstance(result, PipeSequenceSpec)
        assert result.steps[0].pipe_code == "step_one"

    @pytest.mark.parametrize("alias", ["pipe", "pipe_ref", "the_pipe_code", "code", "name", "pipe_name"])
    def test_sequence_steps_all_aliases(self, alias: str) -> None:
        """All pipe_code aliases must work inside step dicts."""
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
        result = parse_pipe_spec(spec, pipe_type="PipeSequence")
        assert isinstance(result, PipeSequenceSpec)
        assert result.steps[0].pipe_code == "step_one"
        assert result.steps[1].pipe_code == "step_two"

    @pytest.mark.parametrize("alias", ["pipe", "pipe_ref", "the_pipe_code", "code", "name", "pipe_name"])
    def test_parallel_branches_all_aliases(self, alias: str) -> None:
        """All pipe_code aliases must work inside branch dicts."""
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
        result = parse_pipe_spec(spec, pipe_type="PipeParallel")
        assert isinstance(result, PipeParallelSpec)
        assert result.branches[0].pipe_code == "branch_a"
        assert result.branches[1].pipe_code == "branch_b"

    # -- extraneous "inputs" in steps/branches silently dropped -----------

    def test_sequence_steps_extraneous_inputs_dropped(self) -> None:
        """Agents sometimes add 'inputs' to individual steps; these should be silently ignored."""
        spec: dict[str, Any] = {
            "pipe_code": "interview_prep",
            "description": "Analyze CV-job match",
            "inputs": {"cv": "Document", "job_offer": "Document"},
            "output": "Text",
            "steps": [
                {"pipe": "extract_cv", "inputs": {"cv": "cv"}, "result": "cv_pages"},
                {"pipe": "extract_job_offer", "inputs": {"job_offer": "job_offer"}, "result": "job_offer_pages"},
                {"pipe": "analyze_match", "result": "match_analysis"},
            ],
        }
        result = parse_pipe_spec(spec, pipe_type="PipeSequence")
        assert isinstance(result, PipeSequenceSpec)
        assert result.steps[0].pipe_code == "extract_cv"
        assert result.steps[1].pipe_code == "extract_job_offer"

    def test_parallel_branches_extraneous_inputs_dropped(self) -> None:
        spec: dict[str, Any] = {
            "pipe_code": "my_par",
            "description": "Parallel branches",
            "inputs": {"doc": "Document"},
            "output": "Text",
            "add_each_output": True,
            "branches": [
                {"pipe": "branch_a", "inputs": {"doc": "doc"}, "result": "result_a"},
            ],
        }
        result = parse_pipe_spec(spec, pipe_type="PipeParallel")
        assert isinstance(result, PipeParallelSpec)
        assert result.branches[0].pipe_code == "branch_a"

    # -- malformed steps/branches shape (typed, not bare TypeError/ValueError) --

    @pytest.mark.parametrize("bad_steps", ["notalist", 42, {"a": "b"}])
    def test_non_list_steps_raises_pipe_spec_error(self, bad_steps: Any) -> None:
        """A non-list ``steps`` is a caller-input fault, surfaced as a typed PipeSpecError."""
        spec: dict[str, Any] = {"pipe_code": "my_seq", "description": "d", "output": "Text", "steps": bad_steps}
        with pytest.raises(PipeSpecError, match="'steps' must be a list of step mappings"):
            parse_pipe_spec(spec, pipe_type="PipeSequence")

    @pytest.mark.parametrize("bad_entry", [42, "astring", [1, 2]])
    def test_non_mapping_step_entry_raises_pipe_spec_error(self, bad_entry: Any) -> None:
        """A step entry that is not a mapping is a typed input error, not a bare TypeError."""
        spec: dict[str, Any] = {"pipe_code": "my_seq", "description": "d", "output": "Text", "steps": [bad_entry]}
        with pytest.raises(PipeSpecError, match="entry in pipe spec 'steps' must be a mapping"):
            parse_pipe_spec(spec, pipe_type="PipeSequence")

    @pytest.mark.parametrize("bad_branches", ["notalist", 42, {"a": "b"}])
    def test_non_list_branches_raises_pipe_spec_error(self, bad_branches: Any) -> None:
        spec: dict[str, Any] = {"pipe_code": "my_par", "description": "d", "output": "Text", "branches": bad_branches}
        with pytest.raises(PipeSpecError, match="'branches' must be a list of step mappings"):
            parse_pipe_spec(spec, pipe_type="PipeParallel")

    @pytest.mark.parametrize("bad_entry", [42, "astring", [1, 2]])
    def test_non_mapping_branch_entry_raises_pipe_spec_error(self, bad_entry: Any) -> None:
        spec: dict[str, Any] = {"pipe_code": "my_par", "description": "d", "output": "Text", "branches": [bad_entry]}
        with pytest.raises(PipeSpecError, match="entry in pipe spec 'branches' must be a mapping"):
            parse_pipe_spec(spec, pipe_type="PipeParallel")

    def test_malformed_steps_classifies_as_input_domain(self) -> None:
        """The raised error carries the INPUT domain so HTTP consumers render it as a 422."""
        spec: dict[str, Any] = {"pipe_code": "my_seq", "description": "d", "output": "Text", "steps": "notalist"}
        with pytest.raises(PipeSpecError) as exc_info:
            parse_pipe_spec(spec, pipe_type="PipeSequence")
        assert error_domain_is_input(exc_info.value.error_domain)

    # -- malformed top-level shape (typed, not bare TypeError/ValueError) --

    @pytest.mark.parametrize("bad_spec", ["a string", ["a", "b"], 123, 3.14, None])
    def test_non_mapping_top_level_raises_pipe_spec_error(self, bad_spec: Any) -> None:
        """A non-mapping top-level spec leaks a bare TypeError/ValueError from dict() without the guard."""
        with pytest.raises(PipeSpecError, match="must be a mapping"):
            parse_pipe_spec(bad_spec, pipe_type="PipeLLM")

    def test_non_mapping_top_level_classifies_as_input_domain(self) -> None:
        with pytest.raises(PipeSpecError) as exc_info:
            parse_pipe_spec("not a mapping", pipe_type="PipeLLM")
        assert error_domain_is_input(exc_info.value.error_domain)

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
        result = parse_pipe_spec(spec, pipe_type="PipeCondition")
        assert isinstance(result, PipeConditionSpec)
        assert result.jinja2_expression_template == "{{ status }}"

    def test_condition_canonical_jinja2_field(self) -> None:
        spec = {**self._BASE_CONDITION, "jinja2_expression_template": "{{ status }}"}
        result = parse_pipe_spec(spec, pipe_type="PipeCondition")
        assert isinstance(result, PipeConditionSpec)
        assert result.jinja2_expression_template == "{{ status }}"

    def test_condition_canonical_takes_precedence(self) -> None:
        spec = {**self._BASE_CONDITION, "jinja2_expression_template": "{{ canonical }}", "expression": "{{ alias }}"}
        result = parse_pipe_spec(spec, pipe_type="PipeCondition")
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
            "prompt": "Write about $text",
        }
        snapshot = dict(original)
        parse_pipe_spec(original, pipe_type="PipeLLM")
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
        parse_pipe_spec(spec, pipe_type="PipeSequence")
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
                    "inputs": {"prompt_text": "Text"},
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
                    "prompt": "Search for $query_text",
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
        result = parse_pipe_spec(spec_data, pipe_type=pipe_type)
        assert isinstance(result, expected_class)
