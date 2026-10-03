import json

import pytest
from markupsafe import escape
from rich.markdown import Markdown

from pipelex.core.stuffs.markdown_content import MarkdownContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.tools.templating.text_format import TextFormat
from tests.unit.pipelex.core.stuffs.markdown_content.test_data import TestData


class TestMarkdownContentRenders:
    def test_is_a_text_content_holding_the_source(self):
        """A Markdown value is a text: TextContent's one field, holding the Markdown source."""
        content = MarkdownContent(text=TestData.SAMPLE_REPORT)
        assert isinstance(content, TextContent)
        assert content.text == TestData.SAMPLE_REPORT
        assert content.smart_dump() == TestData.EXPECTED_SMART_DUMP
        assert content.short_desc == TestData.EXPECTED_SHORT_DESC
        assert MarkdownContent.model_fields["text"].description == TestData.EXPECTED_FIELD_DESCRIPTION

    def test_source_renderings_are_the_markdown_as_it_is(self):
        """Plain, Markdown (the saved `main_stuff.md`) and prompt renderings are the source, verbatim."""
        content = MarkdownContent(text=TestData.SAMPLE_REPORT)
        assert content.rendered_plain() == TestData.SAMPLE_REPORT
        assert content.rendered_markdown() == TestData.SAMPLE_REPORT
        assert content.rendered_for_prompt() == TestData.SAMPLE_REPORT
        assert content.rendered_for_prompt(text_format=TextFormat.MARKDOWN) == TestData.SAMPLE_REPORT
        assert str(content) == TestData.SAMPLE_REPORT
        assert json.loads(content.rendered_json()) == {"text": TestData.SAMPLE_REPORT}

    @pytest.mark.asyncio
    async def test_saved_markdown_is_the_source(self):
        """`pipelex run --save-main-stuff` writes `main_stuff.md` from the async Markdown rendering."""
        content = MarkdownContent(text=TestData.SAMPLE_REPORT)
        assert await content.rendered_markdown_async() == TestData.SAMPLE_REPORT

    def test_html_rendering_converts(self):
        """The HTML view converts the Markdown rather than escaping it, and markupsafe inserts that conversion."""
        content = MarkdownContent(text=TestData.SAMPLE_REPORT)
        assert content.rendered_html() == TestData.EXPECTED_REPORT_HTML
        assert content.rendered_for_prompt(text_format=TextFormat.HTML) == TestData.EXPECTED_REPORT_HTML
        # markupsafe reads `__html__`: escaping the content yields the conversion, not the escaped source.
        assert str(escape(content)) == TestData.EXPECTED_REPORT_HTML
        # A Text holding the same source keeps being escaped.
        assert TextContent(text="<b>x</b>").rendered_html() == "&lt;b&gt;x&lt;/b&gt;"

    @pytest.mark.parametrize(("source", "expected_html"), TestData.HTML_CONVERSION_CASES)
    def test_html_conversion_links_schemes_and_escapes_raw_html(self, source: str, expected_html: str):
        """URLs with a scheme are linked, file names stay text, raw HTML and javascript: targets are neutralized."""
        assert MarkdownContent(text=source).rendered_html() == expected_html

    def test_pretty_rendering_is_always_markdown(self):
        """The pretty view renders the source as Markdown, even when it starts like HTML."""
        pretty = MarkdownContent(text=TestData.SAMPLE_HTML_LOOKING_MARKDOWN).rendered_pretty()
        assert isinstance(pretty, Markdown)
        assert pretty.markup == TestData.SAMPLE_HTML_LOOKING_MARKDOWN
