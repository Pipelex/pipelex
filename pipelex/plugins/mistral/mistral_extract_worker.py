from typing import Any

from mistralai import Mistral
from typing_extensions import override

from pipelex.cogt.exceptions import ExtractCapabilityError, SdkTypeError
from pipelex.cogt.extract.extract_input import ExtractInputError
from pipelex.cogt.extract.extract_job import ExtractJob
from pipelex.cogt.extract.extract_job_components import ExtractJobParams
from pipelex.cogt.extract.extract_output import ExtractOutput
from pipelex.cogt.extract.extract_worker_abstract import ExtractWorkerAbstract
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.plugins.mistral.mistral_factory import MistralFactory
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.tools.misc.base64_utils import make_base64_url_from_path
from pipelex.tools.uri.resolved_uri import (
    ResolvedBase64DataUrl,
    ResolvedHttpUrl,
    ResolvedLocalPath,
    ResolvedPipelexStorage,
)
from pipelex.tools.uri.uri_resolver import resolve_uri


class MistralExtractWorker(ExtractWorkerAbstract):
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

        if not isinstance(sdk_instance, Mistral):
            msg = f"Provided OCR sdk_instance for {self.__class__.__name__} is not of type Mistral: it's a '{type(sdk_instance)}'"
            raise SdkTypeError(msg)

        self.mistral_client: Mistral = sdk_instance

    @override
    async def _extract_pages(
        self,
        extract_job: ExtractJob,
    ) -> ExtractOutput:
        # TODO: report usage
        if image_uri := extract_job.extract_input.image_uri:
            extract_output = await self._extract_page_from_image(
                image_uri=image_uri,
            )

        elif document_uri := extract_job.extract_input.document_uri:
            extract_output = await self._extract_pages_from_document(
                document_uri=document_uri,
                extract_job_params=extract_job.job_params,
            )
        else:
            msg = "No image nor document URI provided in ExtractJob"
            raise ExtractInputError(msg)
        return extract_output

    async def _extract_page_from_image(
        self,
        image_uri: str,
    ) -> ExtractOutput:
        resolved_uri = resolve_uri(image_uri)
        image_url: str
        match resolved_uri:
            case ResolvedHttpUrl():
                image_url = resolved_uri.url
            case ResolvedLocalPath():
                image_url = await make_base64_url_from_path(path=resolved_uri.path)
            case ResolvedPipelexStorage() | ResolvedBase64DataUrl():
                msg = f"Unsupported URI type for Mistral image extraction: {resolved_uri.kind}"
                raise ExtractInputError(msg)
        return await self._extract_from_image_url(image_url=image_url)

    async def _extract_pages_from_document(
        self,
        document_uri: str,
        extract_job_params: ExtractJobParams,
    ) -> ExtractOutput:
        if extract_job_params.should_caption_images:
            msg = "Captioning is not implemented for Mistral OCR."
            raise ExtractCapabilityError(msg)
        resolved_uri = resolve_uri(document_uri)
        document_url: str
        match resolved_uri:
            case ResolvedHttpUrl():
                document_url = resolved_uri.url
            case ResolvedLocalPath():
                document_url = await self._get_signed_url_from_document_file(document_path=resolved_uri.path)
            case ResolvedPipelexStorage() | ResolvedBase64DataUrl():
                msg = f"Unsupported URI type for Mistral document extraction: {resolved_uri.kind}"
                raise ExtractInputError(msg)
        return await self._extract_from_document_url(
            document_url=document_url,
            extract_job_params=extract_job_params,
        )

    async def _extract_from_image_url(
        self,
        image_url: str,
    ) -> ExtractOutput:
        extract_response = await self.mistral_client.ocr.process_async(
            model=self.inference_model.model_id,
            document={
                "type": "image_url",
                "image_url": image_url,
            },
        )
        return await MistralFactory.make_extract_output_from_mistral_response(
            mistral_extract_response=extract_response,
        )

    async def _extract_from_document_url(
        self,
        document_url: str,
        extract_job_params: ExtractJobParams,
    ) -> ExtractOutput:
        image_limit: int | None = extract_job_params.max_nb_images
        image_min_size: int | None = extract_job_params.image_min_size
        if not extract_job_params.should_include_images:
            image_limit = None
            image_min_size = None
        extract_response = await self.mistral_client.ocr.process_async(
            model=self.inference_model.model_id,
            document={
                "type": "document_url",
                "document_url": document_url,
            },
            include_image_base64=True,
            image_limit=image_limit,
            image_min_size=image_min_size,
        )

        return await MistralFactory.make_extract_output_from_mistral_response(
            mistral_extract_response=extract_response,
            should_include_images=extract_job_params.should_include_images,
        )

    async def _get_signed_url_from_document_file(
        self,
        document_path: str,
    ) -> str:
        """Upload a PDF file to Mistral and return a signed URL for it."""
        uploaded_file_id = await MistralFactory.upload_file_to_mistral_for_ocr(
            mistral_client=self.mistral_client,
            file_path=document_path,
        )
        signed_url = await self.mistral_client.files.get_signed_url_async(
            file_id=uploaded_file_id,
        )
        return signed_url.url
