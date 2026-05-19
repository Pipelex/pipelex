import asyncio
import base64
import tempfile
from pathlib import Path
from typing import Any

import aiofiles
from typing_extensions import override

from pipelex.cogt.exceptions import ExtractJobFailureError, InferenceErrorCategory, SdkTypeError
from pipelex.cogt.extract.extract_input import ExtractInputError
from pipelex.cogt.extract.extract_job import ExtractJob
from pipelex.cogt.extract.extract_output import ExtractOutput
from pipelex.cogt.extract.extract_worker_abstract import ExtractWorkerAbstract
from pipelex.cogt.file.file_preparation_utils import prepare_file_from_uri
from pipelex.cogt.inference.error_classification import UserAction, UserActionKind, extract_local_extract_metadata
from pipelex.cogt.inference.provider_name import ProviderName
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.plugins.docling.docling_factory import DoclingFactory
from pipelex.plugins.docling.docling_sdk import DoclingSdk
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.tools.uri.prepared_file import PreparedFileBase64, PreparedFileHttpUrl, PreparedFileLocalPath


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
        """Extract text from any supported URI type (file path, http(s) URL, pipelex-storage://, or base64 data URL)."""
        prepared = await prepare_file_from_uri(
            uri=source_uri,
            keep_http_url=True,
            keep_local_path=True,
        )

        docling_source: str
        temp_path: Path | None = None

        match prepared:
            case PreparedFileHttpUrl():
                docling_source = prepared.url
            case PreparedFileLocalPath():
                docling_source = prepared.path
            case PreparedFileBase64():
                # Docling needs a file path, so write base64 data to temp file
                suffix = f".{prepared.file_type.extension}" if prepared.file_type.extension else ".pdf"
                with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp_file:
                    temp_path = Path(temp_file.name)
                try:
                    async with aiofiles.open(temp_path, "wb") as file:
                        await file.write(base64.b64decode(prepared.base64_data))
                    docling_source = str(temp_path)
                except BaseException:
                    temp_path.unlink(missing_ok=True)
                    raise

        try:
            # Run synchronous Docling conversion in a thread pool to avoid blocking
            conversion_result = await asyncio.to_thread(self.docling_sdk.document_converter.convert, docling_source)
            return DoclingFactory.make_extract_output_from_docling_document(doc=conversion_result.document)
        except ExtractJobFailureError:
            raise
        # The exceptions below are raised by docling's document_converter.convert() for
        # corrupt/unreadable documents, unsupported formats, or file system issues.
        except FileNotFoundError as exc:
            msg = f"Document file not found for Docling extraction: {exc}"
            raise ExtractJobFailureError(
                msg,
                error_category=InferenceErrorCategory.CONTENT,
                user_action=UserAction(
                    kind=UserActionKind.CHANGE_INPUT,
                    detail="The source document path could not be found — check the URI or file path",
                ),
                provider_metadata=extract_local_extract_metadata(exc, provider=ProviderName.DOCLING),
            ) from exc
        except ValueError as exc:
            msg = f"Invalid document format for Docling extraction: {exc}"
            raise ExtractJobFailureError(
                msg,
                error_category=InferenceErrorCategory.CONTENT,
                user_action=UserAction(
                    kind=UserActionKind.CHANGE_INPUT,
                    detail="Docling could not parse the document — verify the format is supported",
                ),
                provider_metadata=extract_local_extract_metadata(exc, provider=ProviderName.DOCLING),
            ) from exc
        except RuntimeError as exc:
            msg = f"Docling conversion failed: {exc}"
            raise ExtractJobFailureError(
                msg,
                error_category=InferenceErrorCategory.CONTENT,
                user_action=UserAction(
                    kind=UserActionKind.CHANGE_INPUT,
                    detail="Docling failed to convert the document — the file may be corrupt or unsupported",
                ),
                provider_metadata=extract_local_extract_metadata(exc, provider=ProviderName.DOCLING),
            ) from exc
        except OSError as exc:
            msg = f"I/O error during Docling extraction: {exc}"
            raise ExtractJobFailureError(
                msg,
                error_category=InferenceErrorCategory.TRANSIENT,
                user_action=UserAction(
                    kind=UserActionKind.WAIT_AND_RETRY,
                    detail="I/O error during Docling extraction — the system will retry automatically",
                ),
                provider_metadata=extract_local_extract_metadata(exc, provider=ProviderName.DOCLING),
            ) from exc
        finally:
            if temp_path:
                temp_path.unlink(missing_ok=True)
