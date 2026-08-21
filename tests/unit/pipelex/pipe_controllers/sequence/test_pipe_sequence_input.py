from typing import Any, Callable

import pytest

from pipelex import log
from pipelex.core.pipes.exceptions import PipeValidationError
from pipelex.pipe_controllers.sequence.pipe_sequence import PipeSequence
from pipelex.pipe_controllers.sequence.pipe_sequence_blueprint import PipeSequenceBlueprint
from pipelex.pipe_machinery.pipe_factory import PipeFactory
from tests.unit.pipelex.pipe_controllers.sequence.data import PipeSequenceInputTestCases


class TestPipeSequenceValidateInputs:
    @pytest.mark.parametrize(
        ("test_id", "blueprint"),
        PipeSequenceInputTestCases.VALID_CASES,
    )
    def test_validate_inputs_valid_cases(
        self,
        test_id: str,
        blueprint: PipeSequenceBlueprint,
        load_empty_library: Callable[[], None],
    ):
        load_empty_library()
        log.verbose(f"Testing valid case: {test_id}")

        # Validation happens automatically during instantiation via model_validator
        pipe_sequence = PipeFactory[PipeSequence].make_from_blueprint(
            domain_code="test_domain",
            pipe_code=f"test_pipe_{test_id}",
            blueprint=blueprint,
        )

        # Assert that the pipe was created successfully
        assert pipe_sequence is not None
        assert pipe_sequence.code == f"test_pipe_{test_id}"

    @pytest.mark.parametrize(
        ("test_id", "blueprint_dict", "expected_error_message_fragment"),
        PipeSequenceInputTestCases.ERROR_CASES,
    )
    def test_validate_inputs_error_cases(
        self,
        test_id: str,
        blueprint_dict: dict[str, Any],
        expected_error_message_fragment: str,
        load_empty_library: Callable[[], None],
    ):
        load_empty_library()
        log.verbose(f"Testing error case: {test_id}")

        with pytest.raises((PipeValidationError, ValueError)) as exc_info:  # ruff: ignore[pytest-raises-with-multiple-statements]
            # Construct blueprint from dict at test time to trigger validation
            blueprint = PipeSequenceBlueprint.model_validate(blueprint_dict)
            pipe_sequence = PipeFactory[PipeSequence].make_from_blueprint(
                domain_code="test_domain",
                pipe_code=f"test_pipe_{test_id}",
                blueprint=blueprint,
            )
            pipe_sequence.validate_with_libraries()

        error_str = str(exc_info.value)
        assert expected_error_message_fragment in error_str, (
            f"Expected fragment '{expected_error_message_fragment}' not found in error message: {error_str}"
        )
