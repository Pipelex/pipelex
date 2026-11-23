from __future__ import annotations

import base64
from typing import TYPE_CHECKING

import pytest

from pipelex.providers.openai.openai_responses_factory import OpenAIResponsesFactory
from tests.helpers.storage_uri_prompt_files import (
    PDF_BYTES,
    PNG_BYTES,
    STORED_IMAGE,
    STORED_PDF,
    content_parts,
    make_stored_files_llm_job,
    mock_storage_load,
)

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


@pytest.mark.asyncio(loop_scope="class")
class TestOpenAIResponsesStorageUri:
    async def test_opted_in_the_uris_travel_as_url_parts(self, mocker: MockerFixture) -> None:
        """`input_image.image_url` and `input_file.file_url` carry the URI, with no storage read."""
        load = mock_storage_load(mocker)
        factory = OpenAIResponsesFactory(is_http_url_enabled=False, is_storage_uri_enabled=True)

        input_items = await factory.make_input_items(llm_job=make_stored_files_llm_job())

        parts = content_parts(input_items[0])
        assert parts[1] == {"type": "input_image", "image_url": STORED_IMAGE, "detail": "auto"}
        assert parts[2] == {"type": "input_file", "file_url": STORED_PDF}
        load.assert_not_called()

    async def test_by_default_the_files_travel_as_base64(self, mocker: MockerFixture) -> None:
        """Off, the default, both files are read and sent as data, even with HTTP URLs enabled."""
        load = mock_storage_load(mocker)
        factory = OpenAIResponsesFactory(is_http_url_enabled=True)

        input_items = await factory.make_input_items(llm_job=make_stored_files_llm_job())

        parts = content_parts(input_items[0])
        assert parts[1]["image_url"] == f"data:image/png;base64,{base64.b64encode(PNG_BYTES).decode('ascii')}"
        assert parts[2]["file_data"] == f"data:application/pdf;base64,{base64.b64encode(PDF_BYTES).decode('ascii')}"
        assert "file_url" not in parts[2]
        assert load.await_count == 2
