from typing import Any

import pytest

from pipelex import log
from pipelex.exceptions import PipeDefinitionError, StaticValidationError
from pipelex.pipe_controllers.parallel.pipe_parallel_blueprint import PipeParallelBlueprint
from pipelex.pipe_controllers.parallel.pipe_parallel_factory import PipeParallelFactory
from tests.unit.pipelex.pipe_controllers.parallel.data import PipeParallelInputTestCases


class TestPipeParallelValidateInputs:
    @pytest.mark.parametrize(
        ("test_id", "blueprint"),
        PipeParallelInputTestCases.VALID_CASES,
    )
    def test_validate_inputs_valid_cases(
        self,
        test_id: str,
        blueprint: PipeParallelBlueprint,
    ):
        log.verbose(f"Testing valid case: {test_id}")

        # Validation happens automatically during instantiation via model_validator
        pipe_parallel = PipeParallelFactory.make_from_blueprint(
            domain="test_domain",
            pipe_code=f"test_pipe_{test_id}",
            blueprint=blueprint,
        )

        # Assert that the pipe was created successfully
        assert pipe_parallel is not None
        assert pipe_parallel.code == f"test_pipe_{test_id}"

    @pytest.mark.parametrize(
        ("test_id", "blueprint_dict", "expected_error_message_fragment"),
        PipeParallelInputTestCases.ERROR_CASES,
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
            blueprint = PipeParallelBlueprint.model_validate(blueprint_dict)
            PipeParallelFactory.make_from_blueprint(
                domain="test_domain",
                pipe_code=f"test_pipe_{test_id}",
                blueprint=blueprint,
            )

        error_str = str(exc_info.value)
        assert expected_error_message_fragment in error_str, (
            f"Expected fragment '{expected_error_message_fragment}' not found in error message: {error_str}"
        )
