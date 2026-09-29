import asyncio
import base64
import re
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlparse

import aiofiles
from typing_extensions import override

from pipelex.cogt.exceptions import ExtractJobFailureError, SdkTypeError
from pipelex.cogt.extract.exceptions import ExtractInputError
from pipelex.cogt.extract.extract_job import ExtractJob
from pipelex.cogt.extract.extract_output import ExtractOutput
from pipelex.cogt.extract.extract_worker_abstract import ExtractWorkerAbstract
from pipelex.cogt.inference.error_classification import extract_local_extract_metadata
from pipelex.cogt.inference.error_classify import classify_inference_error
from pipelex.cogt.inference.error_render import InferenceErrorFamily, render_inference_error
from pipelex.cogt.inference.provider_name import ProviderName
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.providers.docling.docling_factory import DoclingFactory
from pipelex.providers.docling.docling_sdk import DoclingSdk
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.runtime_hub import get_storage_provider
from pipelex.tools.misc.file_fetch_utils import fetch_file_and_content_type_from_url_httpx
from pipelex.tools.misc.filetype_utils import mime_type_to_extension
from pipelex.tools.uri.resolved_uri import ResolvedBase64DataUrl, ResolvedHttpUrl, ResolvedLocalPath, ResolvedPipelexStorage
from pipelex.tools.uri.uri_resolver import resolve_uri

# A Google Drive, Docs, Sheets or Slides link names a viewer page, not the file. Docling
# rewrote one to its export URL when it downloaded URLs itself, and the download here does too.
_GOOGLE_LINK_PATTERN = re.compile(r"google\.com/(file|document|spreadsheets|presentation)/d/([\w-]+)")
_GOOGLE_EXPORT_URL_TEMPLATES = {
    "file": "https://drive.google.com/uc?export=download&id={doc_id}",
    "document": "https://docs.google.com/document/d/{doc_id}/export?format=docx",
    "spreadsheets": "https://docs.google.com/spreadsheets/d/{doc_id}/export?format=xlsx",
    "presentation": "https://docs.google.com/presentation/d/{doc_id}/export?format=pptx",
}


