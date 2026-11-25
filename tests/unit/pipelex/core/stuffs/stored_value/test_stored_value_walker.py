import json

import pytest

from pipelex.core.stuffs.html_content import HtmlContent
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.json_content import JSONContent
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.page_content import PageContent
from pipelex.core.stuffs.stored_value_loader import load_stored_value, load_stored_values
from pipelex.core.stuffs.stored_value_walker import find_unloaded_stored_values
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.text_and_images_content import TextAndImagesContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.tools.storage.in_memory_storage_provider import InMemoryStorageProvider
from pipelex.tools.uri.exceptions import UriReadRefusedError
from tests.unit.pipelex.core.stuffs.stored_value.cases import (
    FOREIGN_URL,
    HTML_KEY,
    JSON_KEY,
    READ_SCOPE,
    STORED_HTML,
    STORED_JSON_OBJ,
    STORED_TEXT,
    TEXT_KEY,
    StoredValueTestData,
)


class _Section(StructuredContent):
    body: TextContent
    notes: TextContent


class _Report(StructuredContent):
    section: _Section
    by_name: dict[str, TextContent]


def _storage() -> InMemoryStorageProvider:
    storage = InMemoryStorageProvider()
    storage.root[TEXT_KEY] = STORED_TEXT.encode("utf-8")
    storage.root[HTML_KEY] = STORED_HTML.encode("utf-8")
    storage.root[JSON_KEY] = json.dumps(STORED_JSON_OBJ).encode("utf-8")
    return storage


@pytest.mark.asyncio(loop_scope="class")
class TestStoredValueWalker:
    async def test_every_stored_value_is_found_wherever_it_sits_and_loaded(self) -> None:
        """A stuff's content, list items, a structure's fields and a TextAndImages' text are all walked."""
        page_text = TextContent.model_validate(StoredValueTestData.TEXT_REFERENCE)
        listed_html = HtmlContent.model_validate(StoredValueTestData.HTML_REFERENCE)
        direct_json = JSONContent.model_validate(StoredValueTestData.JSON_REFERENCE)
        inline_text = TextContent(text="short")
        pages = ListContent[PageContent](
            items=[
                PageContent(text_and_images=TextAndImagesContent(text=inline_text), page_view=ImageContent(url="https://example.com/1.png")),
                PageContent(text_and_images=TextAndImagesContent(text=page_text)),
            ]
        )
        roots = {"pages": pages, "pages_again": pages, "snippets": ListContent[HtmlContent](items=[listed_html]), "data": direct_json}

        found = find_unloaded_stored_values(roots=roots)

        # Reached twice through two roots, the page's text is listed once, under the first path that reached it.
        assert [(stored_value.path, stored_value.content) for stored_value in found] == [
            ("pages.items[1].text_and_images.text", page_text),
            ("snippets.items[0]", listed_html),
            ("data", direct_json),
        ]
        assert found[0].position == "the stored value 'pages.items[1].text_and_images.text'"

        await load_stored_values(stored_values=found, read_scope=READ_SCOPE, storage_provider=_storage())

        assert page_text.require_text() == STORED_TEXT
        assert listed_html.require_inner_html() == STORED_HTML
        assert direct_json.require_json_obj() == STORED_JSON_OBJ
        assert find_unloaded_stored_values(roots=roots) == []

    async def test_inline_and_loaded_values_are_not_listed(self) -> None:
        loaded_text = TextContent.model_validate(StoredValueTestData.TEXT_REFERENCE)
        await load_stored_value(loaded_text, read_scope=READ_SCOPE, position="a value", storage_provider=_storage())

        assert find_unloaded_stored_values(roots={"inline": TextContent(text="short"), "loaded": loaded_text}) == []

    async def test_a_value_outside_the_read_scope_is_refused_naming_its_path(self) -> None:
        foreign_text = TextContent(url=FOREIGN_URL)
        found = find_unloaded_stored_values(roots={"pages": ListContent[TextContent](items=[foreign_text])})

        with pytest.raises(UriReadRefusedError) as exc_info:
            await load_stored_values(stored_values=found, read_scope=READ_SCOPE, storage_provider=_storage())

        assert "the stored value 'pages.items[0]'" in str(exc_info.value)
        assert not foreign_text.is_loaded

    async def test_only_the_values_a_reader_reads_are_listed(self) -> None:
        """A read path lists the value at it, above it and below it, compared by segment, and nothing beside it."""
        body = TextContent.model_validate(StoredValueTestData.TEXT_REFERENCE)
        notes = TextContent(url=FOREIGN_URL)
        keyed = TextContent.model_validate(StoredValueTestData.TEXT_REFERENCE)
        report = _Report(section=_Section(body=body, notes=notes), by_name={"intro": keyed})

        def listed(*, read_paths: list[str]) -> list[str]:
            return [stored_value.path for stored_value in find_unloaded_stored_values(roots={"report": report}, read_paths=read_paths)]

        assert listed(read_paths=["report.section.body"]) == ["report.section.body"]
        # A path reading into a stored value's own field reads the value.
        assert listed(read_paths=["report.section.body.text"]) == ["report.section.body"]
        assert listed(read_paths=["report.section"]) == ["report.section.body", "report.section.notes"]
        assert listed(read_paths=["report"]) == ["report.section.body", "report.section.notes", "report.by_name['intro']"]
        # A mapping's key is read as a field is.
        assert listed(read_paths=["report.by_name.intro"]) == ["report.by_name['intro']"]
        # Segments, not characters: `report.sect` is not a prefix of `report.section`.
        assert listed(read_paths=["report.sect", "other"]) == []

    async def test_a_value_read_through_an_alias_is_listed_under_the_alias(self) -> None:
        """The first root reaching a value is skipped when no read path reads through it, so the alias still lists it."""
        stored_text = TextContent.model_validate(StoredValueTestData.TEXT_REFERENCE)

        found = find_unloaded_stored_values(roots={"main_stuff": stored_text, "note": stored_text}, read_paths=["note"])

        assert [stored_value.path for stored_value in found] == ["note"]
