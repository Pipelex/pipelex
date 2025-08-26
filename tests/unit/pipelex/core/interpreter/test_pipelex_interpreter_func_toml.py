"""Test PipelexInterpreter Func pipe to TOML string conversion."""

import pytest

from pipelex.core.interpreter import PipelexInterpreter
from pipelex.pipe_operators.func.pipe_func_blueprint import PipeFuncBlueprint


class TestPipelexInterpreterFuncToml:
    """Test Func pipe to TOML string conversion."""

    @pytest.mark.parametrize(
        "pipe_name,blueprint,expected_toml",
        [
            # Basic Func pipe
            (
                "process_data",
                PipeFuncBlueprint(
                    type="PipeFunc",
                    definition="Process data with function",
                    output="ProcessedData",
                    function_name="process_data_function",
                ),
                """[pipe.process_data]
type = "PipeFunc"
definition = "Process data with function"
output = "ProcessedData"
function_name = "process_data_function\"""",
            ),
            # Func pipe with inputs
            (
                "transform_data",
                PipeFuncBlueprint(
                    type="PipeFunc",
                    definition="Transform input data",
                    inputs={"data": "Text", "config": "Text"},
                    output="TransformedData",
                    function_name="transform_function",
                ),
                """[pipe.transform_data]
type = "PipeFunc"
definition = "Transform input data"
inputs = { data = "Text", config = "Text" }
output = "TransformedData"
function_name = "transform_function\"""",
            ),
        ],
    )
    def test_func_pipe_to_toml_string(self, pipe_name: str, blueprint: PipeFuncBlueprint, expected_toml: str):
        """Test converting Func pipe blueprint to TOML string."""
        result = PipelexInterpreter.func_pipe_to_toml_string(pipe_name, blueprint, "test_domain")
        assert result == expected_toml
