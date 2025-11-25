from typing import Callable

import pytest

from pipelex import log
from pipelex.core.pipes.exceptions import PipeValidationError, PipeValidationErrorType
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
        load_empty_library: Callable[[], None],
    ):
        load_empty_library()
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
        ("test_id", "blueprint", "expected_error_type"),
        PipeImgGenInputTestCases.ERROR_CASES,
    )
    def test_validate_inputs_error_cases(
        self,
        test_id: str,
        blueprint: PipeImgGenBlueprint,
        expected_error_type: PipeValidationErrorType,
        load_empty_library: Callable[[], None],
    ):
        load_empty_library()
        log.verbose(f"Testing error case: {test_id}")

        with pytest.raises(PipeValidationError) as exc_info:
            PipeImgGenFactory.make_from_blueprint(
                domain="test_domain",
                pipe_code=f"test_pipe_{test_id}",
                blueprint=blueprint,
            ).validate_with_libraries()

        # Verify the error type matches
        assert exc_info.value.error_type == expected_error_type, f"Expected error type {expected_error_type}, but got {exc_info.value.error_type}"
