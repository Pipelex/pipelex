from typing import Callable

import pytest

from pipelex import log
from pipelex.pipe_machinery.pipe_factory import PipeFactory
from pipelex.pipe_operators.compose.pipe_compose import PipeCompose
from pipelex.pipe_operators.compose.pipe_compose_blueprint import PipeComposeBlueprint
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
        load_empty_library: Callable[[], None],
    ):
        load_empty_library()
        log.verbose(f"Testing valid case: {test_id}")

        # Validation happens automatically during instantiation via model_validator
        pipe_compose = PipeFactory[PipeCompose].make_from_blueprint(
            domain_code="test_domain",
            pipe_code=f"test_pipe_{test_id}",
            blueprint=blueprint,
        )

        # Assert that the pipe was created successfully
        assert pipe_compose is not None
        assert pipe_compose.code == f"test_pipe_{test_id}"
