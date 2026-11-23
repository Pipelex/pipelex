"""Shared pieces of the tests of stored prompt files kept as `pipelex-storage://` references.

With `is_storage_uri_enabled` on, preparation returns the URI unchanged and makes no storage read, and each factory
sends it as a URL part. Off, which is what every backend Pipelex ships runs with, the object is loaded and sent as
base64. The storage provider is a mock whose `load` the tests assert on both sides.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from pipelex.cogt.document.prompt_document import PromptDocument, PromptDocumentUri
from pipelex.cogt.image.prompt_image import PromptImage, PromptImageUri
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_job_components import LLMJobConfig, LLMJobParams
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.system.job_metadata import JobMetadata, RunMetadata

if TYPE_CHECKING:
    from unittest.mock import AsyncMock

    from pytest_mock import MockerFixture

STORED_IMAGE = "pipelex-storage://org/uploads/photo.png"
STORED_PDF = "pipelex-storage://org/uploads/brief.pdf"
# A PNG signature and a PDF header are all the file-type sniffer needs to name each kind.
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
PDF_BYTES = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<<>>\nendobj\n"


def mock_storage_load(mocker: MockerFixture) -> AsyncMock:
    """Serve every storage read of prompt preparation from a mock, for images and documents alike, and return its `load`."""

    def _load(*, uri: str) -> bytes:
        return PDF_BYTES if uri.endswith(".pdf") else PNG_BYTES

    storage = mocker.MagicMock()
    storage.load = mocker.AsyncMock(side_effect=_load)
    mocker.patch("pipelex.cogt.image.prompt_image_utils.get_storage_provider", return_value=storage)
    mocker.patch("pipelex.cogt.document.prompt_document_utils.get_storage_provider", return_value=storage)
    return cast("AsyncMock", storage.load)


def make_stored_files_llm_job(*, with_document: bool = True) -> LLMJob:
    """A job whose prompt holds a text, a stored image and, unless told otherwise, a stored PDF, in that order."""
    user_images: list[PromptImage] = [PromptImageUri(uri=STORED_IMAGE)]
    user_documents: list[PromptDocument] = [PromptDocumentUri(uri=STORED_PDF, mime_type="application/pdf")] if with_document else []
    return LLMJob(
        job_metadata=JobMetadata(
            run_metadata=RunMetadata(user_id="pytest", pipeline_run_id="plr-storage-uri", storage_scope="org", read_scope=None),
            pipe_code="describe_files",
        ),
        llm_prompt=LLMPrompt(user_text="Describe the files.", user_images=user_images, user_documents=user_documents),
        job_params=LLMJobParams(temperature=0.5),
        job_config=LLMJobConfig(schema_reask_max_attempts=1),
    )


def content_parts(message: Any) -> list[dict[str, Any]]:
    """The content parts of a built message, typed for asserting on."""
    return cast("list[dict[str, Any]]", message["content"])
