import pytest

from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.pipe_run.result_line import collapse_line, render_result_line, wire_output_content


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
