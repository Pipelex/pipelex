from typing import Any

import pytest

from pipelex.core.stuffs.html_content import HtmlContent
from pipelex.core.stuffs.json_content import JSONContent
from pipelex.core.stuffs.markdown_content import MarkdownContent
from pipelex.core.stuffs.stored_value_content import StoredValueContent
from pipelex.core.stuffs.text_content import TextContent
from tests.unit.pipelex.core.stuffs.stored_value.test_data import STORED_TEXT, StoredValueTestData


class TestStoredValueAssignment:
    def test_assigning_the_text_of_a_loaded_reference_makes_it_inline(self):
        """The PipeFunc pattern `note.text = note.require_text().upper()` leaves a content in one valid form."""
        note = TextContent.model_validate(StoredValueTestData.TEXT_REFERENCE)
        note.accept_loaded_text(text=STORED_TEXT)

        note.text = note.require_text().upper()

        assert note.smart_dump() == {"text": STORED_TEXT.upper()}
        assert not note.is_stored
        assert note.url is None
        assert note.size is None
        assert note.mime_type is None
        assert note.preview is None
        assert note.require_text() == STORED_TEXT.upper()
        assert TextContent.model_validate(note.smart_dump()).require_text() == STORED_TEXT.upper()

    @pytest.mark.parametrize(
        ("content_class", "reference", "value_field_name", "new_value"),
        [
            (TextContent, StoredValueTestData.TEXT_REFERENCE, "text", "rewritten"),
            (MarkdownContent, StoredValueTestData.MARKDOWN_REFERENCE, "text", "# Rewritten"),
            (HtmlContent, StoredValueTestData.HTML_REFERENCE, "inner_html", "<p>Rewritten</p>"),
            (JSONContent, StoredValueTestData.JSON_REFERENCE, "json_obj", {"rewritten": True}),
        ],
    )
    def test_assigning_the_value_of_a_reference_never_loaded_makes_it_inline(
        self,
        content_class: type[StoredValueContent],
        reference: dict[str, Any],
        value_field_name: str,
        new_value: str | dict[str, Any],
    ):
        content = content_class.model_validate(reference)

        setattr(content, value_field_name, new_value)

        assert content.require_value() == new_value
        dumped = content.smart_dump()
        assert dumped[value_field_name] == new_value
        assert "url" not in dumped
        assert content_class.model_validate(dumped).require_value() == new_value

    def test_assigning_the_text_of_an_inline_content_keeps_it_inline(self):
        note = TextContent(text="short")

        note.text = "longer"

        assert note.smart_dump() == {"text": "longer"}

    def test_assigning_a_value_drops_the_value_loaded_before(self):
        note = TextContent.model_validate(StoredValueTestData.TEXT_REFERENCE)
        note.accept_loaded_text(text=STORED_TEXT)
        note.text = "replaced"

        # A later load has nothing to keep: the content now holds its value inline.
        note.accept_loaded_text(text=STORED_TEXT)

        assert note.require_text() == "replaced"
