from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from pipelex.providers.openai.openai_completions_factory import OpenAICompletionsFactory
from tests.helpers.storage_uri_prompt_files import STORED_IMAGE, STORED_PDF, content_parts, make_stored_files_llm_job, mock_storage_load

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


@pytest.mark.asyncio(loop_scope="class")
class TestOpenAICompletionsStorageUri:
    async def test_opted_in_an_image_travels_as_its_uri(self, mocker: MockerFixture) -> None:
        """`image_url.url` carries the URI, with no storage read."""
        load = mock_storage_load(mocker)
        factory = OpenAICompletionsFactory(is_http_url_enabled=False, is_storage_uri_enabled=True)

        messages = await factory.make_simple_messages(llm_job=make_stored_files_llm_job(with_document=False))

        parts = content_parts(messages[-1])
        assert parts[1] == {"type": "image_url", "image_url": {"url": STORED_IMAGE, "detail": "auto"}}
        load.assert_not_called()

    async def test_opted_in_a_document_is_still_inlined(self, mocker: MockerFixture) -> None:
        """The Chat Completions file part has no URL form, so a stored document's bytes are sent whatever the flag."""
        load = mock_storage_load(mocker)
        factory = OpenAICompletionsFactory(is_http_url_enabled=False, is_storage_uri_enabled=True)

        messages = await factory.make_simple_messages(llm_job=make_stored_files_llm_job())

        parts = content_parts(messages[-1])
        assert parts[1]["image_url"]["url"] == STORED_IMAGE
        assert parts[2]["file"]["file_data"].startswith("data:application/pdf;base64,")
        load.assert_awaited_once_with(uri=STORED_PDF)

    async def test_by_default_an_image_travels_as_base64(self, mocker: MockerFixture) -> None:
        """Off, the default, the image is read and sent as a data URL, even with HTTP URLs enabled."""
        load = mock_storage_load(mocker)
        factory = OpenAICompletionsFactory(is_http_url_enabled=True)

        messages = await factory.make_simple_messages(llm_job=make_stored_files_llm_job(with_document=False))

        parts = content_parts(messages[-1])
        assert parts[1]["image_url"]["url"].startswith("data:image/png;base64,")
        load.assert_awaited_once_with(uri=STORED_IMAGE)
