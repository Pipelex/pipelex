import json
from typing import Any

import pytest
from pytest_mock import MockerFixture

from pipelex.core.stuffs.exceptions import StoredValueUnreadableError
from pipelex.core.stuffs.html_content import HtmlContent
from pipelex.core.stuffs.json_content import JSONContent
from pipelex.core.stuffs.markdown_content import MarkdownContent
from pipelex.core.stuffs.stored_value_loader import load_stored_value
from pipelex.core.stuffs.text_content import TextContent
from pipelex.tools.storage.in_memory_storage_provider import InMemoryStorageProvider
from pipelex.tools.uri.exceptions import UriReadRefusalReason, UriReadRefusedError, UriTextNotUtf8Error
from tests.unit.pipelex.core.stuffs.stored_value.test_data import (
    FOREIGN_URL,
    HTML_KEY,
    JSON_KEY,
    MARKDOWN_KEY,
    READ_SCOPE,
    STORED_HTML,
    STORED_JSON_OBJ,
    STORED_TEXT,
    TEXT_KEY,
    StoredValueTestData,
)


def _storage_holding_every_value() -> InMemoryStorageProvider:
    storage = InMemoryStorageProvider()
    storage.root[TEXT_KEY] = STORED_TEXT.encode("utf-8")
    storage.root[MARKDOWN_KEY] = STORED_TEXT.encode("utf-8")
    storage.root[HTML_KEY] = STORED_HTML.encode("utf-8")
    storage.root[JSON_KEY] = json.dumps(STORED_JSON_OBJ).encode("utf-8")
    return storage


@pytest.mark.asyncio(loop_scope="class")
class TestStoredValueLoading:
    async def test_a_stored_text_loads_its_value_and_keeps_the_reference(self):
        content = TextContent.model_validate(StoredValueTestData.TEXT_REFERENCE)

        await load_stored_value(content, read_scope=READ_SCOPE, position="the text input 'pages'", storage_provider=_storage_holding_every_value())

        assert content.require_text() == STORED_TEXT
        assert content.rendered_plain() == STORED_TEXT
        # The loaded value is never written back onto the model: the dump is the reference it was.
        assert content.smart_dump() == StoredValueTestData.TEXT_REFERENCE
        assert STORED_TEXT not in content.model_dump_json()
        assert '"text"' not in content.model_dump_json()

    @pytest.mark.parametrize(
        ("content", "expected_value"),
        [
            (MarkdownContent.model_validate(StoredValueTestData.MARKDOWN_REFERENCE), STORED_TEXT),
            (HtmlContent.model_validate(StoredValueTestData.HTML_REFERENCE), STORED_HTML),
        ],
    )
    async def test_markdown_and_html_load_their_text(self, content: MarkdownContent | HtmlContent, expected_value: str):
        await load_stored_value(content, read_scope=READ_SCOPE, position="a value", storage_provider=_storage_holding_every_value())
        assert content.rendered_plain() == expected_value

    async def test_a_stored_json_is_decoded_back_into_its_object_by_its_mime_type(self):
        content = JSONContent.model_validate(StoredValueTestData.JSON_REFERENCE)

        await load_stored_value(content, read_scope=READ_SCOPE, position="a value", storage_provider=_storage_holding_every_value())

        assert content.require_json_obj() == STORED_JSON_OBJ
        assert content.smart_dump() == StoredValueTestData.JSON_REFERENCE

    async def test_a_stored_json_that_is_not_an_object_is_refused(self):
        storage = InMemoryStorageProvider()
        storage.root[JSON_KEY] = b"[1, 2, 3]"
        content = JSONContent.model_validate(StoredValueTestData.JSON_REFERENCE)

        with pytest.raises(StoredValueUnreadableError):
            await load_stored_value(content, read_scope=READ_SCOPE, position="a value", storage_provider=storage)

    async def test_a_stored_text_that_is_not_utf8_is_refused(self):
        storage = InMemoryStorageProvider()
        storage.root[TEXT_KEY] = b"\xff\xfe\xfa not utf-8"
        content = TextContent.model_validate(StoredValueTestData.TEXT_REFERENCE)

        with pytest.raises(UriTextNotUtf8Error):
            await load_stored_value(content, read_scope=READ_SCOPE, position="a value", storage_provider=storage)

    async def test_a_key_outside_the_read_scope_is_refused_as_an_image_read_is(self, mocker: MockerFixture):
        storage = _storage_holding_every_value()
        load_spy = mocker.spy(InMemoryStorageProvider, "load_with_metadata")
        content = TextContent(url=FOREIGN_URL)

        with pytest.raises(UriReadRefusedError) as exc_info:
            await load_stored_value(content, read_scope=READ_SCOPE, position="the text input 'pages'", storage_provider=storage)

        assert exc_info.value.reason == UriReadRefusalReason.FOREIGN_STORAGE_KEY
        assert "the text input 'pages'" in str(exc_info.value)
        load_spy.assert_not_called()

    async def test_a_second_load_reads_nothing(self, mocker: MockerFixture):
        storage = _storage_holding_every_value()
        load_spy = mocker.spy(InMemoryStorageProvider, "load_with_metadata")
        content = TextContent.model_validate(StoredValueTestData.TEXT_REFERENCE)

        await load_stored_value(content, read_scope=READ_SCOPE, position="a value", storage_provider=storage)
        await load_stored_value(content, read_scope=READ_SCOPE, position="a value", storage_provider=storage)

        assert load_spy.call_count == 1
        assert content.require_text() == STORED_TEXT

    async def test_an_inline_value_loads_nothing(self, mocker: MockerFixture):
        storage = _storage_holding_every_value()
        load_spy = mocker.spy(InMemoryStorageProvider, "load_with_metadata")
        content = TextContent(text="short")

        await load_stored_value(content, read_scope=READ_SCOPE, position="a value", storage_provider=storage)

        load_spy.assert_not_called()
        assert content.require_text() == "short"

    @pytest.mark.parametrize(
        "reference",
        [StoredValueTestData.TEXT_REFERENCE],
    )
    async def test_a_copy_keeps_no_loaded_value_in_its_dump(self, reference: dict[str, Any]):
        content = TextContent.model_validate(reference)
        await load_stored_value(content, read_scope=READ_SCOPE, position="a value", storage_provider=_storage_holding_every_value())

        round_tripped = TextContent.model_validate(content.smart_dump())

        assert round_tripped.smart_dump() == reference
        assert not round_tripped.is_loaded
