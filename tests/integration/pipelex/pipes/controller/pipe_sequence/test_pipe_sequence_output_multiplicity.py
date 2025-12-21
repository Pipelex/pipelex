"""Test for PipeSequence output multiplicity validation."""

from typing import Callable

import pytest

from pipelex.core.pipes.exceptions import PipeValidationError
from pipelex.core.pipes.pipe_factory import PipeFactory
from pipelex.hub import get_pipe_library
from pipelex.pipe_controllers.sequence.pipe_sequence import PipeSequence
from pipelex.pipe_controllers.sequence.pipe_sequence_blueprint import PipeSequenceBlueprint
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint
from pipelex.pipe_operators.llm.pipe_llm import PipeLLM
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint


class TestPipeSequenceOutputMultiplicity:
    """Test that PipeSequence validates output multiplicity matches the last step."""

    def test_multiplicity_mismatch_raises_error(
        self,
        load_empty_library: Callable[[], str],
    ):
        """Test that validation fails when sequence output multiplicity doesn't match last step.

        Creates:
        - A PipeLLM with output_multiplicity=3 (output="Text[3]")
        - A PipeSequence with output_multiplicity=None (output="Text")
        The validation should fail because multiplicities don't match.
        """
        load_empty_library()

        domain_code = "test_multiplicity"

        # Create a PipeLLM with multiple output (output_multiplicity=3)
        llm_blueprint = PipeLLMBlueprint(
            description="LLM that outputs multiple",
            inputs={"input_text": "Text"},
            output="Text[3]",  # Multiple output
            model="llm_for_testing_gen_text",
            prompt="@input_text",
        )
        llm_pipe = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code=domain_code,
            pipe_code="llm_multiple_output",
            blueprint=llm_blueprint,
        )
        get_pipe_library().add_new_pipe(llm_pipe)

        # Create a PipeSequence with single output (output_multiplicity=None)
        sequence_blueprint = PipeSequenceBlueprint(
            description="Sequence with single output",
            inputs={"input_text": "Text"},
            output="Text",  # Single output - MISMATCH!
            steps=[
                SubPipeBlueprint(pipe="llm_multiple_output", result="result"),
            ],
        )
        sequence_pipe = PipeFactory[PipeSequence].make_from_blueprint(
            domain_code=domain_code,
            pipe_code="sequence_mismatch",
            blueprint=sequence_blueprint,
        )
        get_pipe_library().add_new_pipe(sequence_pipe)

        # Validation should fail due to multiplicity mismatch
        with pytest.raises(PipeValidationError) as exc_info:
            sequence_pipe.validate_with_libraries()

        error_message = str(exc_info.value).lower()
        assert "multiplicity" in error_message, f"Error should mention multiplicity mismatch, got: {exc_info.value}"

    def test_no_multiplicity_matching_passes(
        self,
        load_empty_library: Callable[[], str],
    ):
        """Test that validation passes when both sequence and last step have no multiplicity.

        Creates:
        - A PipeLLM with output="Text" (no multiplicity)
        - A PipeSequence with output="Text" (no multiplicity)
        The validation should pass because multiplicities match (both None).
        """
        load_empty_library()

        domain_code = "test_no_multiplicity"

        # Create a PipeLLM with single output (no multiplicity)
        llm_blueprint = PipeLLMBlueprint(
            description="LLM with single output",
            inputs={"input_text": "Text"},
            output="Text",  # Single output
            model="llm_for_testing_gen_text",
            prompt="@input_text",
        )
        llm_pipe = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code=domain_code,
            pipe_code="llm_single_output",
            blueprint=llm_blueprint,
        )
        get_pipe_library().add_new_pipe(llm_pipe)

        # Create a PipeSequence with single output (no multiplicity) - MATCHES
        sequence_blueprint = PipeSequenceBlueprint(
            description="Sequence with single output",
            inputs={"input_text": "Text"},
            output="Text",  # Single output - MATCHES!
            steps=[
                SubPipeBlueprint(pipe="llm_single_output", result="result"),
            ],
        )
        sequence_pipe = PipeFactory[PipeSequence].make_from_blueprint(
            domain_code=domain_code,
            pipe_code="sequence_matching",
            blueprint=sequence_blueprint,
        )
        get_pipe_library().add_new_pipe(sequence_pipe)

        # Validation should pass - no exception raised
        sequence_pipe.validate_with_libraries()

    def test_variable_multiplicity_matching_passes(
        self,
        load_empty_library: Callable[[], str],
    ):
        """Test that validation passes when both have variable multiplicity [].

        Creates:
        - A PipeLLM with output="Text[]" (variable multiplicity)
        - A PipeSequence with output="Text[]" (variable multiplicity)
        The validation should pass because multiplicities match (both True).
        """
        load_empty_library()

        domain_code = "test_variable_multiplicity"

        # Create a PipeLLM with variable multiplicity output
        llm_blueprint = PipeLLMBlueprint(
            description="LLM with variable output",
            inputs={"input_text": "Text"},
            output="Text[]",  # Variable multiplicity
            model="llm_for_testing_gen_text",
            prompt="@input_text",
        )
        llm_pipe = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code=domain_code,
            pipe_code="llm_variable_output",
            blueprint=llm_blueprint,
        )
        get_pipe_library().add_new_pipe(llm_pipe)

        # Create a PipeSequence with variable multiplicity - MATCHES
        sequence_blueprint = PipeSequenceBlueprint(
            description="Sequence with variable output",
            inputs={"input_text": "Text"},
            output="Text[]",  # Variable multiplicity - MATCHES!
            steps=[
                SubPipeBlueprint(pipe="llm_variable_output", result="result"),
            ],
        )
        sequence_pipe = PipeFactory[PipeSequence].make_from_blueprint(
            domain_code=domain_code,
            pipe_code="sequence_variable_matching",
            blueprint=sequence_blueprint,
        )
        get_pipe_library().add_new_pipe(sequence_pipe)

        # Validation should pass - no exception raised
        sequence_pipe.validate_with_libraries()

    def test_variable_vs_none_multiplicity_mismatch(
        self,
        load_empty_library: Callable[[], str],
    ):
        """Test that validation fails when last step has [] but sequence has none.

        Creates:
        - A PipeLLM with output="Text[]" (variable multiplicity)
        - A PipeSequence with output="Text" (no multiplicity)
        The validation should fail because multiplicities don't match.
        """
        load_empty_library()

        domain_code = "test_variable_vs_none"

        # Create a PipeLLM with variable multiplicity
        llm_blueprint = PipeLLMBlueprint(
            description="LLM with variable output",
            inputs={"input_text": "Text"},
            output="Text[]",  # Variable multiplicity
            model="llm_for_testing_gen_text",
            prompt="@input_text",
        )
        llm_pipe = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code=domain_code,
            pipe_code="llm_variable",
            blueprint=llm_blueprint,
        )
        get_pipe_library().add_new_pipe(llm_pipe)

        # Create a PipeSequence with no multiplicity - MISMATCH
        sequence_blueprint = PipeSequenceBlueprint(
            description="Sequence with single output",
            inputs={"input_text": "Text"},
            output="Text",  # No multiplicity - MISMATCH!
            steps=[
                SubPipeBlueprint(pipe="llm_variable", result="result"),
            ],
        )
        sequence_pipe = PipeFactory[PipeSequence].make_from_blueprint(
            domain_code=domain_code,
            pipe_code="sequence_mismatch_var_none",
            blueprint=sequence_blueprint,
        )
        get_pipe_library().add_new_pipe(sequence_pipe)

        # Validation should fail due to multiplicity mismatch
        with pytest.raises(PipeValidationError) as exc_info:
            sequence_pipe.validate_with_libraries()

        error_message = str(exc_info.value).lower()
        assert "multiplicity" in error_message, f"Error should mention multiplicity mismatch, got: {exc_info.value}"

    def test_fixed_vs_variable_multiplicity_mismatch(
        self,
        load_empty_library: Callable[[], str],
    ):
        """Test that validation fails when last step has [3] but sequence has [].

        Creates:
        - A PipeLLM with output="Text[3]" (fixed multiplicity)
        - A PipeSequence with output="Text[]" (variable multiplicity)
        The validation should fail because multiplicities don't match (3 vs True).
        """
        load_empty_library()

        domain_code = "test_fixed_vs_variable"

        # Create a PipeLLM with fixed multiplicity
        llm_blueprint = PipeLLMBlueprint(
            description="LLM with fixed output count",
            inputs={"input_text": "Text"},
            output="Text[3]",  # Fixed multiplicity of 3
            model="llm_for_testing_gen_text",
            prompt="@input_text",
        )
        llm_pipe = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code=domain_code,
            pipe_code="llm_fixed_3",
            blueprint=llm_blueprint,
        )
        get_pipe_library().add_new_pipe(llm_pipe)

        # Create a PipeSequence with variable multiplicity - MISMATCH
        sequence_blueprint = PipeSequenceBlueprint(
            description="Sequence with variable output",
            inputs={"input_text": "Text"},
            output="Text[]",  # Variable multiplicity - MISMATCH!
            steps=[
                SubPipeBlueprint(pipe="llm_fixed_3", result="result"),
            ],
        )
        sequence_pipe = PipeFactory[PipeSequence].make_from_blueprint(
            domain_code=domain_code,
            pipe_code="sequence_mismatch_fixed_var",
            blueprint=sequence_blueprint,
        )
        get_pipe_library().add_new_pipe(sequence_pipe)

        # Validation should fail due to multiplicity mismatch
        with pytest.raises(PipeValidationError) as exc_info:
            sequence_pipe.validate_with_libraries()

        error_message = str(exc_info.value).lower()
        assert "multiplicity" in error_message, f"Error should mention multiplicity mismatch, got: {exc_info.value}"
