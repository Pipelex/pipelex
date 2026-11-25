import hashlib
import json

import pytest
from pytest_mock import MockerFixture

from pipelex.core.stuffs.html_content import HtmlContent
from pipelex.core.stuffs.json_content import JSONContent
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.markdown_content import MarkdownContent
from pipelex.core.stuffs.stored_value_content import StoredValueContent
from pipelex.core.stuffs.stored_value_storer import STORED_VALUE_PREVIEW_MAX_CHARS, store_large_values, store_value_if_large
from pipelex.core.stuffs.text_content import TextContent
from pipelex.system.storage_scope import DRY_RUN_STORAGE_SCOPE, GENERATED_CONTENT_LEAF, INPUT_ASSETS_LEAF
from pipelex.tools.storage.in_memory_storage_provider import InMemoryStorageProvider
from pipelex.tools.storage.storage_file_name import STORAGE_FILE_EXTENSION_PATTERN, STORAGE_FILE_STEM_PATTERN
from tests.unit.pipelex.core.stuffs.stored_value.cases import STORED_HTML, STORED_JSON_OBJ, STORED_TEXT

STORAGE_SCOPE = "org_abc/mt_1/run_9"
STORAGE_URI_SCHEME = "pipelex-storage://"


def _sha16(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


@pytest.mark.asyncio(loop_scope="class")
class TestStoredValueStoring:
    @pytest.mark.parametrize(
        ("content", "stored_text", "mime_type", "extension"),
        [
            (TextContent(text=STORED_TEXT), STORED_TEXT, "text/plain", "txt"),
            (MarkdownContent(text=STORED_TEXT), STORED_TEXT, "text/markdown", "md"),
            (HtmlContent(inner_html=STORED_HTML), STORED_HTML, "text/html", "html"),
            (JSONContent(json_obj=STORED_JSON_OBJ), json.dumps(STORED_JSON_OBJ, ensure_ascii=False), "application/json", "json"),
        ],
    )
    @pytest.mark.parametrize("leaf", [GENERATED_CONTENT_LEAF, INPUT_ASSETS_LEAF])
    async def test_a_large_value_is_stored_under_the_run_s_scope_and_becomes_its_reference(
        self, content: StoredValueContent, stored_text: str, mime_type: str, extension: str, leaf: str
    ):
        content = content.model_copy(deep=True)
        storage = InMemoryStorageProvider()

        is_stored = await store_value_if_large(content, storage_provider=storage, storage_scope=STORAGE_SCOPE, leaf=leaf)

        assert is_stored
        expected_key = f"{STORAGE_SCOPE}/{leaf}/{_sha16(stored_text)}/value.{extension}"
        assert content.url is not None
        assert content.url.removeprefix(STORAGE_URI_SCHEME) == expected_key
        assert storage.root[expected_key] == stored_text.encode("utf-8")
        assert content.size == len(stored_text.encode("utf-8"))
        assert content.mime_type == mime_type
        assert content.preview == stored_text[:STORED_VALUE_PREVIEW_MAX_CHARS]
        # The value stays loaded in this process, and the dump is the reference alone.
        assert content.stored_text() == stored_text
        dumped = content.smart_dump()
        assert content.value_field_name not in dumped
        assert {"url", "size", "mime_type", "preview"} <= set(dumped)
        # The key's last segment is a filename every reader of a storage key accepts, the hosted platform's included.
        *directory_segments, file_name = expected_key.split("/")
        assert all(STORAGE_FILE_STEM_PATTERN.fullmatch(segment) for segment in directory_segments)
        stem, file_extension = file_name.split(".")
        assert STORAGE_FILE_STEM_PATTERN.fullmatch(stem)
        assert STORAGE_FILE_EXTENSION_PATTERN.fullmatch(file_extension)

    @pytest.mark.parametrize(
        ("topic", "content", "storage_scope", "inline_max_bytes"),
        [
            ("a value within the threshold", TextContent(text="short"), STORAGE_SCOPE, 4096),
            ("a value exactly at the threshold", TextContent(text="12345"), STORAGE_SCOPE, 5),
            ("an empty value", TextContent(text=""), STORAGE_SCOPE, 0),
            ("a dry run's scope", TextContent(text=STORED_TEXT), DRY_RUN_STORAGE_SCOPE, 0),
        ],
    )
    async def test_a_value_that_need_not_be_stored_stays_inline(
        self, mocker: MockerFixture, topic: str, content: TextContent, storage_scope: str, inline_max_bytes: int
    ):
        mocker.patch("pipelex.core.stuffs.stored_value_storer.inline_text_max_bytes", return_value=inline_max_bytes)
        content = content.model_copy(deep=True)
        storage = InMemoryStorageProvider()

        is_stored = await store_value_if_large(content, storage_provider=storage, storage_scope=storage_scope, leaf=GENERATED_CONTENT_LEAF)

        assert not is_stored, topic
        assert not content.is_stored, topic
        assert storage.root == {}, topic

    async def test_a_value_already_stored_is_not_stored_again(self):
        storage = InMemoryStorageProvider()
        content = TextContent(text=STORED_TEXT)
        await store_value_if_large(content, storage_provider=storage, storage_scope=STORAGE_SCOPE, leaf=GENERATED_CONTENT_LEAF)
        first_url = content.url

        is_stored_again = await store_value_if_large(
            content, storage_provider=storage, storage_scope="org_abc/mt_1/run_10", leaf=GENERATED_CONTENT_LEAF
        )

        assert not is_stored_again
        assert content.url == first_url
        assert len(storage.root) == 1

    async def test_every_value_of_a_tree_is_stored_wherever_it_sits(self):
        storage = InMemoryStorageProvider()
        pages = ListContent[TextContent](items=[TextContent(text=f"page {index_page}: {STORED_TEXT}") for index_page in range(3)])
        report = HtmlContent(inner_html=STORED_HTML)

        nb_stored = await store_large_values(
            roots={"pages": pages, "report": report}, storage_provider=storage, storage_scope=STORAGE_SCOPE, leaf=GENERATED_CONTENT_LEAF
        )

        assert nb_stored == 4
        assert all(page.is_stored for page in pages.items)
        assert report.is_stored
        assert all(key.startswith(f"{STORAGE_SCOPE}/{GENERATED_CONTENT_LEAF}/") for key in storage.root)

    async def test_a_dry_run_s_scope_stores_no_value_of_a_tree(self):
        storage = InMemoryStorageProvider()
        text = TextContent(text=STORED_TEXT)

        nb_stored = await store_large_values(
            roots={"text": text}, storage_provider=storage, storage_scope=DRY_RUN_STORAGE_SCOPE, leaf=GENERATED_CONTENT_LEAF
        )

        assert nb_stored == 0
        assert not text.is_stored
        assert storage.root == {}
