from typing import Callable

import pytest

from pipelex import log
from pipelex.pipe_controllers.batch.pipe_batch import PipeBatch
from pipelex.pipe_controllers.batch.pipe_batch_blueprint import PipeBatchBlueprint
from pipelex.pipe_machinery.pipe_factory import PipeFactory
from tests.unit.pipelex.pipe_controllers.batch.data import PipeBatchInputTestCases


class TestPipeBatchValidateInputs:
    @pytest.mark.parametrize(
        ("test_id", "blueprint"),
        PipeBatchInputTestCases.VALID_CASES,
    )
    def test_validate_inputs_valid_cases(
        self,
        test_id: str,
        blueprint: PipeBatchBlueprint,
        load_empty_library: Callable[[], None],
    ):
        load_empty_library()
        log.verbose(f"Testing valid case: {test_id}")

        # Validation happens automatically during instantiation via model_validator
        pipe_batch = PipeFactory[PipeBatch].make_from_blueprint(
            domain_code="test_domain",
            pipe_code=f"test_pipe_{test_id}",
            blueprint=blueprint,
        )

        # Assert that the pipe was created successfully
        assert pipe_batch is not None
        assert pipe_batch.code == f"test_pipe_{test_id}"
