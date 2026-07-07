import pytest
from pydantic import ValidationError

from pipelex.core.stuffs.yes_no_content import YesNoContent
from tests.unit.pipelex.core.stuffs.yes_no_content.test_data import TestData


class TestYesNoContentRenders:
    """Tests for YesNoContent render methods and descriptors."""

    def test_construction_true(self):
        """Verify construction from yes_no=True keeps a genuine bool."""
        content = YesNoContent(yes_no=TestData.SAMPLE_TRUE)
        assert content.yes_no is True

    def test_construction_false(self):
        """Verify construction from yes_no=False keeps a genuine bool."""
        content = YesNoContent(yes_no=TestData.SAMPLE_FALSE)
        assert content.yes_no is False

    def test_rejects_non_bool_int(self):
        """An arbitrary int (not 0/1) must not coerce into the bool field."""
        with pytest.raises(ValidationError):
            YesNoContent(yes_no=2)  # pyright: ignore[reportArgumentType]

    def test_rendered_plain_true(self):
        content = YesNoContent(yes_no=TestData.SAMPLE_TRUE)
        assert content.rendered_plain() == TestData.EXPECTED_RENDERED_PLAIN_TRUE

    def test_rendered_plain_false(self):
        content = YesNoContent(yes_no=TestData.SAMPLE_FALSE)
        assert content.rendered_plain() == TestData.EXPECTED_RENDERED_PLAIN_FALSE

    def test_rendered_markdown_true(self):
        content = YesNoContent(yes_no=TestData.SAMPLE_TRUE)
        assert content.rendered_markdown() == TestData.EXPECTED_RENDERED_MARKDOWN_TRUE

    def test_rendered_markdown_false(self):
        content = YesNoContent(yes_no=TestData.SAMPLE_FALSE)
        assert content.rendered_markdown() == TestData.EXPECTED_RENDERED_MARKDOWN_FALSE

    def test_rendered_html_true(self):
        content = YesNoContent(yes_no=TestData.SAMPLE_TRUE)
        assert content.rendered_html() == TestData.EXPECTED_RENDERED_HTML_TRUE

    def test_rendered_html_false(self):
        content = YesNoContent(yes_no=TestData.SAMPLE_FALSE)
        assert content.rendered_html() == TestData.EXPECTED_RENDERED_HTML_FALSE

    def test_rendered_json_true(self):
        content = YesNoContent(yes_no=TestData.SAMPLE_TRUE)
        assert content.rendered_json() == TestData.EXPECTED_RENDERED_JSON_TRUE

    def test_rendered_json_false(self):
        content = YesNoContent(yes_no=TestData.SAMPLE_FALSE)
        assert content.rendered_json() == TestData.EXPECTED_RENDERED_JSON_FALSE

    def test_rendered_for_prompt_true(self):
        content = YesNoContent(yes_no=TestData.SAMPLE_TRUE)
        assert content.rendered_for_prompt() == TestData.EXPECTED_RENDERED_FOR_PROMPT_TRUE

    def test_rendered_for_prompt_false(self):
        content = YesNoContent(yes_no=TestData.SAMPLE_FALSE)
        assert content.rendered_for_prompt() == TestData.EXPECTED_RENDERED_FOR_PROMPT_FALSE

    def test_short_desc_true(self):
        content = YesNoContent(yes_no=TestData.SAMPLE_TRUE)
        assert content.short_desc == TestData.EXPECTED_SHORT_DESC_TRUE

    def test_short_desc_false(self):
        content = YesNoContent(yes_no=TestData.SAMPLE_FALSE)
        assert content.short_desc == TestData.EXPECTED_SHORT_DESC_FALSE

    def test_model_json_schema_carries_field_description(self):
        """The field description is the contract handed to the LLM in the generation schema."""
        schema = YesNoContent.model_json_schema()
        assert schema["properties"]["yes_no"]["description"] == TestData.EXPECTED_FIELD_DESCRIPTION

    @pytest.mark.asyncio
    async def test_rendered_plain_async_true(self):
        content = YesNoContent(yes_no=TestData.SAMPLE_TRUE)
        result = await content.rendered_plain_async()
        assert result == TestData.EXPECTED_RENDERED_PLAIN_TRUE

    @pytest.mark.asyncio
    async def test_rendered_json_async_false(self):
        content = YesNoContent(yes_no=TestData.SAMPLE_FALSE)
        result = await content.rendered_json_async()
        assert result == TestData.EXPECTED_RENDERED_JSON_FALSE
