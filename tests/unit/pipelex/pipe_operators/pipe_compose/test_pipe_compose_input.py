import pytest

from pipelex import log
from pipelex.pipe_operators.compose.pipe_compose_blueprint import PipeComposeBlueprint
from pipelex.pipe_operators.compose.pipe_compose_factory import PipeComposeFactory
from tests.unit.pipelex.pipe_operators.pipe_compose.data import PipeComposeInputTestCases


class TestPipeComposeValidateInputs:
    @pytest.mark.parametrize(
        ("test_id", "blueprint"),
        PipeComposeInputTestCases.VALID_CASES,
    )
    def test_validate_inputs_valid_cases(
        self,
        test_id: str,
        blueprint: PipeComposeBlueprint,
    ):
        log.debug(f"Testing valid case: {test_id}")

        # Validation happens automatically during instantiation via model_validator
        pipe_compose = PipeComposeFactory.make_from_blueprint(
            domain="test_domain",
            pipe_code=f"test_pipe_{test_id}",
            blueprint=blueprint,
        )

        # Assert that the pipe was created successfully
        assert pipe_compose is not None
        assert pipe_compose.code == f"test_pipe_{test_id}"

    @pytest.mark.parametrize(
        ("test_id", "blueprint", "expected_error_type", "expected_error_message_fragment"),
        PipeComposeInputTestCases.ERROR_CASES,
    )
    def test_validate_inputs_error_cases(
        self,
        test_id: str,
        blueprint: PipeComposeBlueprint,
        expected_error_type: type[Exception],
        expected_error_message_fragment: str,
    ):
        log.debug(f"Testing error case: {test_id}")

        with pytest.raises(expected_error_type) as exc_info:
            PipeComposeFactory.make_from_blueprint(
                domain="test_domain",
                pipe_code=f"test_pipe_{test_id}",
                blueprint=blueprint,
            )

        error_str = str(exc_info.value)
        assert expected_error_message_fragment in error_str, (
            f"Expected fragment '{expected_error_message_fragment}' not found in error message: {error_str}"
        )
