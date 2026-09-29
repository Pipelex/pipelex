"""A mocked image or document carries a URL that a scoped run may read: an https URL or a data URL.

A run with a read scope authorizes URLs before the dry-run branch, so a mock whose URL is a random
string, which `resolve_uri` takes for a local path, would be refused by the very dry run that made it.
"""

import base64

import pypdfium2
from pydantic import BaseModel

from pipelex.cogt.content_generation.dry_run_factory import MOCK_DOCUMENT_DATA_URL, DryRunFactory
from pipelex.config import get_config
from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.text_and_images_content import TextAndImagesContent
from pipelex.tools.uri.uri_read_scope import authorize_uri_read


class Dossier(StructuredContent):
    cover: ImageContent
    attachments: list[DocumentContent]
    page: TextAndImagesContent


class _Wrapper(BaseModel):
    dossier: Dossier


class TestDryRunFactoryFileUrls:
    def test_a_mocked_image_carries_a_configured_dry_run_image_url(self) -> None:
        image_content = DryRunFactory.make_dry_run_factory(ImageContent).build(factory_use_construct=True)
        assert image_content.url in get_config().inference.dry_run.image_urls

    def test_a_mocked_document_carries_the_blank_pdf_data_url(self) -> None:
        document_content = DryRunFactory.make_dry_run_factory(DocumentContent).build(factory_use_construct=True)
        assert document_content.url == MOCK_DOCUMENT_DATA_URL

    def test_the_blank_pdf_is_a_pdf_a_reader_opens(self) -> None:
        pdf_bytes = base64.b64decode(MOCK_DOCUMENT_DATA_URL.split(",", 1)[1])
        pdf_document = pypdfium2.PdfDocument(pdf_bytes)
        try:
            assert len(pdf_document) == 1
        finally:
            pdf_document.close()

    def test_nested_images_and_documents_are_mocked_the_same_way(self) -> None:
        wrapper = DryRunFactory.make_dry_run_factory(_Wrapper).build()
        dossier = wrapper.dossier
        assert dossier.cover.url in get_config().inference.dry_run.image_urls
        assert all(attachment.url == MOCK_DOCUMENT_DATA_URL for attachment in dossier.attachments)
        for image in dossier.page.images or []:
            assert image.url in get_config().inference.dry_run.image_urls

    def test_a_scoped_run_reads_every_mocked_file_url(self) -> None:
        image_content = DryRunFactory.make_dry_run_factory(ImageContent).build(factory_use_construct=True)
        document_content = DryRunFactory.make_dry_run_factory(DocumentContent).build(factory_use_construct=True)
        authorize_uri_read(uri=image_content.url, read_scope="org_abc", position="a mocked image")
        authorize_uri_read(uri=document_content.url, read_scope="org_abc", position="a mocked document")
