from typing import Any

import pytest

from pipelex import log
from pipelex.core.exceptions import StaticValidationError
from pipelex.core.pipe_errors import PipeDefinitionError
from pipelex.pipe_controllers.sequence.pipe_sequence_blueprint import PipeSequenceBlueprint
from pipelex.pipe_controllers.sequence.pipe_sequence_factory import PipeSequenceFactory
from tests.unit.pipe_controllers.sequence.data import PipeSequenceInputTestCases


class TestPipeSequenceValidateInputs:
    @pytest.mark.parametrize(
        ("test_id", "blueprint"),
        PipeSequenceInputTestCases.VALID_CASES,
    )
    def test_validate_inputs_valid_cases(
        self,
        test_id: str,
        blueprint: PipeSequenceBlueprint,
    ):
        log.verbose(f"Testing valid case: {test_id}")

        # Validation happens automatically during instantiation via model_validator
        pipe_sequence = PipeSequenceFactory.make_from_blueprint(
            domain="test_domain",
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
    ):
        log.verbose(f"Testing error case: {test_id}")

        with pytest.raises((StaticValidationError, ValueError, PipeDefinitionError)) as exc_info:  # noqa: PT012
            # Construct blueprint from dict at test time to trigger validation
            blueprint = PipeSequenceBlueprint.model_validate(blueprint_dict)
            PipeSequenceFactory.make_from_blueprint(
                domain="test_domain",
                pipe_code=f"test_pipe_{test_id}",
                blueprint=blueprint,
            )

        error_str = str(exc_info.value)
        assert expected_error_message_fragment in error_str, (
            f"Expected fragment '{expected_error_message_fragment}' not found in error message: {error_str}"
        )
