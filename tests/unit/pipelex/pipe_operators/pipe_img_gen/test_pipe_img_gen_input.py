import pytest

from pipelex import log
from pipelex.core.pipe_errors import PipeDefinitionError
from pipelex.exceptions import StaticValidationError
from pipelex.pipe_operators.img_gen.pipe_img_gen_blueprint import PipeImgGenBlueprint
from pipelex.pipe_operators.img_gen.pipe_img_gen_factory import PipeImgGenFactory
from tests.unit.pipelex.pipe_operators.pipe_img_gen.data import PipeImgGenInputTestCases


class TestPipeImgGenValidateInputs:
    @pytest.mark.parametrize(
        ("test_id", "blueprint"),
        PipeImgGenInputTestCases.VALID_CASES,
    )
    def test_validate_inputs_valid_cases(
        self,
        test_id: str,
        blueprint: PipeImgGenBlueprint,
    ):
        log.verbose(f"Testing valid case: {test_id}")

        pipe_img_gen = PipeImgGenFactory.make_from_blueprint(
            domain="test_domain",
            pipe_code=f"test_pipe_{test_id}",
            blueprint=blueprint,
        )

        # Assert that the pipe was created successfully
        assert pipe_img_gen is not None
        assert pipe_img_gen.code == f"test_pipe_{test_id}"

    @pytest.mark.parametrize(
        ("test_id", "blueprint", "expected_error_message_fragment"),
        PipeImgGenInputTestCases.ERROR_CASES,
    )
    def test_validate_inputs_error_cases(
        self,
        test_id: str,
        blueprint: PipeImgGenBlueprint,
        expected_error_message_fragment: str,
    ):
        log.verbose(f"Testing error case: {test_id}")

        with pytest.raises((StaticValidationError, PipeDefinitionError)) as exc_info:
            PipeImgGenFactory.make_from_blueprint(
                domain="test_domain",
                pipe_code=f"test_pipe_{test_id}",
                blueprint=blueprint,
            )

        error_str = str(exc_info.value)
        assert expected_error_message_fragment in error_str, (
            f"Expected fragment '{expected_error_message_fragment}' not found in error message: {error_str}"
        )
