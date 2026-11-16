import hashlib

import pytest

from pipelex.cogt.content_generation.generated_content_factory import GeneratedContentFactory
from pipelex.cogt.extract.extract_output import ExtractOutput, Page
from pipelex.core.stuffs.markdown_content import MarkdownContent
from pipelex.core.stuffs.stored_value_storer import STORED_VALUE_PREVIEW_MAX_CHARS
from pipelex.core.stuffs.text_content import TextContent
from pipelex.system.storage_scope import DRY_RUN_STORAGE_SCOPE
from pipelex.tools.storage.in_memory_storage_provider import InMemoryStorageProvider

STORAGE_SCOPE = "org_abc/mt_1/run_9"
GENERATED_TEXT = "A long answer from the model, sentence after sentence.\n" * 12


def _expected_key(*, text: str, extension: str) -> str:
    return f"{STORAGE_SCOPE}/generated/{hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]}/value.{extension}"


@pytest.mark.asyncio(loop_scope="class")
class TestGeneratedTextStorage:
    @pytest.mark.parametrize(
        ("output_mime_type", "content_class", "extension"),
        [
            ("text/plain", TextContent, "txt"),
            ("text/markdown", MarkdownContent, "md"),
        ],
    )
    async def test_a_generated_text_past_the_threshold_is_stored_by_the_leaf(
        self, output_mime_type: str, content_class: type[TextContent], extension: str
    ):
        storage = InMemoryStorageProvider()
        factory = GeneratedContentFactory(storage_provider=storage)

        text_content = await factory.make_text_content(
            storage_scope=STORAGE_SCOPE, text=GENERATED_TEXT, output_mime_type=output_mime_type, is_dry=False
        )

        assert type(text_content) is content_class
        expected_key = _expected_key(text=GENERATED_TEXT, extension=extension)
        assert text_content.url == f"pipelex-storage://{expected_key}"
        assert storage.root[expected_key] == GENERATED_TEXT.encode("utf-8")
        assert text_content.mime_type == output_mime_type
        assert text_content.preview == GENERATED_TEXT[:STORED_VALUE_PREVIEW_MAX_CHARS]
        assert text_content.require_text() == GENERATED_TEXT

    @pytest.mark.parametrize(
        ("topic", "storage_scope", "is_dry"),
        [
            ("a dry run", STORAGE_SCOPE, True),
            ("a dry run's storage scope", DRY_RUN_STORAGE_SCOPE, False),
        ],
    )
    async def test_a_dry_run_stores_no_generated_text(self, topic: str, storage_scope: str, is_dry: bool):
        storage = InMemoryStorageProvider()
        factory = GeneratedContentFactory(storage_provider=storage)

        text_content = await factory.make_text_content(storage_scope=storage_scope, text=GENERATED_TEXT, output_mime_type="text/plain", is_dry=is_dry)

        assert not text_content.is_stored, topic
        assert text_content.require_text() == GENERATED_TEXT, topic
        assert storage.root == {}, topic

    async def test_each_extracted_page_s_text_is_stored(self):
        storage = InMemoryStorageProvider()
        factory = GeneratedContentFactory(storage_provider=storage)
        page_texts = [f"Page {index_page}. {GENERATED_TEXT}" for index_page in range(3)]
        extract_output = ExtractOutput(pages={index_page: Page(text=page_text) for index_page, page_text in enumerate(page_texts)})

        page_contents = await factory.make_page_contents(STORAGE_SCOPE, extract_output=extract_output)

        stored_pages: list[TextContent] = []
        for page_content in page_contents:
            page_text = page_content.text_and_images.text
            assert page_text is not None
            stored_pages.append(page_text)
        assert [page_text.url for page_text in stored_pages] == [
            f"pipelex-storage://{_expected_key(text=page_text, extension='txt')}" for page_text in page_texts
        ]
        assert [page_text.require_text() for page_text in stored_pages] == page_texts
