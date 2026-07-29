from pathlib import Path
from typing import Callable

import pytest

from pipelex import log
from pipelex.pipe_machinery.pipe_factory import PipeFactory
from pipelex.pipe_operators.func.pipe_func import PipeFunc
from pipelex.pipe_operators.func.pipe_func_blueprint import PipeFuncBlueprint
from tests.unit.pipelex.pipe_operators.pipe_func.data import PipeFuncInputTestCases


class TestPipeFuncValidation:
    """Test PipeFunc with valid, registered, and functioning functions.

    Error cases (function not found, invalid return types, etc.) are tested
    at the registry level in test_func_registry_utils.py.
    """

    @pytest.mark.parametrize(
        ("test_id", "blueprint"),
        PipeFuncInputTestCases.VALID_CASES,
    )
    def test_pipe_func_with_valid_functions(
        self,
        test_id: str,
        blueprint: PipeFuncBlueprint,
        load_test_library: Callable[[list[Path]], None],
    ):
        load_test_library([Path(Path(__file__).parent)])
        """Test that PipeFunc works correctly with valid, registered functions."""
        log.verbose(f"Testing valid case: {test_id}")

        pipe_func = PipeFactory[PipeFunc].make_from_blueprint(
            domain_code="test_domain",
            pipe_code=f"test_pipe_{test_id}",
            blueprint=blueprint,
        )

        # Assert that the pipe was created successfully
        assert pipe_func is not None
        assert pipe_func.code == f"test_pipe_{test_id}"
        assert pipe_func.function_name == blueprint.function_name
