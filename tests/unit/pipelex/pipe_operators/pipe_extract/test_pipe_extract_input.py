import pytest

from pipelex import log
from pipelex.exceptions import StaticValidationError
from pipelex.pipe_operators.extract.pipe_extract_blueprint import PipeExtractBlueprint
from pipelex.pipe_operators.extract.pipe_extract_factory import PipeExtractFactory
from tests.unit.pipelex.pipe_operators.pipe_extract.data import PipeExtractInputTestCases


class TestPipeExtractValidateInputs:
    @pytest.mark.parametrize(
        ("test_id", "blueprint"),
        PipeExtractInputTestCases.VALID_CASES,
    )
    def test_validate_inputs_valid_cases(
        self,
        test_id: str,
        blueprint: PipeExtractBlueprint,
    ):
        log.debug(f"Testing valid case: {test_id}")

        # Validation happens automatically during instantiation via model_validator
        pipe_extract = PipeExtractFactory.make_from_blueprint(
            domain="test_domain",
            pipe_code=f"test_pipe_{test_id}",
            blueprint=blueprint,
        )

        # Assert that the pipe was created successfully
        assert pipe_extract is not None
        assert pipe_extract.code == f"test_pipe_{test_id}"

    @pytest.mark.parametrize(
        ("test_id", "blueprint", "expected_error_message_fragment"),
        PipeExtractInputTestCases.ERROR_CASES,
    )
    def test_validate_inputs_error_cases(
        self,
        test_id: str,
        blueprint: PipeExtractBlueprint,
        expected_error_message_fragment: str,
    ):
        log.debug(f"Testing error case: {test_id}")

        with pytest.raises(StaticValidationError) as exc_info:
            PipeExtractFactory.make_from_blueprint(
                domain="test_domain",
                pipe_code=f"test_pipe_{test_id}",
                blueprint=blueprint,
            )

        error_str = str(exc_info.value)
        assert expected_error_message_fragment in error_str, (
            f"Expected fragment '{expected_error_message_fragment}' not found in error message: {error_str}"
        )
