from collections.abc import Callable

import pytest
from rich.text import Text

from pipelex.core.stuffs.exceptions import StoredValueNotLoadedError
from pipelex.core.stuffs.html_content import HtmlContent
from pipelex.core.stuffs.json_content import JSONContent
from pipelex.core.stuffs.markdown_content import MarkdownContent
from pipelex.core.stuffs.stored_value_content import StoredValueContent
from pipelex.core.stuffs.text_content import TextContent
from tests.unit.pipelex.core.stuffs.stored_value.cases import (
    HTML_URL,
    STORED_HTML,
    STORED_JSON_OBJ,
    STORED_TEXT,
    TEXT_URL,
    StoredValueTestData,
)

# A pretty print is a display, which describes a reference never loaded rather than refusing it.
_RENDERERS = ["rendered_plain", "rendered_markdown", "rendered_html", "rendered_json"]

_REFERENCED_CONTENTS = [
    pytest.param(lambda: TextContent.model_validate(StoredValueTestData.TEXT_REFERENCE), id="Text"),
    pytest.param(lambda: MarkdownContent.model_validate(StoredValueTestData.MARKDOWN_REFERENCE), id="Markdown"),
    pytest.param(lambda: HtmlContent.model_validate(StoredValueTestData.HTML_REFERENCE), id="Html"),
    pytest.param(lambda: JSONContent.model_validate(StoredValueTestData.JSON_REFERENCE), id="JSON"),
]


class TestStoredValueRendering:
    @pytest.mark.parametrize("make_content", _REFERENCED_CONTENTS)
    @pytest.mark.parametrize("renderer_name", _RENDERERS)
    def test_rendering_a_reference_never_loaded_raises_naming_the_content_and_the_loader(
        self,
        make_content: Callable[[], StoredValueContent],
        renderer_name: str,
    ):
        content = make_content()
        with pytest.raises(StoredValueNotLoadedError) as exc_info:
            getattr(content, renderer_name)()
        message = str(exc_info.value)
        assert content.__class__.__name__ in message
        assert "load_stored_value" in message

    @pytest.mark.parametrize("make_content", _REFERENCED_CONTENTS)
    def test_a_pretty_print_of_a_reference_never_loaded_describes_it(self, make_content: Callable[[], StoredValueContent]):
        """The CLI prints a hosted run's output where its storage is not reachable: it shows the reference, never fails."""
        content = make_content()
        pretty = content.rendered_pretty()
        assert isinstance(pretty, Text)
        assert f"{content.size} bytes" in pretty.plain
        assert "not loaded" in pretty.plain
        assert content.preview is not None
        assert pretty.plain.endswith(content.preview)

    @pytest.mark.parametrize(
        ("make_content", "loaded_value", "expected_plain"),
        [
            (lambda: TextContent.model_validate(StoredValueTestData.TEXT_REFERENCE), STORED_TEXT, STORED_TEXT),
            (lambda: MarkdownContent.model_validate(StoredValueTestData.MARKDOWN_REFERENCE), STORED_TEXT, STORED_TEXT),
            (lambda: HtmlContent.model_validate(StoredValueTestData.HTML_REFERENCE), STORED_HTML, STORED_HTML),
        ],
    )
    def test_a_loaded_reference_renders_its_value_as_the_inline_form_does(
        self,
        make_content: Callable[[], StoredValueContent],
        loaded_value: str,
        expected_plain: str,
    ):
        content = make_content()
        content.accept_loaded_text(text=loaded_value)
        assert content.rendered_plain() == expected_plain
        inline = content.__class__.model_validate({content.value_field_name: loaded_value})
        assert content.rendered_markdown() == inline.rendered_markdown()
        assert content.rendered_html() == inline.rendered_html()
        assert content.rendered_json() == inline.rendered_json()

    def test_a_loaded_json_reference_renders_its_object(self):
        content = JSONContent.model_validate(StoredValueTestData.JSON_REFERENCE)
        content.accept_loaded_text(text='{"title": "A large JSON document", "items": [1, 2, 3], "nested": {"accent": "é"}}')
        inline = JSONContent(json_obj=STORED_JSON_OBJ)
        assert content.require_json_obj() == STORED_JSON_OBJ
        assert content.rendered_plain() == inline.rendered_plain()
        assert content.rendered_markdown() == inline.rendered_markdown()
        assert content.rendered_html() == inline.rendered_html()
        assert content.rendered_json() == inline.rendered_json()

    @pytest.mark.parametrize(
        ("content", "expected_desc"),
        [
            (
                TextContent.model_validate(StoredValueTestData.TEXT_REFERENCE),
                f"some stored text ({StoredValueTestData.TEXT_REFERENCE['size']} bytes)",
            ),
            (
                MarkdownContent.model_validate(StoredValueTestData.MARKDOWN_REFERENCE),
                f"some stored markdown ({StoredValueTestData.MARKDOWN_REFERENCE['size']} bytes)",
            ),
            (
                HtmlContent.model_validate(StoredValueTestData.HTML_REFERENCE),
                f"some stored html ({StoredValueTestData.HTML_REFERENCE['size']} bytes)",
            ),
            (JSONContent.model_validate(StoredValueTestData.JSON_REFERENCE), "some stored JSON (77 bytes)"),
            (TextContent(url=TEXT_URL), "some stored text (size unknown)"),
            (HtmlContent(url=HTML_URL), "some stored html (size unknown)"),
            (TextContent(text="four"), "some text (4 chars)"),
        ],
    )
    def test_short_desc_reports_the_stored_size(self, content: StoredValueContent, expected_desc: str):
        assert content.short_desc == expected_desc
