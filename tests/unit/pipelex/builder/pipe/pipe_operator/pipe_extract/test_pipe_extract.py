import pytest

from pipelex import log
from pipelex.builder.pipe.pipe_extract_spec import PipeExtractSpec
from pipelex.pipe_operators.extract.pipe_extract_blueprint import PipeExtractBlueprint
from tests.unit.pipelex.builder.pipe.pipe_operator.pipe_extract.test_data import PipeExtractTestCases


class TestPipeExtractBlueprintConversion:
    @pytest.mark.parametrize(
        ("test_name", "pipe_spec", "expected_blueprint"),
        PipeExtractTestCases.TEST_CASES,
    )
    def test_pipe_extract_spec_to_blueprint(
        self,
        test_name: str,
        pipe_spec: PipeExtractSpec,
        expected_blueprint: PipeExtractBlueprint,
    ):
        log.verbose(f"Testing {test_name}")
        result = pipe_spec.to_blueprint()
        assert result == expected_blueprint
