import pytest

from pipelex.libraries.pipelines.builder.pipe.pipe_llm_spec import PipeLLMSpec
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint

from .test_data import PipeLLMTestCases


class TestPipeLLMBlueprintConversion:
    @pytest.mark.parametrize(
        "test_name,pipe_spec,expected_blueprint",
        PipeLLMTestCases.TEST_CASES,
    )
    def test_pipe_llm_spec_to_blueprint(self, test_name: str, pipe_spec: PipeLLMSpec, expected_blueprint: PipeLLMBlueprint):
        result = pipe_spec.to_blueprint()
        assert result == expected_blueprint
