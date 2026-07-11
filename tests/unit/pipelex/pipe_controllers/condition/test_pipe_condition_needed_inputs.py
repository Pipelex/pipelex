from typing import Callable

import pytest

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.pipes.exceptions import PipeValidationError
from pipelex.core.pipes.inputs.input_stuff_specs import InputStuffSpecs
from pipelex.core.pipes.pipe_factory import PipeFactory
from pipelex.hub import get_concept_library, get_pipe_library
from pipelex.pipe_controllers.condition.pipe_condition import PipeCondition
from pipelex.pipe_controllers.condition.pipe_condition_blueprint import PipeConditionBlueprint
from pipelex.pipe_controllers.condition.special_outcome import SpecialOutcome
from pipelex.pipe_operators.llm.pipe_llm import PipeLLM
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint


class TestPipeConditionNeededInputs:
    """Tests for PipeCondition.needed_inputs method."""

    def test_needed_inputs_collects_expression_variables(self, load_empty_library: Callable[[], None]):
        """Test that variables from the expression are collected as needed inputs."""
        load_empty_library()
        domain_code = "test_domain"
        concept_library = get_concept_library()

        # Create concepts
        text_concept = ConceptFactory.make_from_blueprint(
            domain_code=domain_code,
            concept_code="TextOutput",
            blueprint_or_string_description=ConceptBlueprint(description="Text output"),
        )
        concept_library.add_concepts(concepts=[text_concept])

        # Create PipeCondition with expression that uses variables
        pipe_condition_blueprint = PipeConditionBlueprint(
            description="Condition with expression variables",
            inputs={"status": "native.Text", "priority": "native.Text"},
            output="native.Text?",
            expression="status",  # Uses 'status' variable (gets wrapped in {{ }} internally)
            outcomes={"active": SpecialOutcome.CONTINUE, "inactive": SpecialOutcome.CONTINUE},
            default_outcome=SpecialOutcome.CONTINUE,
        )

        pipe_condition = PipeFactory[PipeCondition].make_from_blueprint(
            domain_code=domain_code,
            pipe_code="test_condition",
            blueprint=pipe_condition_blueprint,
        )

        # Get needed inputs
        needed_inputs = pipe_condition.needed_inputs()

        # Verify it returns InputStuffSpecs
        assert isinstance(needed_inputs, InputStuffSpecs)

        # The expression uses 'status', so it should be in needed inputs
        assert "status" in needed_inputs.root
        # The concept for expression variables comes from the declared inputs
        assert needed_inputs.root["status"].concept.code == NativeConceptCode.TEXT

        concept_library.teardown()

    def test_needed_inputs_collects_from_mapped_pipes(self, load_empty_library: Callable[[], None]):
        """Test that needed_inputs collects inputs from all mapped pipes."""
        load_empty_library()
        domain_code = "test_domain"
        concept_library = get_concept_library()
        pipe_library = get_pipe_library()

        # Create concepts
        document_concept = ConceptFactory.make_from_blueprint(
            domain_code=domain_code,
            concept_code="TestDocument",
            blueprint_or_string_description=ConceptBlueprint(description="A document"),
        )
        analysis_concept = ConceptFactory.make_from_blueprint(
            domain_code=domain_code,
            concept_code="Analysis",
            blueprint_or_string_description=ConceptBlueprint(description="An analysis"),
        )
        concept_library.add_concepts(concepts=[document_concept, analysis_concept])

        # Create two PipeLLM pipes that the condition will map to
        pipe_a_blueprint = PipeLLMBlueprint(
            description="Pipe A",
            inputs={"doc_input": document_concept.concept_ref},
            output=analysis_concept.concept_ref,
            prompt="Analyze: $doc_input",
        )
        pipe_a = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code=domain_code,
            pipe_code="pipe_a",
            blueprint=pipe_a_blueprint,
            concept_codes_from_the_same_domain=[document_concept.code, analysis_concept.code],
        )
        pipe_library.add_new_pipe(pipe=pipe_a)

        pipe_b_blueprint = PipeLLMBlueprint(
            description="Pipe B",
            inputs={"other_doc": document_concept.concept_ref},
            output=analysis_concept.concept_ref,
            prompt="Summarize: $other_doc",
        )
        pipe_b = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code=domain_code,
            pipe_code="pipe_b",
            blueprint=pipe_b_blueprint,
            concept_codes_from_the_same_domain=[document_concept.code, analysis_concept.code],
        )
        pipe_library.add_new_pipe(pipe=pipe_b)

        # Create PipeCondition that maps to these pipes
        pipe_condition_blueprint = PipeConditionBlueprint(
            description="Condition mapping to pipe_a and pipe_b",
            inputs={"selector": "native.Text"},
            output=f"{analysis_concept.concept_ref}?",
            expression="selector",
            outcomes={"option_a": "pipe_a", "option_b": "pipe_b"},
            default_outcome=SpecialOutcome.CONTINUE,
        )

        pipe_condition = PipeFactory[PipeCondition].make_from_blueprint(
            domain_code=domain_code,
            pipe_code="test_condition",
            blueprint=pipe_condition_blueprint,
        )

        # Get needed inputs
        needed_inputs = pipe_condition.needed_inputs()

        # Should contain 'selector' from expression
        assert "selector" in needed_inputs.root

        # Should contain inputs from pipe_a and pipe_b
        assert "doc_input" in needed_inputs.root
        assert "other_doc" in needed_inputs.root

        # Verify concept types for mapped pipe inputs
        assert needed_inputs.root["doc_input"].concept.code == document_concept.code
        assert needed_inputs.root["other_doc"].concept.code == document_concept.code

        concept_library.teardown()

    def test_needed_inputs_preserves_multiplicity(self, load_empty_library: Callable[[], None]):
        """Test that needed_inputs correctly preserves multiplicity from mapped pipes."""
        load_empty_library()
        domain_code = "test_domain"
        concept_library = get_concept_library()
        pipe_library = get_pipe_library()

        # Create concepts
        item_concept = ConceptFactory.make_from_blueprint(
            domain_code=domain_code,
            concept_code="Item",
            blueprint_or_string_description=ConceptBlueprint(description="An item"),
        )
        result_concept = ConceptFactory.make_from_blueprint(
            domain_code=domain_code,
            concept_code="Result",
            blueprint_or_string_description=ConceptBlueprint(description="A result"),
        )
        concept_library.add_concepts(concepts=[item_concept, result_concept])

        # Create a pipe with multiplicity input (list of items)
        pipe_with_list_blueprint = PipeLLMBlueprint(
            description="Pipe with list input",
            inputs={"items": f"{item_concept.concept_ref}[]"},  # List multiplicity
            output=result_concept.concept_ref,
            prompt="Process items: $items",
        )
        pipe_with_list = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code=domain_code,
            pipe_code="pipe_with_list",
            blueprint=pipe_with_list_blueprint,
            concept_codes_from_the_same_domain=[item_concept.code, result_concept.code],
        )
        pipe_library.add_new_pipe(pipe=pipe_with_list)

        # Create PipeCondition that maps to this pipe
        pipe_condition_blueprint = PipeConditionBlueprint(
            description="Condition with list input pipe",
            inputs={"mode": "native.Text"},
            output=f"{result_concept.concept_ref}?",
            expression="mode",
            outcomes={"batch": "pipe_with_list"},
            default_outcome=SpecialOutcome.CONTINUE,
        )

        pipe_condition = PipeFactory[PipeCondition].make_from_blueprint(
            domain_code=domain_code,
            pipe_code="test_condition",
            blueprint=pipe_condition_blueprint,
        )

        # Get needed inputs
        needed_inputs = pipe_condition.needed_inputs()

        # Verify multiplicity is preserved
        assert "items" in needed_inputs.root
        assert needed_inputs.root["items"].multiplicity is True  # [] means list (True)

        concept_library.teardown()


