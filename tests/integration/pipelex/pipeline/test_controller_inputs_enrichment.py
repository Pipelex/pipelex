"""Pin: controller input-drift errors carry the full expected inputs mapping (autofix enrichment).

A controller's ``needed_inputs()`` is the ground truth its declared ``inputs`` table must
match, and the validator has it in hand at detection time. These tests pin that
``MISSING_INPUT_VARIABLE`` / ``EXTRANEOUS_INPUT_VARIABLE`` / ``INPUT_STUFF_SPEC_MISMATCH``
raised on a **controller** carry the full ``expected_inputs`` mapping (variable name →
bundle-representation ref, the exact strings a fix would write) on the categorized error
data — while operator-raised variants of the same error types carry ``None`` and stay
structurally unfixable. This enriched fact is what the fix planner translates into a
``sync-controller-inputs`` suggested fix.
"""

from collections.abc import Callable

import pytest

from pipelex.core.exceptions import PipesAndConceptValidationErrorData
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.validate_bundle import validate_bundle
from pipelex.validation_error_types import PipeValidationErrorType

_MISSING_INPUT_MTHDS = """
domain = "inputsfix_missing"
main_pipe = "make_summary"

[concept]
Summary = "A summary of a text."

[pipe.write_summary]
type = "PipeLLM"
description = "Summarize the text."
inputs = { text = "Text" }
output = "Summary"
prompt = "Summarize $text"

[pipe.make_summary]
type = "PipeSequence"
description = "Sequence not declaring the input its step needs."
output = "Summary"
steps = [
  { pipe = "write_summary", result = "summary" },
]
"""

_EXTRANEOUS_INPUT_MTHDS = """
domain = "inputsfix_extra"
main_pipe = "make_summary"

[concept]
Summary = "A summary of a text."

[pipe.write_summary]
type = "PipeLLM"
description = "Summarize the text."
inputs = { text = "Text" }
output = "Summary"
prompt = "Summarize $text"

[pipe.make_summary]
type = "PipeSequence"
description = "Sequence declaring an input no step needs."
inputs = { text = "Text", note = "Text" }
output = "Summary"
steps = [
  { pipe = "write_summary", result = "summary" },
]
"""

_CONCEPT_MISMATCH_MTHDS = """
domain = "inputsfix_concept"
main_pipe = "make_summary"

[concept]
Summary = "A summary of a text."

[pipe.write_summary]
type = "PipeLLM"
description = "Summarize the text."
inputs = { text = "Text" }
output = "Summary"
prompt = "Summarize $text"

[pipe.make_summary]
type = "PipeSequence"
description = "Sequence declaring the wrong concept for its step's input."
inputs = { text = "Number" }
output = "Summary"
steps = [
  { pipe = "write_summary", result = "summary" },
]
"""

_MULTIPLICITY_MISMATCH_MTHDS = """
domain = "inputsfix_mult"
main_pipe = "make_summary"

[concept]
Summary = "A summary of a text."

[pipe.write_summary]
type = "PipeLLM"
description = "Summarize the text."
inputs = { text = "Text" }
output = "Summary"
prompt = "Summarize $text"

[pipe.make_summary]
type = "PipeSequence"
description = "Sequence declaring a list where its step needs a single item."
inputs = { text = "Text[]" }
output = "Summary"
steps = [
  { pipe = "write_summary", result = "summary" },
]
"""

_FLEXIBLE_NEED_PRESERVED_MTHDS = """
domain = "inputsfix_flex"
main_pipe = "make_summary"

[pipe.summarize]
type = "PipeLLM"
description = "Needs a flexible input plus a concrete one."
inputs = { data = "Anything", other = "Text" }
output = "Text"
prompt = "Use $data and $other"

[pipe.make_summary]
type = "PipeSequence"
description = "Narrows the flexible need to a concrete concept while drifting the other input."
inputs = { data = "Text", other = "Number" }
output = "Text"
steps = [
  { pipe = "summarize", result = "summary" },
]
"""

