import pytest

from pipelex import log
from pipelex.pipe_operators.func.pipe_func_blueprint import PipeFuncBlueprint
from pipelex.pipe_operators.func.pipe_func_factory import PipeFuncFactory
from tests.unit.pipelex.pipe_operators.pipe_func.data import PipeFuncInputTestCases


class TestPipeFuncValidateInputs:
    @pytest.mark.parametrize(
        ("test_id", "blueprint"),
        PipeFuncInputTestCases.VALID_CASES,
    )
    def test_validate_inputs_valid_cases(
        self,
        test_id: str,
        blueprint: PipeFuncBlueprint,
    ):
        log.verbose(f"Testing valid case: {test_id}")

        pipe_func = PipeFuncFactory.make_from_blueprint(
            domain="test_domain",
            pipe_code=f"test_pipe_{test_id}",
            blueprint=blueprint,
        )

        # Assert that the pipe was created successfully
        assert pipe_func is not None
        assert pipe_func.code == f"test_pipe_{test_id}"
        assert pipe_func.function_name == blueprint.function_name
