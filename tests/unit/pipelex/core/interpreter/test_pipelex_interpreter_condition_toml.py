"""Test PipelexInterpreter Condition pipe to TOML string conversion."""

import pytest

from pipelex.core.interpreter import PipelexInterpreter
from pipelex.pipe_controllers.condition.pipe_condition_blueprint import PipeConditionBlueprint, PipeConditionPipeMapBlueprint


class TestPipelexInterpreterConditionToml:
    """Test Condition pipe to TOML string conversion."""

    @pytest.mark.parametrize(
        "pipe_name,blueprint,expected_toml",
        [
            # Basic Condition pipe with expression
            (
                "conditional_process",
                PipeConditionBlueprint(
                    type="PipeCondition",
                    definition="Process based on condition",
                    output="ProcessedData",
                    pipe_map=PipeConditionPipeMapBlueprint({"small": "process_small", "large": "process_large"}),
                    expression="input_data.category",
                ),
                """[pipe.conditional_process]
type = "PipeCondition"
definition = "Process based on condition"
output = "ProcessedData"
pipe_map = { small = "process_small", large = "process_large" }
expression = "input_data.category\"""",
            ),
            # Condition pipe with expression template and inputs
            (
                "complex_condition",
                PipeConditionBlueprint(
                    type="PipeCondition",
                    definition="Complex conditional processing",
                    inputs={"data": "Text", "threshold": "Text"},
                    output="ProcessedData",
                    pipe_map=PipeConditionPipeMapBlueprint({"low": "process_low", "medium": "process_medium", "high": "process_high"}),
                    expression_template="{{ data.size if data.size > threshold else 'low' }}",
                ),
                """[pipe.complex_condition]
type = "PipeCondition"
definition = "Complex conditional processing"
inputs = { data = "Text", threshold = "Text" }
output = "ProcessedData"
pipe_map = { low = "process_low", medium = "process_medium", high = "process_high" }
expression_template = "{{ data.size if data.size > threshold else 'low' }}\"""",
            ),
        ],
    )
    def test_condition_pipe_to_toml_string(self, pipe_name: str, blueprint: PipeConditionBlueprint, expected_toml: str):
        """Test converting Condition pipe blueprint to TOML string."""
        result = PipelexInterpreter.condition_pipe_to_toml_string(pipe_name, blueprint, "test_domain")
        assert result == expected_toml
