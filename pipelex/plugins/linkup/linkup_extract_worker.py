from typing import Any

from linkup import (
    LinkupAuthenticationError,
    LinkupClient,
    LinkupFailedFetchError,
    LinkupFetchResponse,
    LinkupFetchResponseTooLargeError,
    LinkupFetchUrlIsFileError,
    LinkupInsufficientCreditError,
    LinkupInvalidRequestError,
    LinkupNoResultError,
    LinkupTimeoutError,
    LinkupTooManyRequestsError,
    LinkupUnknownError,
)
from typing_extensions import override

from pipelex.cogt.extract.extract_job import ExtractJob
from pipelex.cogt.extract.extract_output import ExtractedImageFromPage, ExtractOutput, Page
from pipelex.cogt.extract.extract_worker_abstract import ExtractWorkerAbstract
from pipelex.cogt.inference.error_classification import extract_linkup_metadata
from pipelex.cogt.inference.error_classify import classify_inference_error
from pipelex.cogt.inference.error_render import InferenceErrorFamily, render_inference_error
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.usage.token_category import TokenCategory
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.runtime_hub import get_secrets_provider


class LinkupExtractWorker(ExtractWorkerAbstract):
    def __init__(
        self,
        extra_config: dict[str, Any],
        inference_model: InferenceModelSpec,
        reporting_delegate: ReportingProtocol | None = None,
    ) -> None:
        ExtractWorkerAbstract.__init__(
            self,
            extra_config=extra_config,
            inference_model=inference_model,
            reporting_delegate=reporting_delegate,
        )
        api_key = get_secrets_provider().get_secret(secret_id="LINKUP_API_KEY")
        self._linkup_client = LinkupClient(api_key=api_key)

    @override
    async def _extract_pages(
        self,
        extract_job: ExtractJob,
    ) -> ExtractOutput:
        document_uri = extract_job.extract_input.document_uri
        if not document_uri:
            msg = "LinkupExtractWorker requires a document_uri (web URL) in ExtractInput"
            raise ValueError(msg)

        job_params = extract_job.job_params
        extract_images = job_params.max_nb_images is None or job_params.max_nb_images > 0

        try:
            response: LinkupFetchResponse = await self._linkup_client.async_fetch(
                url=document_uri,
                render_js=job_params.render_js,
                include_raw_html=job_params.include_raw_html,
                extract_images=extract_images,
            )
        except (
            LinkupAuthenticationError,
            LinkupInsufficientCreditError,
            LinkupTooManyRequestsError,
            LinkupTimeoutError,
            LinkupInvalidRequestError,
            LinkupFetchResponseTooLargeError,
            LinkupFetchUrlIsFileError,
            LinkupFailedFetchError,
            LinkupNoResultError,
            LinkupUnknownError,
        ) as sdk_exc:
            metadata = extract_linkup_metadata(sdk_exc)
            classification = classify_inference_error(metadata)
            raise render_inference_error(
                metadata=metadata,
                classification=classification,
                family=InferenceErrorFamily.EXTRACT,
                model_desc=self.inference_model.desc,
                model_handle=self.inference_model.name,
            ) from sdk_exc

        # Per-request cost model: costs are defined per million, so 1 request = 1_000_000
        if extract_tokens_usage := extract_job.job_report.extract_tokens_usage:
            extract_tokens_usage.nb_tokens_by_category = {
                TokenCategory.INPUT: 1_000_000,
                TokenCategory.OUTPUT: 1_000_000,
            }

        max_images = job_params.max_nb_images
        extracted_images: list[ExtractedImageFromPage] = []
        if response.images:
            for image in response.images:
                if max_images is not None and len(extracted_images) >= max_images:
                    break
                extracted_images.append(
                    ExtractedImageFromPage(
                        size=None,
                        actual_url=image.url,
                        mime_type=None,
                        caption=image.alt or None,
                    )
                )

        page = Page(
            text=response.markdown,
            raw_html=response.raw_html,
            extracted_images=extracted_images,
        )

        return ExtractOutput(pages={0: page})
