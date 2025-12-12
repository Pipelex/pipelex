import asyncio
from typing import Any

from typing_extensions import override

from pipelex.cogt.exceptions import SdkTypeError
from pipelex.cogt.extract.extract_input import ExtractInputError
from pipelex.cogt.extract.extract_job import ExtractJob
from pipelex.cogt.extract.extract_output import ExtractOutput
from pipelex.cogt.extract.extract_worker_abstract import ExtractWorkerAbstract
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.plugins.docling.docling_factory import DoclingFactory
from pipelex.plugins.docling.docling_sdk import DoclingSdk
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.tools.misc.path_utils import clarify_path_or_url


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
        elif pdf_uri := extract_job.extract_input.pdf_uri:
            source_uri = pdf_uri
        else:
            msg = "Neither image URI nor PDF URI provided in ExtractJob"
            raise ExtractInputError(msg)

        return await self._extract_from_source(source_uri=source_uri)

    async def _extract_from_source(self, source_uri: str) -> ExtractOutput:
        """Extract text from a source URI (file path, file:// URI, or http(s) URL)."""
        source_path, source_url = clarify_path_or_url(path_or_uri=source_uri)
        resolved_source = source_url or source_path
        assert resolved_source is not None

        # Run synchronous Docling conversion in a thread pool to avoid blocking
        conversion_result = await asyncio.to_thread(self.docling_sdk.document_converter.convert, resolved_source)
        return DoclingFactory.make_extract_output_from_docling_document(doc=conversion_result.document)