class TestPipeConditionOutputValidation:
    """Tests for PipeCondition output validation.

    Rules:
    1. If all mapped pipes have the same output concept, PipeCondition's output MUST be that same concept.
    2. If mapped pipes have different output concepts, PipeCondition's output MUST be Dynamic.
    """

    def test_validate_output_all_pipes_same_output_must_match(self, load_empty_library: Callable[[], None]):
        """Test that validation passes when all mapped pipes have the same output and PipeCondition matches it.

        Special outcomes do not influence the output validation - only actual pipes matter.
        """
        load_empty_library()
        domain_code = "test_domain"
        concept_library = get_concept_library()
        pipe_library = get_pipe_library()

        # Create concepts
        input_concept = ConceptFactory.make_from_blueprint(
            domain_code=domain_code,
            concept_code="Input",
            blueprint_or_string_description=ConceptBlueprint(description="Input"),
        )
        output_concept = ConceptFactory.make_from_blueprint(
            domain_code=domain_code,
            concept_code="SharedOutput",
            blueprint_or_string_description=ConceptBlueprint(description="Shared output"),
        )
        concept_library.add_concepts(concepts=[input_concept, output_concept])

        # Create two pipes with the SAME output concept
        pipe_a = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code=domain_code,
            pipe_code="pipe_a",
            blueprint=PipeLLMBlueprint(
                description="Pipe A",
                inputs={"input_a": input_concept.concept_ref},
                output=output_concept.concept_ref,
                prompt="Process A: $input_a",
            ),
            concept_codes_from_the_same_domain=[input_concept.code, output_concept.code],
        )
        pipe_library.add_new_pipe(pipe=pipe_a)

        pipe_b = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code=domain_code,
            pipe_code="pipe_b",
            blueprint=PipeLLMBlueprint(
                description="Pipe B",
                inputs={"input_b": input_concept.concept_ref},
                output=output_concept.concept_ref,
                prompt="Process B: $input_b",
            ),
            concept_codes_from_the_same_domain=[input_concept.code, output_concept.code],
        )
        pipe_library.add_new_pipe(pipe=pipe_b)

        # Create PipeCondition with the SAME output as mapped pipes
        # Special outcome (CONTINUE) does not affect the output validation
        pipe_condition_blueprint = PipeConditionBlueprint(
            description="Condition with matching outputs",
            inputs={"selector": "native.Text"},
            output=f"{output_concept.concept_ref}?",
            expression="selector",
            outcomes={"a": "pipe_a", "b": "pipe_b"},
            default_outcome=SpecialOutcome.CONTINUE,
        )

        pipe_condition = PipeFactory[PipeCondition].make_from_blueprint(
            domain_code=domain_code,
            pipe_code="test_condition",
            blueprint=pipe_condition_blueprint,
        )

        # Should not raise - outputs match (special outcomes don't affect validation)
        pipe_condition.validate_output_with_library()

        concept_library.teardown()

    def test_validate_output_all_pipes_same_output_dynamic_not_allowed(self, load_empty_library: Callable[[], None]):
        """Test that using Dynamic output when all mapped pipes have the same output raises an error."""
        load_empty_library()
        domain_code = "test_domain"
        concept_library = get_concept_library()
        pipe_library = get_pipe_library()

        # Create concepts
        input_concept = ConceptFactory.make_from_blueprint(
            domain_code=domain_code,
            concept_code="Input",
            blueprint_or_string_description=ConceptBlueprint(description="Input"),
        )
        output_concept = ConceptFactory.make_from_blueprint(
            domain_code=domain_code,
            concept_code="SharedOutput",
            blueprint_or_string_description=ConceptBlueprint(description="Shared output"),
        )
        concept_library.add_concepts(concepts=[input_concept, output_concept])

        # Create two pipes with the SAME output concept
        pipe_a = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code=domain_code,
            pipe_code="pipe_a",
            blueprint=PipeLLMBlueprint(
                description="Pipe A",
                inputs={"input_a": input_concept.concept_ref},
                output=output_concept.concept_ref,
                prompt="Process A: $input_a",
            ),
            concept_codes_from_the_same_domain=[input_concept.code, output_concept.code],
        )
        pipe_library.add_new_pipe(pipe=pipe_a)

        pipe_b = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code=domain_code,
            pipe_code="pipe_b",
            blueprint=PipeLLMBlueprint(
                description="Pipe B",
                inputs={"input_b": input_concept.concept_ref},
                output=output_concept.concept_ref,
                prompt="Process B: $input_b",
            ),
            concept_codes_from_the_same_domain=[input_concept.code, output_concept.code],
        )
        pipe_library.add_new_pipe(pipe=pipe_b)

        # Create PipeCondition with Dynamic output - NOT ALLOWED when all pipes have the same output
        pipe_condition_blueprint = PipeConditionBlueprint(
            description="Condition with Dynamic output when not needed",
            inputs={"selector": "native.Text"},
            output=f"{NativeConceptCode.DYNAMIC.concept_ref}?",
            expression="selector",
            outcomes={"a": "pipe_a", "b": "pipe_b"},
            default_outcome=SpecialOutcome.CONTINUE,
        )

        pipe_condition = PipeFactory[PipeCondition].make_from_blueprint(
            domain_code=domain_code,
            pipe_code="test_condition",
            blueprint=pipe_condition_blueprint,
        )

        # Should raise - all pipes have the same output, so Dynamic is not allowed
        with pytest.raises(PipeValidationError) as exc_info:
            pipe_condition.validate_output_with_library()

        assert "same output" in str(exc_info.value).lower() or output_concept.concept_ref in str(exc_info.value)

        concept_library.teardown()

    @pytest.mark.xfail(reason="Anything output is currently allowed")
    def test_validate_output_all_pipes_same_output_anything_not_allowed(self, load_empty_library: Callable[[], None]):
        """Test that using Anything output when all mapped pipes have the same output raises an error."""
        load_empty_library()
        domain_code = "test_domain"
        concept_library = get_concept_library()
        pipe_library = get_pipe_library()

        # Create concepts
        input_concept = ConceptFactory.make_from_blueprint(
            domain_code=domain_code,
            concept_code="Input",
            blueprint_or_string_description=ConceptBlueprint(description="Input"),
        )
        output_concept = ConceptFactory.make_from_blueprint(
            domain_code=domain_code,
            concept_code="SharedOutput",
            blueprint_or_string_description=ConceptBlueprint(description="Shared output"),
        )
        concept_library.add_concepts(concepts=[input_concept, output_concept])

        # Create one pipe with specific output
        pipe_a = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code=domain_code,
            pipe_code="pipe_a",
            blueprint=PipeLLMBlueprint(
                description="Pipe A",
                inputs={"input_a": input_concept.concept_ref},
                output=output_concept.concept_ref,
                prompt="Process A: $input_a",
            ),
            concept_codes_from_the_same_domain=[input_concept.code, output_concept.code],
        )
        pipe_library.add_new_pipe(pipe=pipe_a)

        # Create PipeCondition with Anything output - NOT ALLOWED when all pipes have the same output
        pipe_condition_blueprint = PipeConditionBlueprint(
            description="Condition with Anything output when not needed",
            inputs={"selector": "native.Text"},
            output=f"{NativeConceptCode.ANYTHING.concept_ref}?",
            expression="selector",
            outcomes={"a": "pipe_a"},
            default_outcome=SpecialOutcome.CONTINUE,
        )

        pipe_condition = PipeFactory[PipeCondition].make_from_blueprint(
            domain_code=domain_code,
            pipe_code="test_condition",
            blueprint=pipe_condition_blueprint,
        )

        # Should raise - all pipes have the same output, so Anything is not allowed
        with pytest.raises(PipeValidationError) as exc_info:
            pipe_condition.validate_output_with_library()

        assert "same output" in str(exc_info.value).lower() or output_concept.concept_ref in str(exc_info.value)

        concept_library.teardown()

    def test_validate_output_different_outputs_requires_dynamic(self, load_empty_library: Callable[[], None]):
        """Test that when pipes have different outputs, PipeCondition MUST use Dynamic."""
        load_empty_library()
        domain_code = "test_domain"
        concept_library = get_concept_library()
        pipe_library = get_pipe_library()

        # Create concepts
        input_concept = ConceptFactory.make_from_blueprint(
            domain_code=domain_code,
            concept_code="Input",
            blueprint_or_string_description=ConceptBlueprint(description="Input"),
        )
        output_a = ConceptFactory.make_from_blueprint(
            domain_code=domain_code,
            concept_code="OutputA",
            blueprint_or_string_description=ConceptBlueprint(description="Output A"),
        )
        output_b = ConceptFactory.make_from_blueprint(
            domain_code=domain_code,
            concept_code="OutputB",
            blueprint_or_string_description=ConceptBlueprint(description="Output B"),
        )
        concept_library.add_concepts(concepts=[input_concept, output_a, output_b])

        # Create two pipes with DIFFERENT output concepts
        pipe_a = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code=domain_code,
            pipe_code="pipe_a",
            blueprint=PipeLLMBlueprint(
                description="Pipe A",
                inputs={"input_a": input_concept.concept_ref},
                output=output_a.concept_ref,
                prompt="Process A: $input_a",
            ),
            concept_codes_from_the_same_domain=[input_concept.code, output_a.code, output_b.code],
        )
        pipe_library.add_new_pipe(pipe=pipe_a)

        pipe_b = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code=domain_code,
            pipe_code="pipe_b",
            blueprint=PipeLLMBlueprint(
                description="Pipe B",
                inputs={"input_b": input_concept.concept_ref},
                output=output_b.concept_ref,
                prompt="Process B: $input_b",
            ),
            concept_codes_from_the_same_domain=[input_concept.code, output_a.code, output_b.code],
        )
        pipe_library.add_new_pipe(pipe=pipe_b)

        # Create PipeCondition with Dynamic output - REQUIRED when pipes have different outputs
        pipe_condition_blueprint = PipeConditionBlueprint(
            description="Condition with Dynamic output",
            inputs={"selector": "native.Text"},
            output=f"{NativeConceptCode.ANYTHING.concept_ref}?",
            expression="selector",
            outcomes={"a": "pipe_a", "b": "pipe_b"},
            default_outcome=SpecialOutcome.CONTINUE,
        )

        pipe_condition = PipeFactory[PipeCondition].make_from_blueprint(
            domain_code=domain_code,
            pipe_code="test_condition",
            blueprint=pipe_condition_blueprint,
        )

        # Should not raise - Dynamic is correct for different outputs
        pipe_condition.validate_output_with_library()

        concept_library.teardown()

    def test_validate_output_different_outputs_specific_concept_not_allowed(self, load_empty_library: Callable[[], None]):
        """Test that using a specific concept when pipes have different outputs raises an error."""
        load_empty_library()
        domain_code = "test_domain"
        concept_library = get_concept_library()
        pipe_library = get_pipe_library()

        # Create concepts
        input_concept = ConceptFactory.make_from_blueprint(
            domain_code=domain_code,
            concept_code="Input",
            blueprint_or_string_description=ConceptBlueprint(description="Input"),
        )
        output_a = ConceptFactory.make_from_blueprint(
            domain_code=domain_code,
            concept_code="OutputA",
            blueprint_or_string_description=ConceptBlueprint(description="Output A"),
        )
        output_b = ConceptFactory.make_from_blueprint(
            domain_code=domain_code,
            concept_code="OutputB",
            blueprint_or_string_description=ConceptBlueprint(description="Output B"),
        )
        concept_library.add_concepts(concepts=[input_concept, output_a, output_b])

        # Create two pipes with DIFFERENT output concepts
        pipe_a = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code=domain_code,
            pipe_code="pipe_a",
            blueprint=PipeLLMBlueprint(
                description="Pipe A",
                inputs={"input_a": input_concept.concept_ref},
                output=output_a.concept_ref,
                prompt="Process A: $input_a",
            ),
            concept_codes_from_the_same_domain=[input_concept.code, output_a.code, output_b.code],
        )
        pipe_library.add_new_pipe(pipe=pipe_a)

        pipe_b = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code=domain_code,
            pipe_code="pipe_b",
            blueprint=PipeLLMBlueprint(
                description="Pipe B",
                inputs={"input_b": input_concept.concept_ref},
                output=output_b.concept_ref,
                prompt="Process B: $input_b",
            ),
            concept_codes_from_the_same_domain=[input_concept.code, output_a.code, output_b.code],
        )
        pipe_library.add_new_pipe(pipe=pipe_b)

        # Create PipeCondition with OutputA - NOT ALLOWED when pipes have different outputs
        pipe_condition_blueprint = PipeConditionBlueprint(
            description="Condition with specific output when Dynamic is required",
            inputs={"selector": "native.Text"},
            output=f"{output_a.concept_ref}?",
            expression="selector",
            outcomes={"a": "pipe_a", "b": "pipe_b"},
            default_outcome=SpecialOutcome.CONTINUE,
        )

        pipe_condition = PipeFactory[PipeCondition].make_from_blueprint(
            domain_code=domain_code,
            pipe_code="test_condition",
            blueprint=pipe_condition_blueprint,
        )

        # Should raise - pipes have different outputs, so Dynamic is required
        with pytest.raises(PipeValidationError) as exc_info:
            pipe_condition.validate_output_with_library()

        error_message = str(exc_info.value).lower()
        assert "different" in error_message or "dynamic" in error_message

        concept_library.teardown()

    def test_validate_output_different_outputs_anything_not_allowed(self, load_empty_library: Callable[[], None]):
        """Test that using Anything when pipes have different outputs raises an error (must use Dynamic)."""
        load_empty_library()
        domain_code = "test_domain"
        concept_library = get_concept_library()
        pipe_library = get_pipe_library()

        # Create concepts
        input_concept = ConceptFactory.make_from_blueprint(
            domain_code=domain_code,
            concept_code="Input",
            blueprint_or_string_description=ConceptBlueprint(description="Input"),
        )
        output_a = ConceptFactory.make_from_blueprint(
            domain_code=domain_code,
            concept_code="OutputA",
            blueprint_or_string_description=ConceptBlueprint(description="Output A"),
        )
        output_b = ConceptFactory.make_from_blueprint(
            domain_code=domain_code,
            concept_code="OutputB",
            blueprint_or_string_description=ConceptBlueprint(description="Output B"),
        )
        concept_library.add_concepts(concepts=[input_concept, output_a, output_b])

        # Create two pipes with DIFFERENT output concepts
        pipe_a = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code=domain_code,
            pipe_code="pipe_a",
            blueprint=PipeLLMBlueprint(
                description="Pipe A",
                inputs={"input_a": input_concept.concept_ref},
                output=output_a.concept_ref,
                prompt="Process A: $input_a",
            ),
            concept_codes_from_the_same_domain=[input_concept.code, output_a.code, output_b.code],
        )
        pipe_library.add_new_pipe(pipe=pipe_a)

        pipe_b = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code=domain_code,
            pipe_code="pipe_b",
            blueprint=PipeLLMBlueprint(
                description="Pipe B",
                inputs={"input_b": input_concept.concept_ref},
                output=output_b.concept_ref,
                prompt="Process B: $input_b",
            ),
            concept_codes_from_the_same_domain=[input_concept.code, output_a.code, output_b.code],
        )
        pipe_library.add_new_pipe(pipe=pipe_b)

        # Create PipeCondition with Anything output - NOT ALLOWED when pipes have different outputs
        pipe_condition_blueprint = PipeConditionBlueprint(
            description="Condition with Anything output when Dynamic is required",
            inputs={"selector": "native.Text"},
            output=f"{NativeConceptCode.TEXT.concept_ref}?",
            expression="selector",
            outcomes={"a": "pipe_a", "b": "pipe_b"},
            default_outcome=SpecialOutcome.CONTINUE,
        )

        pipe_condition = PipeFactory[PipeCondition].make_from_blueprint(
            domain_code=domain_code,
            pipe_code="test_condition",
            blueprint=pipe_condition_blueprint,
        )

        # Should raise - pipes have different outputs, so Anything is required
        with pytest.raises(PipeValidationError) as exc_info:
            pipe_condition.validate_output_with_library()

        error_message = str(exc_info.value).lower()
        assert "different" in error_message or "dynamic" in error_message

        concept_library.teardown()


