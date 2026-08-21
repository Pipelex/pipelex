from typing import Any, Callable

import pytest

from pipelex import log
from pipelex.core.pipes.exceptions import PipeValidationError
from pipelex.pipe_controllers.parallel.pipe_parallel import PipeParallel
from pipelex.pipe_controllers.parallel.pipe_parallel_blueprint import PipeParallelBlueprint
from pipelex.pipe_machinery.pipe_factory import PipeFactory
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
        load_empty_library: Callable[[], None],
    ):
        load_empty_library()
        log.verbose(f"Testing valid case: {test_id}")

        # Validation happens automatically during instantiation via model_validator
        pipe_parallel = PipeFactory[PipeParallel].make_from_blueprint(
            domain_code="test_domain",
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
        load_empty_library: Callable[[], None],
    ):
        load_empty_library()
        log.verbose(f"Testing error case: {test_id}")

        with pytest.raises((PipeValidationError, ValueError)) as exc_info:  # ruff: ignore[pytest-raises-with-multiple-statements]
            # Construct blueprint from dict at test time to trigger validation
            blueprint = PipeParallelBlueprint.model_validate(blueprint_dict)
            pipe_parallel = PipeFactory[PipeParallel].make_from_blueprint(
                domain_code="test_domain",
                pipe_code=f"test_pipe_{test_id}",
                blueprint=blueprint,
            )
            pipe_parallel.validate_with_libraries()

        error_str = str(exc_info.value)
        assert expected_error_message_fragment in error_str, (
            f"Expected fragment '{expected_error_message_fragment}' not found in error message: {error_str}"
        )
