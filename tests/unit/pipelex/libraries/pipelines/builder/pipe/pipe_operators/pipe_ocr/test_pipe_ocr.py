import pytest

from pipelex.libraries.pipelines.builder.pipe.pipe_ocr_spec import PipeOcrSpec
from pipelex.pipe_operators.ocr.pipe_ocr_blueprint import PipeOcrBlueprint

from pipelex import log
from tests.unit.pipelex.libraries.pipelines.builder.pipe.pipe_operators.pipe_ocr.test_data import PipeOcrTestCases


class TestPipeOcrBlueprintConversion:
    @pytest.mark.parametrize(
        "test_name,pipe_spec,expected_blueprint",
        PipeOcrTestCases.TEST_CASES,
    )
    def test_pipe_ocr_spec_to_blueprint(
        self,
        test_name: str,
        pipe_spec: PipeOcrSpec,
        expected_blueprint: PipeOcrBlueprint,
    ):
        log.verbose(f"Testing {test_name}")
        result = pipe_spec.to_blueprint()
        assert result == expected_blueprint
