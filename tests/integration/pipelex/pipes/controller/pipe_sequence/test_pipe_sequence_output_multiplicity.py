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
            model="$testing-text",
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

        error_str = str(exc_info.value)
        error_message = error_str.lower()
        assert "multiplicity" in error_message, f"Error should mention multiplicity mismatch, got: {exc_info.value}"
        # The message must speak author syntax (Text vs Text[3]) and name the concrete fix, never the
        # internal repr (`multiplicity=None/True`).
        assert "multiplicity=" not in error_str, f"Message leaks internal repr: {error_str}"
        assert "declares its output as 'Text'" in error_str, error_str
        assert "yields 'Text[3]'" in error_str, error_str
        assert "Update the sequence's output to 'Text[3]'" in error_str, error_str

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
            model="$testing-text",
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
            model="$testing-text",
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
            model="$testing-text",
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

    def test_fixed_multiplicity_compatible_with_variable_multiplicity(
        self,
        load_empty_library: Callable[[], str],
    ):
        """Test that validation passes when last step has [3] and sequence has [].

        Creates:
        - A PipeLLM with output="Text[3]" (fixed multiplicity)
        - A PipeSequence with output="Text[]" (variable multiplicity)

        A fixed multiplicity is compatible with a variable multiplicity expectation
        because a fixed count of items fulfills the "list of items" requirement.
        """
        load_empty_library()

        domain_code = "test_fixed_vs_variable"

        # Create a PipeLLM with fixed multiplicity
        llm_blueprint = PipeLLMBlueprint(
            description="LLM with fixed output count",
            inputs={"input_text": "Text"},
            output="Text[3]",  # Fixed multiplicity of 3
            model="$testing-text",
            prompt="@input_text",
        )
        llm_pipe = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code=domain_code,
            pipe_code="llm_fixed_3",
            blueprint=llm_blueprint,
        )
        get_pipe_library().add_new_pipe(llm_pipe)

        # Create a PipeSequence with variable multiplicity
        # This is COMPATIBLE: fixed count fulfills variable expectation
        sequence_blueprint = PipeSequenceBlueprint(
            description="Sequence with variable output",
            inputs={"input_text": "Text"},
            output="Text[]",  # Variable multiplicity - compatible with fixed
            steps=[
                SubPipeBlueprint(pipe="llm_fixed_3", result="result"),
            ],
        )
        sequence_pipe = PipeFactory[PipeSequence].make_from_blueprint(
            domain_code=domain_code,
            pipe_code="sequence_fixed_to_variable",
            blueprint=sequence_blueprint,
        )
        get_pipe_library().add_new_pipe(sequence_pipe)

        # Validation should pass - fixed multiplicity is compatible with variable
        sequence_pipe.validate_with_libraries()

    def test_variable_multiplicity_incompatible_with_fixed_multiplicity(
        self,
        load_empty_library: Callable[[], str],
    ):
        """Test that validation fails when last step has [] but sequence has [3].

        Creates:
        - A PipeLLM with output="Text[]" (variable multiplicity)
        - A PipeSequence with output="Text[3]" (fixed multiplicity)

        A variable multiplicity cannot fulfill a fixed count expectation because
        we cannot guarantee the exact number of items will be produced.
        """
        load_empty_library()

        domain = "test_variable_vs_fixed"

        # Create a PipeLLM with variable multiplicity
        llm_blueprint = PipeLLMBlueprint(
            description="LLM with variable output count",
            inputs={"input_text": "Text"},
            output="Text[]",  # Variable multiplicity
            model="$testing-text",
            prompt="@input_text",
        )
        llm_pipe = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code=domain,
            pipe_code="llm_variable",
            blueprint=llm_blueprint,
        )
        get_pipe_library().add_new_pipe(llm_pipe)

        # Create a PipeSequence with fixed multiplicity - INCOMPATIBLE
        sequence_blueprint = PipeSequenceBlueprint(
            description="Sequence with fixed output count",
            inputs={"input_text": "Text"},
            output="Text[3]",  # Fixed multiplicity - cannot be fulfilled by variable
            steps=[
                SubPipeBlueprint(pipe="llm_variable", result="result"),
            ],
        )
        sequence_pipe = PipeFactory[PipeSequence].make_from_blueprint(
            domain_code=domain,
            pipe_code="sequence_variable_to_fixed",
            blueprint=sequence_blueprint,
        )
        get_pipe_library().add_new_pipe(sequence_pipe)

        # Validation should fail - variable cannot fulfill fixed expectation
        with pytest.raises(PipeValidationError) as exc_info:
            sequence_pipe.validate_with_libraries()

        error_message = str(exc_info.value).lower()
        assert "multiplicity" in error_message, f"Error should mention multiplicity mismatch, got: {exc_info.value}"

    def test_batch_over_with_variable_multiplicity_passes(
        self,
        load_empty_library: Callable[[], str],
    ):
        """Test that validation passes when last step uses batch_over/batch_as and sequence has [].

        When a step has batch_over and batch_as, the effective output multiplicity should be
        variable (True), since batching produces multiple outputs.

        Creates:
        - A PipeLLM with output="Text" (single output)
        - A PipeSequence with output="Text[]" where last step has batch_over/batch_as
        The validation should pass because batch_over/batch_as makes the effective multiplicity True.
        """
        load_empty_library()

        domain = "test_batch_over_variable"

        # Create a PipeLLM with single output (process_cv in the example)
        llm_blueprint = PipeLLMBlueprint(
            description="LLM that processes single item",
            inputs={"cv_pdf": "Document"},
            output="Text",  # Single output
            model="$testing-text",
            prompt="@cv_pdf",
        )
        llm_pipe = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code=domain,
            pipe_code="process_cv",
            blueprint=llm_blueprint,
        )
        get_pipe_library().add_new_pipe(llm_pipe)

        # Create a PipeSequence with variable multiplicity where last step batches
        sequence_blueprint = PipeSequenceBlueprint(
            description="Sequence that batches over CVs",
            inputs={"cvs": "Document[]"},  # Multiple PDFs input
            output="Text[]",  # Variable multiplicity output - should match batch_over effect
            steps=[
                SubPipeBlueprint(
                    pipe="process_cv",
                    result="match_analyses",
                    batch_over="cvs",
                    batch_as="cv_pdf",
                ),
            ],
        )
        sequence_pipe = PipeFactory[PipeSequence].make_from_blueprint(
            domain_code=domain,
            pipe_code="sequence_batch_variable",
            blueprint=sequence_blueprint,
        )
        get_pipe_library().add_new_pipe(sequence_pipe)

        # Validation should pass - batch_over/batch_as makes effective multiplicity True
        sequence_pipe.validate_with_libraries()

    def test_batch_over_with_no_multiplicity_fails(
        self,
        load_empty_library: Callable[[], str],
    ):
        """Test that validation fails when last step uses batch_over/batch_as but sequence has no multiplicity.

        When a step has batch_over and batch_as, the effective output multiplicity should be
        variable (True). The sequence must declare output="Concept[]" to match.

        Creates:
        - A PipeLLM with output="Text" (single output)
        - A PipeSequence with output="Text" (no multiplicity) where last step has batch_over/batch_as
        The validation should fail because batch_over/batch_as makes multiplicity True, but sequence says None.
        """
        load_empty_library()

        domain = "test_batch_over_no_mult"

        # Create a PipeLLM with single output
        llm_blueprint = PipeLLMBlueprint(
            description="LLM that processes single item",
            inputs={"cv_pdf": "Document"},
            output="Text",  # Single output
            model="$testing-text",
            prompt="@cv_pdf",
        )
        llm_pipe = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code=domain,
            pipe_code="process_cv_single",
            blueprint=llm_blueprint,
        )
        get_pipe_library().add_new_pipe(llm_pipe)

        # Create a PipeSequence with NO multiplicity where last step batches - MISMATCH
        sequence_blueprint = PipeSequenceBlueprint(
            description="Sequence that batches but declares single output",
            inputs={"cvs": "Document[]"},  # Multiple PDFs input
            output="Text",  # No multiplicity - MISMATCH with batch effect!
            steps=[
                SubPipeBlueprint(
                    pipe="process_cv_single",
                    result="match_analyses",
                    batch_over="cvs",
                    batch_as="cv_pdf",
                ),
            ],
        )
        sequence_pipe = PipeFactory[PipeSequence].make_from_blueprint(
            domain_code=domain,
            pipe_code="sequence_batch_mismatch",
            blueprint=sequence_blueprint,
        )
        get_pipe_library().add_new_pipe(sequence_pipe)

        # Validation should fail due to multiplicity mismatch
        with pytest.raises(PipeValidationError) as exc_info:
            sequence_pipe.validate_with_libraries()

        error_message = str(exc_info.value).lower()
        assert "multiplicity" in error_message, f"Error should mention multiplicity mismatch, got: {exc_info.value}"

    def test_batch_over_with_nb_output_fixed_multiplicity(
        self,
        load_empty_library: Callable[[], str],
    ):
        """Test that when last step has batch_over/batch_as AND nb_output, multiplicity uses nb_output.

        When a step has batch_over, batch_as, AND nb_output=3, the effective output multiplicity
        should be 3, not True.

        Creates:
        - A PipeLLM with output="Text" (single output)
        - A PipeSequence with output="Text[3]" where last step has batch_over/batch_as and nb_output=3
        The validation should pass because nb_output=3 overrides to give multiplicity=3.
        """
        load_empty_library()

        domain = "test_batch_over_nb_output"

        # Create a PipeLLM with single output
        llm_blueprint = PipeLLMBlueprint(
            description="LLM that processes single item",
            inputs={"cv_pdf": "Document"},
            output="Text",  # Single output
            model="$testing-text",
            prompt="@cv_pdf",
        )
        llm_pipe = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code=domain,
            pipe_code="process_cv_fixed",
            blueprint=llm_blueprint,
        )
        get_pipe_library().add_new_pipe(llm_pipe)

        # Create a PipeSequence with fixed multiplicity where last step batches with nb_output
        sequence_blueprint = PipeSequenceBlueprint(
            description="Sequence that batches with fixed output count",
            inputs={"cvs": "Document[]"},  # Multiple PDFs input
            output="Text[6]",  # Fixed multiplicity - should match nb_output
            steps=[
                SubPipeBlueprint(
                    pipe="process_cv_fixed",
                    result="match_analyses",
                    batch_over="cvs",
                    batch_as="cv_pdf",
                    nb_output=6,  # Fixed output count
                ),
            ],
        )
        sequence_pipe = PipeFactory[PipeSequence].make_from_blueprint(
            domain_code=domain,
            pipe_code="sequence_batch_fixed",
            blueprint=sequence_blueprint,
        )
        get_pipe_library().add_new_pipe(sequence_pipe)

        # Validation should pass - nb_output=3 gives multiplicity=3
        sequence_pipe.validate_with_libraries()

    def test_nb_output_only_fixed_multiplicity(
        self,
        load_empty_library: Callable[[], str],
    ):
        """Test that when last step has ONLY nb_output (no batch_over/batch_as), multiplicity uses nb_output.

        Creates:
        - A PipeLLM with output="Text" (single output)
        - A PipeSequence with output="Text[5]" where last step has nb_output=5 only
        The validation should pass because nb_output=5 gives multiplicity=5.
        """
        load_empty_library()

        domain = "test_nb_output_only"

        # Create a PipeLLM with single output
        llm_blueprint = PipeLLMBlueprint(
            description="LLM that processes single item",
            inputs={"input_text": "Text"},
            output="Text",  # Single output
            model="$testing-text",
            prompt="@input_text",
        )
        llm_pipe = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code=domain,
            pipe_code="single_output_llm",
            blueprint=llm_blueprint,
        )
        get_pipe_library().add_new_pipe(llm_pipe)

        # Create a PipeSequence with fixed multiplicity where last step has nb_output only
        sequence_blueprint = PipeSequenceBlueprint(
            description="Sequence with fixed output count via nb_output",
            inputs={"input_text": "Text"},
            output="Text[5]",  # Fixed multiplicity - should match nb_output
            steps=[
                SubPipeBlueprint(
                    pipe="single_output_llm",
                    result="results",
                    nb_output=5,  # Fixed output count, no batch_over/batch_as
                ),
            ],
        )
        sequence_pipe = PipeFactory[PipeSequence].make_from_blueprint(
            domain_code=domain,
            pipe_code="sequence_nb_output_only",
            blueprint=sequence_blueprint,
        )
        get_pipe_library().add_new_pipe(sequence_pipe)

        # Validation should pass - nb_output=5 gives multiplicity=5
        sequence_pipe.validate_with_libraries()

    def test_multiple_output_only_variable_multiplicity(
        self,
        load_empty_library: Callable[[], str],
    ):
        """Test that when last step has ONLY multiple_output=True (no nb_output, no batch_over/batch_as), multiplicity is True.

        Creates:
        - A PipeLLM with output="Text" (single output)
        - A PipeSequence with output="Text[]" where last step has multiple_output=True only
        The validation should pass because multiple_output=True gives multiplicity=True.
        """
        load_empty_library()

        domain = "test_multiple_output_only"

        # Create a PipeLLM with single output
        llm_blueprint = PipeLLMBlueprint(
            description="LLM that processes single item",
            inputs={"input_text": "Text"},
            output="Text",  # Single output
            model="$testing-text",
            prompt="@input_text",
        )
        llm_pipe = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code=domain,
            pipe_code="single_output_llm_mult",
            blueprint=llm_blueprint,
        )
        get_pipe_library().add_new_pipe(llm_pipe)

        # Create a PipeSequence with variable multiplicity where last step has multiple_output only
        sequence_blueprint = PipeSequenceBlueprint(
            description="Sequence with variable output via multiple_output",
            inputs={"input_text": "Text"},
            output="Text[]",  # Variable multiplicity - should match multiple_output=True
            steps=[
                SubPipeBlueprint(
                    pipe="single_output_llm_mult",
                    result="results",
                    multiple_output=True,  # Variable output, no nb_output, no batch_over/batch_as
                ),
            ],
        )
        sequence_pipe = PipeFactory[PipeSequence].make_from_blueprint(
            domain_code=domain,
            pipe_code="sequence_multiple_output_only",
            blueprint=sequence_blueprint,
        )
        get_pipe_library().add_new_pipe(sequence_pipe)

        # Validation should pass - multiple_output=True gives multiplicity=True
        sequence_pipe.validate_with_libraries()
