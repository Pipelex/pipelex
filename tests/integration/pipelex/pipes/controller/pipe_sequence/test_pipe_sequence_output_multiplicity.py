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

        domain = "test_multiplicity"

        # Create a PipeLLM with multiple output (output_multiplicity=3)
        llm_blueprint = PipeLLMBlueprint(
            description="LLM that outputs multiple",
            inputs={"input_text": "Text"},
            output="Text[3]",  # Multiple output
            model="llm_for_testing_gen_text",
            prompt="@input_text",
        )
        llm_pipe = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code=domain,
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
            domain_code=domain,
            pipe_code="sequence_mismatch",
            blueprint=sequence_blueprint,
        )
        get_pipe_library().add_new_pipe(sequence_pipe)

        # Validation should fail due to multiplicity mismatch
        with pytest.raises(PipeValidationError) as exc_info:
            sequence_pipe.validate_with_libraries()

        error_message = str(exc_info.value).lower()
        assert "multiplicity" in error_message, f"Error should mention multiplicity mismatch, got: {exc_info.value}"
