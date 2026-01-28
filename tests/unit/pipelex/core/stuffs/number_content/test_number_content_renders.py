import pytest

from pipelex.core.stuffs.number_content import NumberContent
from tests.unit.pipelex.core.stuffs.number_content.test_data import TestData


class TestNumberContentRenders:
    """Tests for NumberContent render methods."""

    def test_rendered_plain_int(self):
        """Verify rendered_plain returns string representation of integer."""
        content = NumberContent(number=TestData.SAMPLE_INT)
        assert content.rendered_plain() == TestData.EXPECTED_RENDERED_PLAIN_INT

    def test_rendered_plain_float(self):
        """Verify rendered_plain returns string representation of float."""
        content = NumberContent(number=TestData.SAMPLE_FLOAT)
        assert content.rendered_plain() == TestData.EXPECTED_RENDERED_PLAIN_FLOAT

    def test_rendered_markdown_int(self):
        """Verify rendered_markdown returns string representation of integer."""
        content = NumberContent(number=TestData.SAMPLE_INT)
        assert content.rendered_markdown() == TestData.EXPECTED_RENDERED_MARKDOWN_INT

    def test_rendered_markdown_float(self):
        """Verify rendered_markdown returns string representation of float."""
        content = NumberContent(number=TestData.SAMPLE_FLOAT)
        assert content.rendered_markdown() == TestData.EXPECTED_RENDERED_MARKDOWN_FLOAT

    def test_rendered_html_int(self):
        """Verify rendered_html returns string representation of integer."""
        content = NumberContent(number=TestData.SAMPLE_INT)
        assert content.rendered_html() == TestData.EXPECTED_RENDERED_HTML_INT

    def test_rendered_html_float(self):
        """Verify rendered_html returns string representation of float."""
        content = NumberContent(number=TestData.SAMPLE_FLOAT)
        assert content.rendered_html() == TestData.EXPECTED_RENDERED_HTML_FLOAT

    def test_rendered_json_int(self):
        """Verify rendered_json returns JSON string with number key for integer."""
        content = NumberContent(number=TestData.SAMPLE_INT)
        assert content.rendered_json() == TestData.EXPECTED_RENDERED_JSON_INT

    def test_rendered_json_float(self):
        """Verify rendered_json returns JSON string with number key for float."""
        content = NumberContent(number=TestData.SAMPLE_FLOAT)
        assert content.rendered_json() == TestData.EXPECTED_RENDERED_JSON_FLOAT

    def test_rendered_for_prompt_int(self):
        """Verify rendered_for_prompt returns string representation for integer."""
        content = NumberContent(number=TestData.SAMPLE_INT)
        assert content.rendered_for_prompt() == TestData.EXPECTED_RENDERED_FOR_PROMPT_INT

    def test_rendered_for_prompt_float(self):
        """Verify rendered_for_prompt returns string representation for float."""
        content = NumberContent(number=TestData.SAMPLE_FLOAT)
        assert content.rendered_for_prompt() == TestData.EXPECTED_RENDERED_FOR_PROMPT_FLOAT

    @pytest.mark.asyncio
    async def test_rendered_plain_async_int(self):
        """Verify async rendered_plain returns the same as sync version for integer."""
        content = NumberContent(number=TestData.SAMPLE_INT)
        result = await content.rendered_plain_async()
        assert result == TestData.EXPECTED_RENDERED_PLAIN_INT

    @pytest.mark.asyncio
    async def test_rendered_markdown_async_int(self):
        """Verify async rendered_markdown returns the same as sync version for integer."""
        content = NumberContent(number=TestData.SAMPLE_INT)
        result = await content.rendered_markdown_async()
        assert result == TestData.EXPECTED_RENDERED_MARKDOWN_INT

    @pytest.mark.asyncio
    async def test_rendered_html_async_int(self):
        """Verify async rendered_html returns the same as sync version for integer."""
        content = NumberContent(number=TestData.SAMPLE_INT)
        result = await content.rendered_html_async()
        assert result == TestData.EXPECTED_RENDERED_HTML_INT

    @pytest.mark.asyncio
    async def test_rendered_json_async_int(self):
        """Verify async rendered_json returns the same as sync version for integer."""
        content = NumberContent(number=TestData.SAMPLE_INT)
        result = await content.rendered_json_async()
        assert result == TestData.EXPECTED_RENDERED_JSON_INT
