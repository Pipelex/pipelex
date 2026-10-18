import json

import pytest
import typer
from mthds.protocol.problem.registry import CoreCode

from pipelex.base_exceptions import PipelexError
from pipelex.cli.agent_cli.commands.agent_output import agent_error_markdown, run_failure_fields
from pipelex.errors.problem import ProblemView, problem_metadata
from pipelex.pipeline.exceptions import PipelineExecutionError
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from tests.integration.pipelex.pipeline.test_data import SecurityRefusalTestData

# A construct whose fields render templates, one at its root and one inside a nested field.
_CONSTRUCT_MTHDS = """
domain = "template_refusal_construct"
description = "Compose a photo from a topic"
main_pipe = "make_photo"

[concept.Photo]
description = "A photo with a caption"

[concept.Photo.structure]
caption = { type = "text", description = "The caption" }
picture = { type = "concept", concept_ref = "native.Image", description = "The picture" }

[pipe.make_photo]
type = "PipeCompose"
description = "Build a photo"
inputs = { topic = "Text" }
output = "Photo"

[pipe.make_photo.construct]
caption = { template = "CAPTION_SLOT" }

[pipe.make_photo.construct.picture]
url = { template = "URL_SLOT" }
"""

# A condition whose field, written as a template or as an expression, reads a private name its own source spells.
_CONDITION_MTHDS = """
domain = "template_refusal_condition"
description = "Route a topic"
main_pipe = "route_topic"

[pipe.route_topic]
type = "PipeCondition"
description = "Choose where a topic goes"
inputs = { topic = "Text" }
output = "Text"
EXPRESSION_LINE
outcomes = { loud = "say_it" }
default_outcome = "say_it"

[pipe.say_it]
type = "PipeCompose"
description = "Say the topic"
inputs = { topic = "Text" }
output = "Text"
template = "$topic"
"""


def _compose_bundle(*, template: str) -> str:
    return SecurityRefusalTestData.COMPOSE_MTHDS.replace(SecurityRefusalTestData.COMPOSE_MTHDS_SLOT, template)


async def _refused_run(*, template: str, topic: str) -> PipelineExecutionError:
    with pytest.raises(PipelexError) as exc_info:
        await PipelexMTHDSProtocol().execute(mthds_contents=[_compose_bundle(template=template)], inputs={"topic": topic})
    error = exc_info.value
    assert isinstance(error, PipelineExecutionError)
    return error


def _agent_markdown(*, error: PipelineExecutionError, capsys: pytest.CaptureFixture[str]) -> str:
    """What `pipelex-agent run --error-format markdown` prints for the failed run."""
    with pytest.raises(typer.Exit):
        agent_error_markdown(error.message, error_type="PipelineExecutionError", cause=error, **run_failure_fields(error=error))
    return capsys.readouterr().err


