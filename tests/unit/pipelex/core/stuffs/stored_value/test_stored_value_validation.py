from typing import Any

import pytest
from pydantic import ValidationError

from pipelex.core.stuffs.html_content import HtmlContent
from pipelex.core.stuffs.json_content import JSONContent
from pipelex.core.stuffs.markdown_content import MarkdownContent
from pipelex.core.stuffs.stored_value_content import StoredValueContent
from pipelex.core.stuffs.text_content import TextContent
from tests.unit.pipelex.core.stuffs.stored_value.test_data import (
    HTML_URL,
    JSON_URL,
    STORED_HTML,
    STORED_JSON_OBJ,
    STORED_TEXT,
    TEXT_URL,
    StoredValueTestData,
)


class TestStoredValueValidation:
    @pytest.mark.parametrize(
        ("content_class", "fields"),
        [
            (TextContent, {"text": STORED_TEXT}),
            (MarkdownContent, {"text": STORED_TEXT}),
            (HtmlContent, {"inner_html": STORED_HTML}),
            (HtmlContent, {"inner_html": STORED_HTML, "css_class": "page"}),
            (JSONContent, {"json_obj": STORED_JSON_OBJ}),
            (TextContent, StoredValueTestData.TEXT_REFERENCE),
            (MarkdownContent, StoredValueTestData.MARKDOWN_REFERENCE),
            (HtmlContent, StoredValueTestData.HTML_REFERENCE),
            (HtmlContent, {**StoredValueTestData.HTML_REFERENCE, "css_class": "page"}),
            (JSONContent, StoredValueTestData.JSON_REFERENCE),
            # A caller may send a text input as a bare URL: the metadata is the storing code's, never required.
            (TextContent, {"url": TEXT_URL}),
            (HtmlContent, {"url": HTML_URL}),
            (JSONContent, {"url": JSON_URL}),
        ],
    )
    def test_a_value_or_a_url_is_accepted(self, content_class: type[StoredValueContent], fields: dict[str, Any]):
        content = content_class.model_validate(fields)
        assert content.is_stored == ("url" in fields)

    @pytest.mark.parametrize(
        ("content_class", "fields", "expected_fragment"),
        [
            (TextContent, {"text": STORED_TEXT, "url": TEXT_URL}, "both"),
            (MarkdownContent, {"text": STORED_TEXT, **StoredValueTestData.MARKDOWN_REFERENCE}, "both"),
            (HtmlContent, {"inner_html": STORED_HTML, "url": HTML_URL}, "both"),
            (JSONContent, {"json_obj": STORED_JSON_OBJ, "url": JSON_URL}, "both"),
            (TextContent, {}, "neither"),
            (MarkdownContent, {}, "neither"),
            (HtmlContent, {"css_class": "page"}, "neither"),
            (JSONContent, {}, "neither"),
            (TextContent, {"text": STORED_TEXT, "size": 12}, "size"),
            (TextContent, {"text": STORED_TEXT, "mime_type": "text/plain"}, "mime_type"),
            (TextContent, {"text": STORED_TEXT, "preview": "The first"}, "preview"),
            (HtmlContent, {"inner_html": STORED_HTML, "preview": "<h1>"}, "preview"),
            (JSONContent, {"json_obj": STORED_JSON_OBJ, "size": 77}, "size"),
        ],
    )
    def test_both_neither_or_reference_metadata_without_url_is_refused(
        self,
        content_class: type[StoredValueContent],
        fields: dict[str, Any],
        expected_fragment: str,
    ):
        with pytest.raises(ValidationError) as exc_info:
            content_class.model_validate(fields)
        assert expected_fragment in str(exc_info.value)

    def test_a_negative_size_is_refused(self):
        with pytest.raises(ValidationError):
            TextContent(url=TEXT_URL, size=-1)