class DoclingExtractWorker(ExtractWorkerAbstract):
    def __init__(
        self,
        sdk_instance: Any,
        extra_config: dict[str, Any],
        inference_model: InferenceModelSpec,
        reporting_delegate: ReportingProtocol | None = None,
    ):
        super().__init__(
            extra_config=extra_config,
            inference_model=inference_model,
            reporting_delegate=reporting_delegate,
        )

        if not isinstance(sdk_instance, DoclingSdk):
            msg = f"Provided sdk_instance for {self.__class__.__name__} is not of type DoclingSdk: it's a '{type(sdk_instance)}'"
            raise SdkTypeError(msg)

        self.docling_sdk: DoclingSdk = sdk_instance

    @override
    async def _extract_pages(
        self,
        extract_job: ExtractJob,
    ) -> ExtractOutput:
        source_uri: str
        if image_uri := extract_job.extract_input.image_uri:
            source_uri = image_uri
        elif pdf_uri := extract_job.extract_input.document_uri:
            source_uri = pdf_uri
        else:
            msg = "Neither image URI nor PDF URI provided in ExtractJob"
            raise ExtractInputError(msg)

        return await self._extract_from_source(source_uri=source_uri)

    async def _extract_from_source(self, source_uri: str) -> ExtractOutput:
        """Extract text from any supported URI type (file path, http(s) URL, pipelex-storage://, or base64 data URL).

        Docling reads a path, so any source that is not a local file is written to a temp file
        first, named with an extension Docling can read the format from.

        An http(s) URL is downloaded by the runtime's fetch helper, never handed to Docling.
        Docling's own client checks each host with a single DNS lookup before connecting, which
        a record that changes in between defeats, and it does not follow the runtime's
        `is_fetch_ssrf_guard_enabled` switch. The helper vets the address it actually connects
        to, on every redirect hop.
        """
        raw_bytes: bytes
        media_type: str | None
        named_after: str | None
        resolved_uri = resolve_uri(source_uri)
        match resolved_uri:
            case ResolvedLocalPath():
                return await self._convert(docling_source=resolved_uri.path)
            case ResolvedHttpUrl():
                download_url = self._export_url_for_google_link(url=resolved_uri.url)
                raw_bytes, media_type = await fetch_file_and_content_type_from_url_httpx(download_url)
                named_after = download_url
            case ResolvedPipelexStorage():
                raw_bytes = await get_storage_provider().load(uri=resolved_uri.storage_uri)
                media_type = None
                named_after = resolved_uri.storage_uri
            case ResolvedBase64DataUrl():
                raw_bytes = base64.b64decode(resolved_uri.base64_data)
                media_type = resolved_uri.mime_type
                named_after = None

        temp_path = await self._write_temp_file(
            data=raw_bytes,
            suffix=self._suffix_for_docling(named_after=named_after, media_type=media_type),
        )
        try:
            return await self._convert(docling_source=str(temp_path))
        finally:
            temp_path.unlink(missing_ok=True)

    async def _convert(self, *, docling_source: str) -> ExtractOutput:
        try:
            # Run synchronous Docling conversion in a thread pool to avoid blocking
            conversion_result = await asyncio.to_thread(self.docling_sdk.document_converter.convert, docling_source)
            return DoclingFactory.make_extract_output_from_docling_document(doc=conversion_result.document)
        except ExtractJobFailureError:
            raise
        # The exceptions below are raised by docling's document_converter.convert() for
        # corrupt/unreadable documents, unsupported formats, or file system issues.
        except (FileNotFoundError, ValueError, RuntimeError, OSError) as sdk_exc:
            metadata = extract_local_extract_metadata(sdk_exc, provider=ProviderName.DOCLING)
            classification = classify_inference_error(metadata)
            raise render_inference_error(
                metadata=metadata,
                classification=classification,
                family=InferenceErrorFamily.EXTRACT,
                model_desc=self.inference_model.desc,
                model_handle=self.inference_model.name,
            ) from sdk_exc

    @classmethod
    def _export_url_for_google_link(cls, *, url: str) -> str:
        """Return the export URL of a Google Drive, Docs, Sheets or Slides link, and any other URL unchanged."""
        google_link = _GOOGLE_LINK_PATTERN.search(url)
        if not google_link:
            return url
        doc_type, doc_id = google_link.groups()
        return _GOOGLE_EXPORT_URL_TEMPLATES[doc_type].format(doc_id=doc_id)

    @classmethod
    def _suffix_for_docling(cls, *, named_after: str | None, media_type: str | None) -> str:
        """Pick the extension a temp file is written under, so Docling can tell its format.

        Docling reads a file's format from its bytes first, which settles every binary format.
        A text format (HTML, Markdown, CSV) says nothing in its bytes, so Docling falls back on
        the extension, and refuses one it does not know. So the extension is one Docling knows:
        the one the source's URL or storage key ends with, as Docling used when it fetched URLs
        itself, else the one the declared media type implies. With neither, the file gets none,
        and Docling recognizes HTML and CSV from the content and refuses anything else.
        """
        docling_extensions = cls._docling_extensions()
        if named_after:
            suffix = PurePosixPath(urlparse(named_after).path).suffix
            if suffix.removeprefix(".").lower() in docling_extensions:
                return suffix
        if media_type:
            extension = mime_type_to_extension(media_type)
            if extension.lower() in docling_extensions:
                return f".{extension}"
        return ""

    @classmethod
    def _docling_extensions(cls) -> frozenset[str]:
        """The file extensions Docling maps to a format, lowercased."""
        # Deferred import: avoid pulling heavy SDK at module-load time
        from docling.datamodel.base_models import FormatToExtensions  # ruff: ignore[import-outside-top-level]

        return frozenset(extension.lower() for extensions in FormatToExtensions.values() for extension in extensions)

    @classmethod
    async def _write_temp_file(cls, *, data: bytes, suffix: str) -> Path:
        """Write `data` to a new temp file named with `suffix`, which the caller deletes."""
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp_file:
            temp_path = Path(temp_file.name)
        try:
            async with aiofiles.open(temp_path, "wb") as file:
                await file.write(data)
        except BaseException:
            temp_path.unlink(missing_ok=True)
            raise
        return temp_path
