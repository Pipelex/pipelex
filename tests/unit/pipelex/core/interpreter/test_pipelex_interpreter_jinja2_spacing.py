import pytest

from pipelex.core.interpreter import PipelexInterpreter
from pipelex.pipe_operators.jinja2.pipe_jinja2_blueprint import PipeJinja2Blueprint


class TestPipelexInterpreterJinja2PipePLX:
    @pytest.mark.parametrize(
        "pipe_name,blueprint,expected_plx",
        [
            # Basic Jinja2 pipe
            (
                "greeting_pipe",
                PipeJinja2Blueprint(
                    type="PipeJinja2",
                    definition="Process a Jinja2 template",
                    output="Text",
                    jinja2="Hello {{ name }}!",
                ),
                """[pipe.greeting_pipe]
type = "PipeJinja2"
definition = "Process a Jinja2 template"
output = "Text"
jinja2 = "Hello {{ name }}!\"""",
            ),
            # Jinja2 pipe with inputs
            (
                "template_pipe",
                PipeJinja2Blueprint(
                    type="PipeJinja2",
                    definition="Process template with inputs",
                    inputs={"name": "Text", "greeting": "Text"},
                    output="Text",
                    jinja2="{{ greeting }} {{ name }}!",
                ),
                """[pipe.template_pipe]
type = "PipeJinja2"
definition = "Process template with inputs"
inputs = { name = "Text", greeting = "Text" }
output = "Text"
jinja2 = "{{ greeting }} {{ name }}!\"""",
            ),
            # Jinja2 pipe with complex template
            (
                "complex_pipe",
                PipeJinja2Blueprint(
                    type="PipeJinja2",
                    definition="Process complex template",
                    output="Text",
                    jinja2="{% for item in items %}{{ item.name }}{% endfor %}",
                ),
                """[pipe.complex_pipe]
type = "PipeJinja2"
definition = "Process complex template"
output = "Text"
jinja2 = "{% for item in items %}{{ item.name }}{% endfor %}\"""",
            ),
            # Jinja2 pipe with jinja2_name instead of inline jinja2
            (
                "named_template_pipe",
                PipeJinja2Blueprint(
                    type="PipeJinja2",
                    definition="Use named template",
                    output="Text",
                    jinja2_name="greeting_template",
                ),
                """[pipe.named_template_pipe]
type = "PipeJinja2"
definition = "Use named template"
output = "Text"
jinja2_name = "greeting_template\"""",
            ),
        ],
    )
    def test_jinja2_pipe_to_plx_string(self, pipe_name: str, blueprint: PipeJinja2Blueprint, expected_plx: str):
        result = PipelexInterpreter.jinja2_pipe_to_plx_string(pipe_name, blueprint)
        assert result == expected_plx
