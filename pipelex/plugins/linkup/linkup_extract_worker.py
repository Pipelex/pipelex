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

from pipelex.cogt.exceptions import ExtractJobFailureError, InferenceErrorCategory
from pipelex.cogt.extract.extract_job import ExtractJob
from pipelex.cogt.extract.extract_output import ExtractedImageFromPage, ExtractOutput, Page
from pipelex.cogt.extract.extract_worker_abstract import ExtractWorkerAbstract
from pipelex.cogt.inference.error_classification import UserAction, UserActionKind, extract_linkup_metadata
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.usage.token_category import TokenCategory
from pipelex.hub import get_secrets_provider
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.urls import URLs


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

    def _classify_linkup_error(self, exc: Exception) -> ExtractJobFailureError:
        """Classify a Linkup SDK error into a categorized ExtractJobFailureError.

        The returned error carries a structured ``provider_metadata`` and a
        semantic ``UserActionKind`` so downstream consumers (retry, CLI,
        telemetry) get uniform shape across providers.
        """
        metadata = extract_linkup_metadata(exc)
        if isinstance(exc, LinkupAuthenticationError):
            msg = f"Linkup authentication error: {exc}"
            return ExtractJobFailureError(
                msg,
                error_category=InferenceErrorCategory.CONFIGURATION,
                user_action=UserAction(
                    kind=UserActionKind.CHECK_CREDENTIALS,
                    detail="Check that the LINKUP_API_KEY environment variable is set",
                ),
                provider_metadata=metadata,
            )
        if isinstance(exc, LinkupInsufficientCreditError):
            msg = f"Linkup credits exhausted: {exc}"
            return ExtractJobFailureError(
                msg,
                error_category=InferenceErrorCategory.CAPACITY,
                user_action=UserAction(
                    kind=UserActionKind.CHECK_BILLING,
                    detail=f"Your Linkup account has insufficient credits — check billing at {URLs.linkup_billing}",
                ),
                provider_metadata=metadata,
            )
        if isinstance(exc, LinkupTooManyRequestsError):
            msg = f"Linkup rate limit exceeded: {exc}"
            return ExtractJobFailureError(
                msg,
                error_category=InferenceErrorCategory.TRANSIENT,
                user_action=UserAction(
                    kind=UserActionKind.WAIT_AND_RETRY,
                    detail="Rate limited by Linkup — the system will retry automatically",
                ),
                provider_metadata=metadata,
            )
        if isinstance(exc, LinkupTimeoutError):
            msg = f"Linkup request timed out: {exc}"
            return ExtractJobFailureError(
                msg,
                error_category=InferenceErrorCategory.TRANSIENT,
                user_action=UserAction(
                    kind=UserActionKind.WAIT_AND_RETRY,
                    detail="Linkup request timed out — the system will retry automatically",
                ),
                provider_metadata=metadata,
            )
        if isinstance(exc, LinkupInvalidRequestError):
            msg = f"Linkup invalid request: {exc}"
            return ExtractJobFailureError(
                msg,
                error_category=InferenceErrorCategory.CONTENT,
                user_action=UserAction(
                    kind=UserActionKind.CHANGE_INPUT,
                    detail="Linkup rejected the request — review the URL and parameters",
                ),
                provider_metadata=metadata,
            )
        if isinstance(exc, (LinkupFetchResponseTooLargeError, LinkupFetchUrlIsFileError)):
            msg = f"Linkup fetch error: {exc}"
            return ExtractJobFailureError(
                msg,
                error_category=InferenceErrorCategory.CONTENT,
                user_action=UserAction(
                    kind=UserActionKind.CHANGE_INPUT,
                    detail="Linkup could not fetch the URL — the target may be too large or not a web page",
                ),
                provider_metadata=metadata,
            )
        if isinstance(exc, LinkupNoResultError):
            msg = f"Linkup found no results: {exc}"
            return ExtractJobFailureError(
                msg,
                error_category=InferenceErrorCategory.CONTENT,
                user_action=UserAction(
                    kind=UserActionKind.CHANGE_INPUT,
                    detail="Linkup found no results — broaden or rephrase the request",
                ),
                provider_metadata=metadata,
            )
        msg = f"Linkup error: {exc}"
        return ExtractJobFailureError(
            msg,
            error_category=InferenceErrorCategory.TRANSIENT,
            user_action=UserAction(
                kind=UserActionKind.WAIT_AND_RETRY,
                detail="Linkup returned an unexpected error — the system will retry automatically",
            ),
            provider_metadata=metadata,
        )

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
        ) as exc:
            raise self._classify_linkup_error(exc) from exc

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
