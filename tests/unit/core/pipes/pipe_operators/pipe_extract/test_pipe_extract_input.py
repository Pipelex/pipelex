import pytest

from pipelex import log
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
        log.verbose(f"Testing valid case: {test_id}")

        # Validation happens automatically during instantiation via model_validator
        pipe_extract = PipeExtractFactory.make_from_blueprint(
            domain="test_domain",
            pipe_code=f"test_pipe_{test_id}",
            blueprint=blueprint,
        )

        # Assert that the pipe was created successfully
        assert pipe_extract is not None
        assert pipe_extract.code == f"test_pipe_{test_id}"