@pytest.mark.asyncio(loop_scope="class")
class TestTemplateRefusalNames:
    @pytest.mark.parametrize(
        "template",
        [SecurityRefusalTestData.PRIVATE_READ_TEMPLATE, SecurityRefusalTestData.FORMAT_LITERAL_TEMPLATE],
        ids=["read_by_key", "read_through_a_format_string_literal"],
    )
    async def test_a_name_the_template_spells_reaches_the_caller_located_on_the_template_field(self, template: str) -> None:
        """The refused name is the template's own, so the problem names it and locates it on the pipe and its template field.

        A name written inside a string literal, which a format string reads, is the template's own text too: naming it
        leaks nothing of the run's data.
        """
        error = await _refused_run(template=template, topic=SecurityRefusalTestData.TOPIC)

        caller = error.to_problem(view=ProblemView.CALLER)

        assert caller.code == CoreCode.SECURITY_TEMPLATE_REFUSED
        assert caller.params is not None
        assert caller.params.as_wire() == {"pipe": "say", "name": "_owner"}
        assert caller.detail == "A template of pipe 'say' reached for '_owner', which the template sandbox forbids."
        assert caller.next_step.detail == "Remove '_owner' from the templates of pipe 'say', then run the method again."
        assert caller.location is not None
        assert caller.location.as_wire() == {"pipe": "say", "path": ["say"], "field": "template"}

    async def test_a_name_the_run_s_data_gave_reaches_no_reader(self, capsys: pytest.CaptureFixture[str]) -> None:
        """A template looking the refused name up from the run's data: the input value reaches no view, no message and no Markdown.

        The problem carries no `name`, its sentences say that the template looked a name up from the run's data, and it
        is located on the pipe and its template field.
        """
        marker = SecurityRefusalTestData.DATA_NAMED_TOPIC
        error = await _refused_run(template=SecurityRefusalTestData.DATA_NAMED_TEMPLATE, topic=marker)

        operator = error.to_problem(view=ProblemView.OPERATOR)
        caller = error.to_problem(view=ProblemView.CALLER)
        markdown = _agent_markdown(error=error, capsys=capsys)

        assert caller.code == CoreCode.SECURITY_TEMPLATE_REFUSED
        assert marker not in error.message
        assert marker not in json.dumps(operator.to_wire())
        assert marker not in json.dumps(caller.to_wire())
        assert marker not in json.dumps(problem_metadata(problem=operator).to_wire())
        assert marker not in markdown
        assert caller.params is not None
        assert caller.params.as_wire() == {"pipe": "say"}
        assert caller.detail == "A template of pipe 'say' looked a name up from the run's data, and the template sandbox refused that name."
        assert caller.next_step.detail == (
            "Change the templates of pipe 'say' so that the run's data no longer chooses the names they look up, then run the method again."
        )
        assert caller.location is not None
        assert caller.location.as_wire() == {"pipe": "say", "path": ["say"], "field": "template"}
        assert "# Error: PipelineExecutionError" in markdown

    @pytest.mark.parametrize(
        ("caption_template", "url_template", "expected_field"),
        [
            ("{{ topic['_owner'] }}", "https://example.com/photo.png", "construct.caption"),
            ("A caption", "{{ topic['_owner'] }}", "construct.picture.url"),
        ],
    )
    async def test_a_construct_field_s_template_is_located_on_its_path(self, caption_template: str, url_template: str, expected_field: str) -> None:
        """A construct's template is located by its path from the construct's root, through a nested field too."""
        bundle = _CONSTRUCT_MTHDS.replace("CAPTION_SLOT", caption_template).replace("URL_SLOT", url_template)
        with pytest.raises(PipelexError) as exc_info:
            await PipelexMTHDSProtocol().execute(mthds_contents=[bundle], inputs={"topic": SecurityRefusalTestData.TOPIC})

        caller = exc_info.value.to_problem(view=ProblemView.CALLER)

        assert caller.code == CoreCode.SECURITY_TEMPLATE_REFUSED
        assert caller.location is not None
        assert caller.location.as_wire() == {"pipe": "make_photo", "path": ["make_photo"], "field": expected_field}

    @pytest.mark.parametrize(
        ("expression_line", "expected_field"),
        [
            ("expression_template = \"{{ topic['_owner'] }}\"", "expression_template"),
            ("expression = \"topic['_owner']\"", "expression"),
        ],
    )
    async def test_a_condition_s_refusal_is_located_on_the_field_the_bundle_wrote(self, expression_line: str, expected_field: str) -> None:
        """A condition writes its expression as a template or as an expression: its refusal names the field it wrote."""
        bundle = _CONDITION_MTHDS.replace("EXPRESSION_LINE", expression_line)
        with pytest.raises(PipelexError) as exc_info:
            await PipelexMTHDSProtocol().execute(mthds_contents=[bundle], inputs={"topic": SecurityRefusalTestData.TOPIC})

        caller = exc_info.value.to_problem(view=ProblemView.CALLER)

        assert caller.code == CoreCode.SECURITY_TEMPLATE_REFUSED
        assert caller.location is not None
        assert caller.location.as_wire() == {"pipe": "route_topic", "path": ["route_topic"], "field": expected_field}
