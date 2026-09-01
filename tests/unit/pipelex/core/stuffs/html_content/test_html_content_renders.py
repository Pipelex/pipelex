import json

import pytest

from pipelex.core.stuffs.html_content import HtmlContent
from tests.unit.pipelex.core.stuffs.html_content.test_data import TestData


class TestHtmlContentRenders:
    """Tests for HtmlContent render methods."""

    def test_rendered_plain(self):
        """Verify rendered_plain returns the inner_html."""
        content = HtmlContent(inner_html=TestData.SAMPLE_INNER_HTML, css_class=TestData.SAMPLE_CSS_CLASS)
        assert content.rendered_plain() == TestData.EXPECTED_RENDERED_PLAIN

    def test_rendered_markdown(self):
        """Verify rendered_markdown returns the inner_html."""
        content = HtmlContent(inner_html=TestData.SAMPLE_INNER_HTML, css_class=TestData.SAMPLE_CSS_CLASS)
        assert content.rendered_markdown() == TestData.EXPECTED_RENDERED_MARKDOWN

    def test_rendered_html(self):
        """Verify rendered_html wraps content in div with escaped css_class."""
        content = HtmlContent(inner_html=TestData.SAMPLE_INNER_HTML, css_class=TestData.SAMPLE_CSS_CLASS)
        assert content.rendered_html() == TestData.EXPECTED_RENDERED_HTML

    def test_rendered_html_escapes_css_class(self):
        """Verify rendered_html properly escapes potentially dangerous css_class values."""
        content = HtmlContent(inner_html=TestData.SAMPLE_INNER_HTML, css_class=TestData.XSS_CSS_CLASS)
        assert content.rendered_html() == TestData.EXPECTED_XSS_PROTECTED_HTML

    def test_rendered_html_without_css_class(self):
        """An unset css_class renders the raw inner_html with no wrapping div."""
        content = HtmlContent(inner_html=TestData.SAMPLE_INNER_HTML)
        assert content.rendered_html() == TestData.EXPECTED_RENDERED_HTML_NO_CLASS

    def test_rendered_json_states_the_models_own_members(self):
        """The JSON rendering is the model's, member for member — `inner_html`, never a rename.

        It used to emit `html`, which made a payload that did not satisfy the schema its own output
        contract publishes: `native.Html` pins `inner_html` and pins it required, so a consumer
        reading the contract found the required member absent and one the standard does not define
        beside it. Caught by a real run once the output contract started carrying a schema.
        """
        content = HtmlContent(inner_html=TestData.SAMPLE_INNER_HTML, css_class=TestData.SAMPLE_CSS_CLASS)
        assert json.loads(content.rendered_json()) == TestData.EXPECTED_RENDERED_JSON

    def test_rendered_json_without_css_class(self):
        """An unset optional member is stated as null, exactly as the model dumps it."""
        content = HtmlContent(inner_html=TestData.SAMPLE_INNER_HTML)
        assert json.loads(content.rendered_json()) == TestData.EXPECTED_RENDERED_JSON_NO_CLASS

    def test_rendered_for_prompt(self):
        """Verify rendered_for_prompt returns markdown format (which is inner_html for HtmlContent)."""
        content = HtmlContent(inner_html=TestData.SAMPLE_INNER_HTML, css_class=TestData.SAMPLE_CSS_CLASS)
        assert content.rendered_for_prompt() == TestData.EXPECTED_RENDERED_FOR_PROMPT

    @pytest.mark.asyncio
    async def test_rendered_plain_async(self):
        """Verify async rendered_plain returns the same as sync version."""
        content = HtmlContent(inner_html=TestData.SAMPLE_INNER_HTML, css_class=TestData.SAMPLE_CSS_CLASS)
        result = await content.rendered_plain_async()
        assert result == TestData.EXPECTED_RENDERED_PLAIN

    @pytest.mark.asyncio
    async def test_rendered_markdown_async(self):
        """Verify async rendered_markdown returns the same as sync version."""
        content = HtmlContent(inner_html=TestData.SAMPLE_INNER_HTML, css_class=TestData.SAMPLE_CSS_CLASS)
        result = await content.rendered_markdown_async()
        assert result == TestData.EXPECTED_RENDERED_MARKDOWN

    @pytest.mark.asyncio
    async def test_rendered_html_async(self):
        """Verify async rendered_html returns the same as sync version."""
        content = HtmlContent(inner_html=TestData.SAMPLE_INNER_HTML, css_class=TestData.SAMPLE_CSS_CLASS)
        result = await content.rendered_html_async()
        assert result == TestData.EXPECTED_RENDERED_HTML

    @pytest.mark.asyncio
    async def test_rendered_json_async(self):
        """Verify async rendered_json returns the same as sync version."""
        content = HtmlContent(inner_html=TestData.SAMPLE_INNER_HTML, css_class=TestData.SAMPLE_CSS_CLASS)
        result = await content.rendered_json_async()
        assert json.loads(result) == TestData.EXPECTED_RENDERED_JSON
