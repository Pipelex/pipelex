import asyncio
import base64
import json
from typing import Any

import pytest
from mthds.protocol.problem.registry import CoreCode
from pydantic import PrivateAttr
from pytest_mock import MockerFixture
from typing_extensions import override

from pipelex.core.stuffs.exceptions import StoredValueUnreadableError
from pipelex.core.stuffs.html_content import HtmlContent
from pipelex.core.stuffs.json_content import JSONContent
from pipelex.core.stuffs.markdown_content import MarkdownContent
from pipelex.core.stuffs.stored_value_loader import load_stored_value, load_stored_values
from pipelex.core.stuffs.stored_value_walker import find_unloaded_stored_values
from pipelex.core.stuffs.text_content import TextContent
from pipelex.tools.storage.in_memory_storage_provider import InMemoryStorageProvider
from pipelex.tools.storage.storage_provider_abstract import StoredData
from pipelex.tools.uri.exceptions import UriReadRefusalReason, UriReadRefusedError, UriTextNotUtf8Error, UriTextTooLargeError
from pipelex.tools.uri.uri_bytes import MAX_CONCURRENT_URI_READS
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


class ConcurrencyCountingStorage(InMemoryStorageProvider):
    """An in-memory storage whose every read takes a moment, counting the most reads in flight at once."""

    _nb_in_flight: int = PrivateAttr(default=0)
    _max_in_flight: int = PrivateAttr(default=0)

    @property
    def max_in_flight(self) -> int:
        return self._max_in_flight

    @override
    async def load_with_metadata(self, uri: str) -> StoredData:
        self._nb_in_flight += 1
        self._max_in_flight = max(self._max_in_flight, self._nb_in_flight)
        try:
            await asyncio.sleep(0.01)
            return await super().load_with_metadata(uri)
        finally:
            self._nb_in_flight -= 1


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

    @pytest.mark.parametrize(
        "stored_json",
        [
            '{"ratio": NaN}',
            '{"ratio": Infinity}',
            '{"ratio": -Infinity}',
            '{"nested": {"values": [1, NaN]}}',
            # A literal too large for a float decodes to an infinity, which the same check as an inline value's refuses.
            '{"ratio": 1e999}',
        ],
    )
    async def test_a_stored_json_holding_a_non_standard_constant_is_refused_as_inline_json_is(self, stored_json: str):
        """JSON has no NaN nor infinities: an inline `json_obj` holding one is refused, and so is a stored one."""
        storage = InMemoryStorageProvider()
        storage.root[JSON_KEY] = stored_json.encode("utf-8")
        content = JSONContent.model_validate(StoredValueTestData.JSON_REFERENCE)

        with pytest.raises(StoredValueUnreadableError) as exc_info:
            await load_stored_value(content, read_scope=READ_SCOPE, position="a value", storage_provider=storage)

        assert "not valid JSON" in str(exc_info.value)
        assert not content.is_loaded

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

    async def test_a_stored_text_that_is_not_utf8_is_the_caller_s_unreadable_input(self):
        """Bytes that are not a text are a URL pointed at the wrong file: `input.file_unreadable`, naming the input."""
        storage = InMemoryStorageProvider()
        storage.root[TEXT_KEY] = b"\xff\xfe\xfa not utf-8"
        content = TextContent.model_validate(StoredValueTestData.TEXT_REFERENCE)

        with pytest.raises(UriTextNotUtf8Error) as exc_info:
            await load_stored_value(content, read_scope=READ_SCOPE, position="a value", storage_provider=storage, input_name="pages")

        assert exc_info.value.error_code == CoreCode.INPUT_FILE_UNREADABLE
        assert exc_info.value.problem_params() == {"input": "pages", "file_type": "text", "reason": "not_utf8"}

    async def test_a_stored_json_that_is_not_an_object_is_the_caller_s_unreadable_input(self):
        storage = InMemoryStorageProvider()
        storage.root[JSON_KEY] = b"[1, 2, 3]"
        content = JSONContent.model_validate(StoredValueTestData.JSON_REFERENCE)

        with pytest.raises(StoredValueUnreadableError) as exc_info:
            await load_stored_value(content, read_scope=READ_SCOPE, position="a value", storage_provider=storage, input_name="report")

        assert exc_info.value.error_code == CoreCode.INPUT_FILE_UNREADABLE
        assert exc_info.value.problem_params() == {"input": "report", "file_type": "json", "reason": "not_a_json_object"}

    async def test_a_stored_text_past_the_fetch_cap_is_refused_before_it_is_read(self, mocker: MockerFixture):
        """A stored object is sized first, and one past `[runtime.network] max_fetch_bytes` is `input.too_large`, unread."""
        mocker.patch("pipelex.tools.uri.uri_text.fetch_max_bytes", return_value=16)
        storage = _storage_holding_every_value()
        load_spy = mocker.spy(InMemoryStorageProvider, "load_with_metadata")
        content = TextContent.model_validate(StoredValueTestData.TEXT_REFERENCE)

        with pytest.raises(UriTextTooLargeError) as exc_info:
            await load_stored_value(content, read_scope=READ_SCOPE, position="a value", storage_provider=storage, input_name="pages")

        assert exc_info.value.error_code == CoreCode.INPUT_TOO_LARGE
        assert exc_info.value.problem_params() == {"input": "pages", "limit": 16, "size": len(STORED_TEXT.encode("utf-8"))}
        load_spy.assert_not_called()
        assert not content.is_loaded

    async def test_a_data_url_past_the_fetch_cap_is_refused(self, mocker: MockerFixture):
        mocker.patch("pipelex.tools.uri.uri_text.fetch_max_bytes", return_value=16)
        data_url = "data:text/plain;base64," + base64.b64encode(STORED_TEXT.encode("utf-8")).decode("ascii")
        content = TextContent(url=data_url)

        with pytest.raises(UriTextTooLargeError) as exc_info:
            await load_stored_value(content, read_scope=None, position="a value", input_name="pages")

        assert exc_info.value.problem_params()["limit"] == 16

    async def test_a_tree_of_stored_values_loads_a_bounded_number_at_a_time(self):
        storage = ConcurrencyCountingStorage()
        nb_values = 3 * MAX_CONCURRENT_URI_READS
        roots: dict[str, Any] = {}
        for index_value in range(nb_values):
            key = f"{READ_SCOPE}/mt_1/run_9/generated/{index_value:016x}/value.txt"
            storage.root[key] = f"value {index_value}".encode()
            roots[f"text_{index_value}"] = TextContent(url=f"pipelex-storage://{key}")

        await load_stored_values(stored_values=find_unloaded_stored_values(roots=roots), read_scope=READ_SCOPE, storage_provider=storage)

        assert [roots[f"text_{index_value}"].require_text() for index_value in range(nb_values)] == [
            f"value {index_value}" for index_value in range(nb_values)
        ]
        assert 1 < storage.max_in_flight <= MAX_CONCURRENT_URI_READS
