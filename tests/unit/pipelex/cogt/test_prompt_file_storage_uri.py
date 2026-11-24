from __future__ import annotations

import base64
from typing import TYPE_CHECKING

import pytest

from pipelex.cogt.document.prompt_document import PromptDocumentUri
from pipelex.cogt.document.prompt_document_utils import prep_prompt_documents, prepare_prompt_document
from pipelex.cogt.image.prompt_image import PromptImageUri
from pipelex.cogt.image.prompt_image_utils import prep_prompt_images, prepare_prompt_image
from pipelex.tools.uri.prepared_file import PreparedFileBase64, PreparedFileStorageUri
from tests.helpers.storage_uri_prompt_files import PDF_BYTES, PNG_BYTES, STORED_IMAGE, STORED_PDF, mock_storage_load

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


@pytest.mark.asyncio(loop_scope="class")
class TestPromptFileStorageUri:
    async def test_opted_in_an_image_keeps_its_uri_unread(self, mocker: MockerFixture) -> None:
        """The URI comes back unchanged and the storage is never read."""
        load = mock_storage_load(mocker)

        prepared = await prepare_prompt_image(PromptImageUri(uri=STORED_IMAGE), is_http_url_enabled=False, is_storage_uri_enabled=True)
        batch = await prep_prompt_images(prompt_images=[PromptImageUri(uri=STORED_IMAGE)], is_http_url_enabled=False, is_storage_uri_enabled=True)

        assert prepared == PreparedFileStorageUri(storage_uri=STORED_IMAGE)
        assert batch == [PreparedFileStorageUri(storage_uri=STORED_IMAGE)]
        load.assert_not_called()

    async def test_opted_in_a_document_keeps_its_uri_unread(self, mocker: MockerFixture) -> None:
        """The URI comes back unchanged and the storage is never read."""
        load = mock_storage_load(mocker)

        prepared = await prepare_prompt_document(PromptDocumentUri(uri=STORED_PDF), is_http_url_enabled=False, is_storage_uri_enabled=True)
        batch = await prep_prompt_documents(
            prompt_documents=[PromptDocumentUri(uri=STORED_PDF)], is_http_url_enabled=False, is_storage_uri_enabled=True
        )

        assert prepared == PreparedFileStorageUri(storage_uri=STORED_PDF)
        assert batch == [PreparedFileStorageUri(storage_uri=STORED_PDF)]
        load.assert_not_called()

    async def test_by_default_a_stored_image_is_loaded_as_base64(self, mocker: MockerFixture) -> None:
        """Off, which is the default, the object is read and inlined, URL support or not."""
        load = mock_storage_load(mocker)

        prepared = await prepare_prompt_image(PromptImageUri(uri=STORED_IMAGE), is_http_url_enabled=True)

        assert isinstance(prepared, PreparedFileBase64)
        assert prepared.base64_data == base64.b64encode(PNG_BYTES).decode("ascii")
        assert prepared.mime_type == "image/png"
        load.assert_awaited_once_with(uri=STORED_IMAGE)

    async def test_by_default_a_stored_document_is_loaded_as_base64(self, mocker: MockerFixture) -> None:
        """Off, which is the default, the object is read and inlined, URL support or not."""
        load = mock_storage_load(mocker)

        prepared = await prepare_prompt_document(PromptDocumentUri(uri=STORED_PDF), is_http_url_enabled=True)

        assert isinstance(prepared, PreparedFileBase64)
        assert prepared.base64_data == base64.b64encode(PDF_BYTES).decode("ascii")
        assert prepared.mime_type == "application/pdf"
        load.assert_awaited_once_with(uri=STORED_PDF)