_OPTIONAL_MARKER_MTHDS = """
domain = "inputsfix_optional"
main_pipe = "check_doc"

[concept]
Verdict = "A verdict."

[pipe.check]
type = "PipeLLM"
description = "Check the doc."
inputs = { doc = "Text" }
output = "Verdict"
prompt = "Check $doc"

[pipe.check_doc]
type = "PipeSequence"
description = "Sequence with a lift-skip optional input plus an extraneous one."
inputs = { doc = "Text?", note = "Text" }
output = "Verdict?"
steps = [
  { pipe = "check", result = "verdict" },
]
"""

_CROSS_DOMAIN_CONCEPTS_MTHDS = """
domain = "docsdom"
main_pipe = "read_doc"

[concept]
Doc = "A document."

[pipe.read_doc]
type = "PipeLLM"
description = "Read the doc."
inputs = { doc = "Doc" }
output = "Text"
prompt = "Read $doc"
"""

_CROSS_DOMAIN_FLOW_MTHDS = """
domain = "flowdom"
main_pipe = "make_flow"

[pipe.summarize]
type = "PipeLLM"
description = "Summarize a cross-domain doc."
inputs = { doc = "docsdom.Doc" }
output = "Text"
prompt = "Summarize $doc"

[pipe.make_flow]
type = "PipeSequence"
description = "Sequence not declaring the cross-domain input its step needs."
output = "Text"
steps = [
  { pipe = "summarize", result = "summary" },
]
"""

_OPERATOR_MISSING_MTHDS = """
domain = "inputsfix_op_missing"
main_pipe = "write"

[pipe.write]
type = "PipeLLM"
description = "Prompt references a variable that is not declared."
output = "Text"
prompt = "Summarize $text"
"""

_OPERATOR_EXTRANEOUS_MTHDS = """
domain = "inputsfix_op_extra"
main_pipe = "write"

[pipe.write]
type = "PipeLLM"
description = "Declares an input the prompt never uses."
inputs = { text = "Text", note = "Text" }
output = "Text"
prompt = "Summarize $text"
"""

_OPERATOR_STRUCTURE_MISMATCH_MTHDS = """
domain = "inputsfix_op_struct"
main_pipe = "extract_record"

[concept.Record]
description = "A record."

[concept.Record.structure]
title = { type = "text", description = "Title" }

[pipe.extract_record]
type = "PipeStructure"
description = "Structure from an image input (invalid: not Text-compatible)."
inputs = { img = "Image" }
output = "Record"
"""

_CONDITION_EXPRESSION_VAR_MTHDS = """
domain = "inputsfix_cond"
main_pipe = "gate"

[concept]
Verdict = "A verdict."

[pipe.check]
type = "PipeLLM"
description = "Check the doc."
inputs = { doc = "Text" }
output = "Verdict"
prompt = "Check $doc"

[pipe.gate]
type = "PipeCondition"
description = "Gate whose expression variable is not declared in inputs."
inputs = { doc = "Text" }
output = "Verdict?"
expression = "mode"
default_outcome = "continue"

[pipe.gate.outcomes]
go = "check"
"""

_UNRESOLVED_DEP_MTHDS = """
domain = "inputsfix_unresolved"
main_pipe = "make_flow"

[pipe.make_flow]
type = "PipeSequence"
description = "Sequence referencing a pipe that does not exist."
inputs = { text = "Text" }
output = "Text"
steps = [
  { pipe = "nonexistent_pipe", result = "out" },
]
"""


async def _error_data_for(
    mthds_contents: list[str],
    *,
    error_type: PipeValidationErrorType,
) -> PipesAndConceptValidationErrorData:
    """Validate invalid bundles and return the first pipe-validation error data of the given type."""
    with pytest.raises(ValidateBundleError) as exc_info:
        await validate_bundle(mthds_contents=mthds_contents)
    matching = [error_data for error_data in exc_info.value.pipe_validation_error_data if error_data.error_type == error_type]
    assert matching, f"Expected a {error_type} error, got {[(e.error_type, e.pipe_code) for e in exc_info.value.pipe_validation_error_data]}"
    return matching[0]


