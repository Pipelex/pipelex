from typing import Any, Callable

import pytest

from pipelex import log
from pipelex.core.pipes.exceptions import PipeValidationError
from pipelex.pipe_controllers.condition.pipe_condition import PipeCondition
from pipelex.pipe_controllers.condition.pipe_condition_blueprint import PipeConditionBlueprint
from pipelex.pipe_machinery.pipe_factory import PipeFactory
from tests.unit.pipelex.pipe_controllers.condition.data import PipeConditionInputTestCases


class TestPipeConditionValidateInputs:
    @pytest.mark.parametrize(
        ("test_id", "blueprint"),
        PipeConditionInputTestCases.VALID_CASES,
    )
    def test_validate_inputs_valid_cases(
        self,
        test_id: str,
        blueprint: PipeConditionBlueprint,
        load_empty_library: Callable[[], None],
    ):
        load_empty_library()
        log.verbose(f"Testing valid case: {test_id}")

        # Validation happens automatically during instantiation via model_validator
        pipe_condition = PipeFactory[PipeCondition].make_from_blueprint(
            domain_code="test_domain",
            pipe_code=f"test_pipe_{test_id}",
            blueprint=blueprint,
        )

        # Assert that the pipe was created successfully
        assert pipe_condition is not None
        assert pipe_condition.code == f"test_pipe_{test_id}"

    @pytest.mark.parametrize(
        ("test_id", "blueprint_dict", "expected_error_message_fragment"),
        PipeConditionInputTestCases.ERROR_CASES,
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
            blueprint = PipeConditionBlueprint.model_validate(blueprint_dict)
            pipe_condition = PipeFactory[PipeCondition].make_from_blueprint(
                domain_code="test_domain",
                pipe_code=f"test_pipe_{test_id}",
                blueprint=blueprint,
            )
            pipe_condition.validate_with_libraries()

        error_str = str(exc_info.value)
        assert expected_error_message_fragment in error_str, (
            f"Expected fragment '{expected_error_message_fragment}' not found in error message: {error_str}"
        )
