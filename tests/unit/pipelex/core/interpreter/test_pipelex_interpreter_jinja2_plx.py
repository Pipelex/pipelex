import pytest

from pipelex.core.interpreter import PipelexInterpreter
from pipelex.pipe_operators.jinja2.pipe_jinja2_blueprint import PipeJinja2Blueprint


class TestPipelexInterpreterJinja2PLX:
    @pytest.mark.parametrize(
        "pipe_name,blueprint,expected_plx",
        [
            # Basic Jinja2 pipe
            (
                "process_template",
                PipeJinja2Blueprint(
                    type="PipeJinja2",
                    definition="Process a Jinja2 template",
                    output="Text",
                    jinja2="Hello {{ name }}!",
                ),
                """[pipe.process_template]
type = "PipeJinja2"
definition = "Process a Jinja2 template"
output = "Text"
jinja2 = "Hello {{ name }}!\"""",
            ),
            # Jinja2 pipe with inputs and named template
            (
                "format_data",
                PipeJinja2Blueprint(
                    type="PipeJinja2",
                    definition="Format data with template",
                    inputs={"data": "Text", "format": "Text"},
                    output="Text",
                    jinja2_name="data_formatter",
                ),
                """[pipe.format_data]
type = "PipeJinja2"
definition = "Format data with template"
inputs = { data = "Text", format = "Text" }
output = "Text"
jinja2_name = "data_formatter\"""",
            ),
        ],
    )
    def test_jinja2_pipe_to_plx_string(self, pipe_name: str, blueprint: PipeJinja2Blueprint, expected_plx: str):
        result = PipelexInterpreter.jinja2_pipe_to_plx_string(pipe_name, blueprint)
        assert result == expected_plx
