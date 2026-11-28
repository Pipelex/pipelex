import pytest
from pytest_mock import MockerFixture

from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.pipe_run import result_line
from pipelex.pipe_run.result_line import collapse_line, render_result_line, result_line_of_run, wire_output_content


class FieldsNamedLikeDictMethods(StructuredContent):
    items: list[str]
    values: str
    update: str
    get: str
    verdict: str


@pytest.mark.asyncio(loop_scope="class")
class TestResultLine:
    @pytest.mark.parametrize(
        ("rendered", "expected"),
        [("  3 approved\n\n 1 rejected  ", "3 approved 1 rejected"), ("\t\n", ""), ("one", "one")],
    )
    def test_collapses_white_space_into_one_line(self, rendered: str, expected: str) -> None:
        assert collapse_line(rendered=rendered) == expected

    def test_a_plural_output_reads_as_an_array(self) -> None:
        """`output` is the wire content: an array of the items for a plural output, an object for a single one."""
        plural = ListContent[TextContent](items=[TextContent(text="a"), TextContent(text="b")])
        assert wire_output_content(content=plural) == [{"text": "a"}, {"text": "b"}]
        assert wire_output_content(content=TextContent(text="a")) == {"text": "a"}

    @pytest.mark.parametrize(
        ("template", "expected"),
        [
            ("{{ output | length }} items", "2 items"),
            ("{% for item in output %} {{ item.text }}\n{% endfor %}", "a b"),
            ("{{ output.missing.deeper }}", None),
            ("{{ '' }}", None),
        ],
    )
    async def test_renders_against_the_output_or_gives_none(self, template: str, expected: str | None) -> None:
        """A line that fails to render or renders nothing is None, so the derived line takes its place."""
        plural = ListContent[TextContent](items=[TextContent(text="a"), TextContent(text="b")])
        assert await render_result_line(result_line=template, content=plural, pipe_code="review") == expected

    @pytest.mark.parametrize(
        ("template", "expected"),
        [
            ("{{ output.items | length }} {{ output.values }} {{ output.update }} {{ output.get }}", "2 V U G"),
            ("{{ output.items | join('+') }}", "a+b"),
            ("{{ output['values'] }} {{ 'update' in output }} {{ output | length }}", "V True 5"),
        ],
        ids=["dotted_fields", "dotted_list_field", "brackets_membership_length"],
    )
    async def test_a_field_named_like_a_dict_method_reads_as_the_field(self, template: str, expected: str) -> None:
        """`output.items` reads the field `items`, never the dict method, as the line reads in every engine."""
        content = FieldsNamedLikeDictMethods(items=["a", "b"], values="V", update="U", get="G", verdict="ok")
        assert await render_result_line(result_line=template, content=content, pipe_code="review") == expected

    async def test_dict_methods_stay_callable_without_a_field_of_their_name(self) -> None:
        """A record without a field named `items` still iterates its fields with `items()`, as a dict does."""
        rendered = await render_result_line(
            result_line="{% for key, value in output.items() %}{{ key }}={{ value }} {% endfor %}{{ output.get('text') }}",
            content=TextContent(text="a"),
            pipe_code="review",
        )
        assert rendered == "text=a a"

    @pytest.mark.parametrize(
        "template",
        [
            "{{ output.text | wordwrap(0) }}",
            "{{ '{:d}'.format('a') }}",
            "{{ output.__class__ }}",
            "{{ output._fields }}",
            "{{ 1 / 0 }}",
            "{% for %}",
        ],
        ids=["filter_value_error", "format_value_error", "dunder_refused", "private_refused", "arithmetic", "syntax"],
    )
    async def test_a_failing_line_never_raises(self, template: str) -> None:
        """Whatever the template raises, a refusal of the sandbox included, the authored line is None and the run goes on."""
        assert await render_result_line(result_line=template, content=TextContent(text="a"), pipe_code="review") is None

    async def test_an_output_with_no_json_form_gives_no_authored_line(self, mocker: MockerFixture) -> None:
        """An output that cannot be put on the wire gives no authored line rather than failing the run."""
        mocker.patch.object(result_line, "clean_json_dumps", side_effect=TypeError("not serializable"))
        assert await render_result_line(result_line="{{ output.text }}", content=TextContent(text="a"), pipe_code="review") is None

    async def test_a_run_with_no_main_output_has_no_line(self) -> None:
        """A working memory holding no main output gives no line, rather than failing the run that already ended."""
        pipe_output = PipeOutput(working_memory=WorkingMemory(root={}))
        assert await result_line_of_run(result_line="{{ output }}", pipe_output=pipe_output, pipe_code="review") is None