@pytest.mark.asyncio(loop_scope="class")
class TestControllerInputsEnrichment:
    async def test_missing_input_carries_expected_inputs(
        self,
        load_empty_library: Callable[[], str],
    ) -> None:
        """A controller missing a needed input carries the full expected mapping."""
        load_empty_library()
        error_data = await _error_data_for([_MISSING_INPUT_MTHDS], error_type=PipeValidationErrorType.MISSING_INPUT_VARIABLE)
        assert error_data.pipe_code == "make_summary"
        assert error_data.expected_inputs == {"text": "Text"}

    async def test_extraneous_input_carries_expected_inputs(
        self,
        load_empty_library: Callable[[], str],
    ) -> None:
        """A controller declaring an unneeded input carries the mapping without it."""
        load_empty_library()
        error_data = await _error_data_for([_EXTRANEOUS_INPUT_MTHDS], error_type=PipeValidationErrorType.EXTRANEOUS_INPUT_VARIABLE)
        assert error_data.pipe_code == "make_summary"
        assert error_data.expected_inputs == {"text": "Text"}

    async def test_concept_mismatch_carries_expected_inputs(
        self,
        load_empty_library: Callable[[], str],
    ) -> None:
        """A concept mismatch on a controller input carries the needed concept's ref."""
        load_empty_library()
        error_data = await _error_data_for([_CONCEPT_MISMATCH_MTHDS], error_type=PipeValidationErrorType.INPUT_STUFF_SPEC_MISMATCH)
        assert error_data.pipe_code == "make_summary"
        assert error_data.expected_inputs == {"text": "Text"}
        # The message speaks author syntax (Number vs Text) and names the fix — never the Python repr
        # of the Concept/StuffSpec objects (`Concept(...)`, `presence=<PresenceMarker...>`).
        assert (
            error_data.message
            == "In pipe 'make_summary', input 'text' is declared as 'Number' but its step needs 'Text'. Update the input to 'Text'."
        )
        assert "Concept(" not in error_data.message
        assert "presence=" not in error_data.message

    async def test_multiplicity_mismatch_carries_expected_inputs(
        self,
        load_empty_library: Callable[[], str],
    ) -> None:
        """A multiplicity mismatch on a controller input carries the needed single-item ref."""
        load_empty_library()
        error_data = await _error_data_for([_MULTIPLICITY_MISMATCH_MTHDS], error_type=PipeValidationErrorType.INPUT_STUFF_SPEC_MISMATCH)
        assert error_data.pipe_code == "make_summary"
        assert error_data.expected_inputs == {"text": "Text"}

    async def test_flexible_need_preserves_declared_concrete_input(
        self,
        load_empty_library: Callable[[], str],
    ) -> None:
        """A concrete input narrowing a flexible (Anything/Dynamic) need is preserved, not widened.

        The validator accepts a concrete declaration against a flexible need (its concept/multiplicity
        check is skipped for Dynamic/Anything), so the fix renderer must mirror that carve-out: when a
        co-occurring drift on another input raises the enriched error, the narrowed concrete input must
        survive in ``expected_inputs`` instead of being rewritten back to the flexible ``Anything``.
        """
        load_empty_library()
        error_data = await _error_data_for([_FLEXIBLE_NEED_PRESERVED_MTHDS], error_type=PipeValidationErrorType.INPUT_STUFF_SPEC_MISMATCH)
        assert error_data.pipe_code == "make_summary"
        assert error_data.expected_inputs == {"data": "Text", "other": "Text"}

    async def test_declared_optional_marker_preserved_in_expected_inputs(
        self,
        load_empty_library: Callable[[], str],
    ) -> None:
        """A declared input matching the needed spec keeps the author's `?` marker in the mapping."""
        load_empty_library()
        error_data = await _error_data_for([_OPTIONAL_MARKER_MTHDS], error_type=PipeValidationErrorType.EXTRANEOUS_INPUT_VARIABLE)
        assert error_data.pipe_code == "check_doc"
        assert error_data.expected_inputs == {"doc": "Text?"}

    async def test_cross_domain_needed_input_is_qualified(
        self,
        load_empty_library: Callable[[], str],
    ) -> None:
        """A needed input whose concept lives in another domain renders as a qualified ref."""
        load_empty_library()
        error_data = await _error_data_for(
            [_CROSS_DOMAIN_CONCEPTS_MTHDS, _CROSS_DOMAIN_FLOW_MTHDS],
            error_type=PipeValidationErrorType.MISSING_INPUT_VARIABLE,
        )
        assert error_data.pipe_code == "make_flow"
        assert error_data.expected_inputs == {"doc": "docsdom.Doc"}

    async def test_operator_missing_prompt_variable_not_enriched(
        self,
        load_empty_library: Callable[[], str],
    ) -> None:
        """A PipeLLM missing a prompt variable stays on the blueprint channel, unenriched.

        The operator's static validation raises at blueprint stage, so the error is a
        blueprint-channel lookalike carrying no ``expected_inputs`` — the input-fix planner
        never sees it (it only hooks the pipe-validation channel).
        """
        load_empty_library()
        with pytest.raises(ValidateBundleError) as exc_info:
            await validate_bundle(mthds_contents=[_OPERATOR_MISSING_MTHDS])
        assert not exc_info.value.pipe_validation_error_data
        blueprint_error_types = [error_data.error_type for error_data in exc_info.value.pipelex_bundle_blueprint_validation_errors]
        assert PipeValidationErrorType.MISSING_INPUT_VARIABLE in blueprint_error_types

    async def test_operator_extraneous_input_not_enriched(
        self,
        load_empty_library: Callable[[], str],
    ) -> None:
        """A PipeLLM declaring an unused input stays on the blueprint channel, unenriched."""
        load_empty_library()
        with pytest.raises(ValidateBundleError) as exc_info:
            await validate_bundle(mthds_contents=[_OPERATOR_EXTRANEOUS_MTHDS])
        assert not exc_info.value.pipe_validation_error_data
        blueprint_error_types = [error_data.error_type for error_data in exc_info.value.pipelex_bundle_blueprint_validation_errors]
        assert PipeValidationErrorType.EXTRANEOUS_INPUT_VARIABLE in blueprint_error_types

    async def test_operator_structure_mismatch_not_enriched(
        self,
        load_empty_library: Callable[[], str],
    ) -> None:
        """A PipeStructure input mismatch carries no expected mapping (unfixable)."""
        load_empty_library()
        error_data = await _error_data_for([_OPERATOR_STRUCTURE_MISMATCH_MTHDS], error_type=PipeValidationErrorType.INPUT_STUFF_SPEC_MISMATCH)
        assert error_data.pipe_code == "extract_record"
        assert error_data.expected_inputs is None

    async def test_condition_expression_variable_not_enriched(
        self,
        load_empty_library: Callable[[], str],
    ) -> None:
        """A controller's missing *expression* variable is unknowable — no expected mapping.

        The required-variables check fires before ``needed_inputs()`` is computed, and for a
        PipeCondition the needed spec of an expression variable comes from the declared inputs
        themselves — there is nothing trustworthy to derive a fix from.
        """
        load_empty_library()
        error_data = await _error_data_for([_CONDITION_EXPRESSION_VAR_MTHDS], error_type=PipeValidationErrorType.MISSING_INPUT_VARIABLE)
        assert error_data.pipe_code == "gate"
        assert error_data.expected_inputs is None

    async def test_unresolved_dependency_precludes_input_errors(
        self,
        load_empty_library: Callable[[], str],
    ) -> None:
        """An unresolved step dependency surfaces alone — input-drift errors cannot co-occur.

        Library validation resolves every controller dependency (raising immediately on
        failure) before any pipe's ``validate_with_libraries`` runs, so ``needed_inputs()``
        is trustworthy wherever the input checks fire — the prerequisite-clean guard is
        satisfied by validation ordering, not by planner-side scanning.
        """
        load_empty_library()
        with pytest.raises(ValidateBundleError) as exc_info:
            await validate_bundle(mthds_contents=[_UNRESOLVED_DEP_MTHDS])
        error_types = [error_data.error_type for error_data in exc_info.value.pipe_validation_error_data]
        assert PipeValidationErrorType.UNRESOLVED_PIPE_DEPENDENCY in error_types
        input_error_types = {
            PipeValidationErrorType.MISSING_INPUT_VARIABLE,
            PipeValidationErrorType.EXTRANEOUS_INPUT_VARIABLE,
            PipeValidationErrorType.INPUT_STUFF_SPEC_MISMATCH,
        }
        assert not input_error_types.intersection(error_types)
        assert all(error_data.expected_inputs is None for error_data in exc_info.value.pipe_validation_error_data)
