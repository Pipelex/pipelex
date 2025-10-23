import pytest

from pipelex import log
from pipelex.exceptions import StaticValidationError
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint
from pipelex.pipe_operators.llm.pipe_llm_factory import PipeLLMFactory
from tests.unit.pipe_operators.pipe_llm.data import PipeLLMInputTestCases


class TestPipeLLMValidateInputs:
    @pytest.mark.parametrize(
        ("test_id", "blueprint"),
        PipeLLMInputTestCases.VALID_CASES,
    )
    def test_validate_inputs_valid_cases(
        self,
        test_id: str,
        blueprint: PipeLLMBlueprint,
    ):
        log.verbose(f"Testing valid case: {test_id}")

        pipe_llm = PipeLLMFactory.make_from_blueprint(
            domain="test_domain",
            pipe_code=f"test_pipe_{test_id}",
            blueprint=blueprint,
        )

        pipe_llm.validate_inputs()

    @pytest.mark.parametrize(
        ("test_id", "blueprint", "expected_error_message_fragment"),
        PipeLLMInputTestCases.ERROR_CASES,
    )
    def test_validate_inputs_error_cases(
        self,
        test_id: str,
        blueprint: PipeLLMBlueprint,
        expected_error_message_fragment: str,
    ):
        log.verbose(f"Testing error case: {test_id}")

        with pytest.raises(StaticValidationError) as exc_info:
            PipeLLMFactory.make_from_blueprint(
                domain="test_domain",
                pipe_code=f"test_pipe_{test_id}",
                blueprint=blueprint,
            )

        error_str = str(exc_info.value)
        assert expected_error_message_fragment in error_str, (
            f"Expected fragment '{expected_error_message_fragment}' not found in error message: {error_str}"
        )