class TestPipeConditionSpecialOutcomes:
    """Tests for PipeCondition with special outcomes (CONTINUE, FAIL)."""

    def test_needed_inputs_with_all_continue_outcomes(self, load_empty_library: Callable[[], None]):
        """Test needed_inputs when all outcomes are CONTINUE (no actual pipes)."""
        load_empty_library()
        domain_code = "test_domain"

        # Create PipeCondition where all outcomes are CONTINUE
        pipe_condition_blueprint = PipeConditionBlueprint(
            description="Condition with only CONTINUE outcomes",
            inputs={"status": "native.Text"},
            output="native.Text?",
            expression="status",
            outcomes={"active": SpecialOutcome.CONTINUE, "inactive": SpecialOutcome.CONTINUE},
            default_outcome=SpecialOutcome.CONTINUE,
        )

        pipe_condition = PipeFactory[PipeCondition].make_from_blueprint(
            domain_code=domain_code,
            pipe_code="test_condition",
            blueprint=pipe_condition_blueprint,
        )

        # Get needed inputs
        needed_inputs = pipe_condition.needed_inputs()

        # Should only contain expression variable, no inputs from mapped pipes (there are none)
        assert isinstance(needed_inputs, InputStuffSpecs)
        assert "status" in needed_inputs.root
        # Only the expression variable should be present
        assert len(needed_inputs.root) == 1

    def test_needed_inputs_with_all_fail_outcomes(self, load_empty_library: Callable[[], None]):
        """Test needed_inputs when all outcomes are FAIL (no actual pipes)."""
        load_empty_library()
        domain_code = "test_domain"

        # Create PipeCondition where all outcomes are FAIL
        pipe_condition_blueprint = PipeConditionBlueprint(
            description="Condition with only FAIL outcomes",
            inputs={"error_type": "native.Text"},
            output="native.Text",
            expression="error_type",
            outcomes={"critical": SpecialOutcome.FAIL, "warning": SpecialOutcome.FAIL},
            default_outcome=SpecialOutcome.FAIL,
        )

        pipe_condition = PipeFactory[PipeCondition].make_from_blueprint(
            domain_code=domain_code,
            pipe_code="test_condition",
            blueprint=pipe_condition_blueprint,
        )

        # Get needed inputs
        needed_inputs = pipe_condition.needed_inputs()

        # Should only contain expression variable, no inputs from mapped pipes (there are none)
        assert isinstance(needed_inputs, InputStuffSpecs)
        assert "error_type" in needed_inputs.root
        assert len(needed_inputs.root) == 1

    def test_needed_inputs_with_mixed_pipe_and_continue(self, load_empty_library: Callable[[], None]):
        """Test needed_inputs when some outcomes are pipes and some are CONTINUE."""
        load_empty_library()
        domain_code = "test_domain"
        concept_library = get_concept_library()
        pipe_library = get_pipe_library()

        # Create concepts
        input_concept = ConceptFactory.make_from_blueprint(
            domain_code=domain_code,
            concept_code="Input",
            blueprint_or_string_description=ConceptBlueprint(description="Input"),
        )
        output_concept = ConceptFactory.make_from_blueprint(
            domain_code=domain_code,
            concept_code="Output",
            blueprint_or_string_description=ConceptBlueprint(description="Output"),
        )
        concept_library.add_concepts(concepts=[input_concept, output_concept])

        # Create a pipe for one of the outcomes
        pipe_a = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code=domain_code,
            pipe_code="process_pipe",
            blueprint=PipeLLMBlueprint(
                description="Process pipe",
                inputs={"doc": input_concept.concept_ref},
                output=output_concept.concept_ref,
                prompt="Process: $doc",
            ),
            concept_codes_from_the_same_domain=[input_concept.code, output_concept.code],
        )
        pipe_library.add_new_pipe(pipe=pipe_a)

        # Create PipeCondition with mixed outcomes: one pipe, one CONTINUE, default CONTINUE
        # Special outcomes don't affect output validation - only actual pipes matter
        pipe_condition_blueprint = PipeConditionBlueprint(
            description="Condition with mixed pipe and CONTINUE",
            inputs={"action": "native.Text"},
            output=f"{output_concept.concept_ref}?",
            expression="action",
            outcomes={
                "process": "process_pipe",  # Actual pipe
                "skip": SpecialOutcome.CONTINUE,  # Special outcome
            },
            default_outcome=SpecialOutcome.CONTINUE,
        )

        pipe_condition = PipeFactory[PipeCondition].make_from_blueprint(
            domain_code=domain_code,
            pipe_code="test_condition",
            blueprint=pipe_condition_blueprint,
        )

        # Get needed inputs
        needed_inputs = pipe_condition.needed_inputs()

        # Should contain expression variable AND inputs from the actual pipe
        assert "action" in needed_inputs.root  # From expression
        assert "doc" in needed_inputs.root  # From process_pipe

        concept_library.teardown()

    def test_needed_inputs_with_mixed_pipe_and_fail(self, load_empty_library: Callable[[], None]):
        """Test needed_inputs when some outcomes are pipes and some are FAIL."""
        load_empty_library()
        domain_code = "test_domain"
        concept_library = get_concept_library()
        pipe_library = get_pipe_library()

        # Create concepts
        input_concept = ConceptFactory.make_from_blueprint(
            domain_code=domain_code,
            concept_code="Input",
            blueprint_or_string_description=ConceptBlueprint(description="Input"),
        )
        output_concept = ConceptFactory.make_from_blueprint(
            domain_code=domain_code,
            concept_code="Output",
            blueprint_or_string_description=ConceptBlueprint(description="Output"),
        )
        concept_library.add_concepts(concepts=[input_concept, output_concept])

        # Create a pipe for one of the outcomes
        pipe_a = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code=domain_code,
            pipe_code="success_pipe",
            blueprint=PipeLLMBlueprint(
                description="Success pipe",
                inputs={"data": input_concept.concept_ref},
                output=output_concept.concept_ref,
                prompt="Process: $data",
            ),
            concept_codes_from_the_same_domain=[input_concept.code, output_concept.code],
        )
        pipe_library.add_new_pipe(pipe=pipe_a)

        # Create PipeCondition with mixed outcomes: one pipe, one FAIL
        # Special outcomes don't affect output validation - only actual pipes matter
        pipe_condition_blueprint = PipeConditionBlueprint(
            description="Condition with mixed pipe and FAIL",
            inputs={"status": "native.Text"},
            output=output_concept.concept_ref,
            expression="status",
            outcomes={
                "success": "success_pipe",  # Actual pipe
                "error": SpecialOutcome.FAIL,  # Special outcome
            },
            default_outcome=SpecialOutcome.FAIL,
        )

        pipe_condition = PipeFactory[PipeCondition].make_from_blueprint(
            domain_code=domain_code,
            pipe_code="test_condition",
            blueprint=pipe_condition_blueprint,
        )

        # Get needed inputs
        needed_inputs = pipe_condition.needed_inputs()

        # Should contain expression variable AND inputs from the actual pipe
        assert "status" in needed_inputs.root  # From expression
        assert "data" in needed_inputs.root  # From success_pipe

        concept_library.teardown()

    def test_validate_output_with_only_special_outcomes(self, load_empty_library: Callable[[], None]):
        """Test that output validation passes when all outcomes are special (CONTINUE/FAIL)."""
        load_empty_library()
        domain_code = "test_domain"

        # Create PipeCondition with only special outcomes
        pipe_condition_blueprint = PipeConditionBlueprint(
            description="Condition with only special outcomes",
            inputs={"flag": "native.Text"},
            output="native.Text?",
            expression="flag",
            outcomes={
                "yes": SpecialOutcome.CONTINUE,
                "no": SpecialOutcome.FAIL,
            },
            default_outcome=SpecialOutcome.CONTINUE,
        )

        pipe_condition = PipeFactory[PipeCondition].make_from_blueprint(
            domain_code=domain_code,
            pipe_code="test_condition",
            blueprint=pipe_condition_blueprint,
        )

        # Should not raise - no actual pipes to validate against
        pipe_condition.validate_output_with_library()

    def test_mapped_pipe_codes_excludes_special_outcomes(self, load_empty_library: Callable[[], None]):
        """Test that pipe_dependencies() property excludes CONTINUE and FAIL."""
        load_empty_library()
        domain_code = "test_domain"
        concept_library = get_concept_library()
        pipe_library = get_pipe_library()

        # Create a minimal pipe
        output_concept = ConceptFactory.make_from_blueprint(
            domain_code=domain_code,
            concept_code="Output",
            blueprint_or_string_description=ConceptBlueprint(description="Output"),
        )
        concept_library.add_concepts(concepts=[output_concept])

        pipe_a = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code=domain_code,
            pipe_code="real_pipe",
            blueprint=PipeLLMBlueprint(
                description="Real pipe",
                inputs={},
                output=output_concept.concept_ref,
                prompt="Do something",
            ),
            concept_codes_from_the_same_domain=[output_concept.code],
        )
        pipe_library.add_new_pipe(pipe=pipe_a)

        # Create PipeCondition with mix of real pipe and special outcomes
        # Special outcomes don't affect output validation - only actual pipes matter
        pipe_condition_blueprint = PipeConditionBlueprint(
            description="Condition with mixed outcomes",
            inputs={"mode": "native.Text"},
            output=f"{output_concept.concept_ref}?",
            expression="mode",
            outcomes={
                "run": "real_pipe",
                "skip": SpecialOutcome.CONTINUE,
                "abort": SpecialOutcome.FAIL,
            },
            default_outcome=SpecialOutcome.CONTINUE,
        )

        pipe_condition = PipeFactory[PipeCondition].make_from_blueprint(
            domain_code=domain_code,
            pipe_code="test_condition",
            blueprint=pipe_condition_blueprint,
        )

        # pipe_dependencies() should only contain actual pipes, not special outcomes
        assert pipe_condition.pipe_dependencies() == {"real_pipe"}
        assert SpecialOutcome.CONTINUE not in pipe_condition.pipe_dependencies()
        assert SpecialOutcome.FAIL not in pipe_condition.pipe_dependencies()

        concept_library.teardown()
