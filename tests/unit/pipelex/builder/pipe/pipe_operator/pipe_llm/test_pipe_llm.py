import pytest

from pipelex import pretty_print
from pipelex.builder.pipe.pipe_llm_spec import PipeLLMSpec
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint
from pipelex.pipe_operators.llm.pipe_llm_factory import PipeLLMFactory
from tests.unit.pipelex.builder.pipe.pipe_operator.pipe_llm.test_data import PipeLLMTestCases


class TestPipeLLMBlueprintConversion:
    @pytest.mark.parametrize(
        ("test_name", "pipe_spec", "expected_blueprint"),
        PipeLLMTestCases.TEST_CASES,
    )
    def test_pipe_llm_spec_to_blueprint(self, test_name: str, pipe_spec: PipeLLMSpec, expected_blueprint: PipeLLMBlueprint):
        blueprint = pipe_spec.to_blueprint()
        assert blueprint == expected_blueprint

        pipe_llm_from_blueprint = PipeLLMFactory.make_from_blueprint(
            domain="test_domain",
            pipe_code=f"test_pipe_{test_name}",
            blueprint=blueprint,
        )
        pretty_print(pipe_llm_from_blueprint, title="PipeLLM from blueprint")
