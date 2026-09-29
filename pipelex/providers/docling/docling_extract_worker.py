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
from pipelex.cogt.file.file_preparation_utils import prepare_file_from_uri
from pipelex.cogt.inference.error_classification import extract_local_extract_metadata
from pipelex.cogt.inference.error_classify import classify_inference_error
from pipelex.cogt.inference.error_render import InferenceErrorFamily, render_inference_error
from pipelex.cogt.inference.provider_name import ProviderName
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.providers.docling.docling_factory import DoclingFactory
from pipelex.providers.docling.docling_sdk import DoclingSdk
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.tools.misc.file_fetch_utils import fetch_file_and_content_type_from_url_httpx
from pipelex.tools.misc.filetype_utils import UNKNOWN_FILE_TYPE, mime_type_to_extension
from pipelex.tools.uri.prepared_file import PreparedFileBase64, PreparedFileHttpUrl, PreparedFileLocalPath
from pipelex.tools.uri.resolved_uri import ResolvedHttpUrl
from pipelex.tools.uri.uri_resolver import resolve_uri

# An extension taken from a URL's path names a temp file, so only a plain one is kept.
_PLAIN_SUFFIX_PATTERN = re.compile(r"\.[A-Za-z0-9]{1,16}")


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

        An http(s) URL is downloaded by the runtime's fetch helper, never handed to Docling.
        Docling's own client checks each host with a single DNS lookup before connecting, which
        a record that changes in between defeats, and it does not follow the runtime's
        `is_fetch_ssrf_guard_enabled` switch. The helper vets the address it actually connects
        to, on every redirect hop.
        """
        docling_source: str
        temp_path: Path | None = None

        resolved_uri = resolve_uri(source_uri)
        if isinstance(resolved_uri, ResolvedHttpUrl):
            raw_bytes, media_type = await fetch_file_and_content_type_from_url_httpx(resolved_uri.url)
            temp_path = await self._write_temp_file(
                data=raw_bytes,
                suffix=self._suffix_for_downloaded_url(url=resolved_uri.url, media_type=media_type),
            )
            docling_source = str(temp_path)
        else:
            prepared = await prepare_file_from_uri(
                uri=source_uri,
                keep_http_url=False,
                keep_local_path=True,
            )
            match prepared:
                case PreparedFileHttpUrl():
                    # This shouldn't happen: http(s) URLs are downloaded above
                    msg = f"Unexpected PreparedFileHttpUrl for URI: {source_uri}"
                    raise TypeError(msg)
                case PreparedFileLocalPath():
                    docling_source = prepared.path
                case PreparedFileBase64():
                    # Docling needs a file path, so write base64 data to temp file
                    suffix = f".{prepared.file_type.extension}" if prepared.file_type.extension else ".pdf"
                    temp_path = await self._write_temp_file(data=base64.b64decode(prepared.base64_data), suffix=suffix)
                    docling_source = str(temp_path)

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
        finally:
            if temp_path:
                temp_path.unlink(missing_ok=True)

    @classmethod
    def _suffix_for_downloaded_url(cls, *, url: str, media_type: str | None) -> str:
        """Pick the extension a downloaded file is written under, so Docling can tell its format.

        Docling reads a file's format from its bytes first, which settles every binary format.
        A text format (HTML, Markdown, CSV) says nothing in its bytes, so Docling falls back on
        the extension: the URL path's own, as Docling used when it fetched URLs itself, else
        the one the server's declared content type implies. With neither, the file gets none,
        and Docling sniffs the content for HTML and CSV before reading it as plain text.
        """
        url_suffix = PurePosixPath(urlparse(url).path).suffix
        if _PLAIN_SUFFIX_PATTERN.fullmatch(url_suffix):
            return url_suffix
        if media_type:
            extension = mime_type_to_extension(media_type)
            if extension != UNKNOWN_FILE_TYPE:
                return f".{extension}"
        return ""

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
