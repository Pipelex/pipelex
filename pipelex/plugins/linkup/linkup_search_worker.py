from datetime import date
from typing import Any

from linkup import (
    LinkupAuthenticationError,
    LinkupClient,
    LinkupInsufficientCreditError,
    LinkupInvalidRequestError,
    LinkupNoResultError,
    LinkupSourcedAnswer,
    LinkupTimeoutError,
    LinkupTooManyRequestsError,
    LinkupUnknownError,
)
from typing_extensions import override

from pipelex.cogt.exceptions import InferenceErrorCategory, SearchJobFailureError
from pipelex.cogt.inference.error_classification import UserAction, UserActionKind, extract_linkup_metadata
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.search.search_depth import SearchDepth
from pipelex.cogt.search.search_job import SearchJob
from pipelex.cogt.search.search_worker_abstract import SearchWorkerAbstract
from pipelex.cogt.usage.token_category import TokenCategory
from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.core.stuffs.search_result_content import SearchResultContent
from pipelex.hub import get_secrets_provider
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.tools.typing.pydantic_utils import BaseModelTypeVar
from pipelex.urls import URLs


class LinkupSearchWorker(SearchWorkerAbstract):
    def __init__(
        self,
        inference_model: InferenceModelSpec,
        reporting_delegate: ReportingProtocol | None = None,
    ) -> None:
        SearchWorkerAbstract.__init__(self, inference_model=inference_model, reporting_delegate=reporting_delegate)
        api_key = get_secrets_provider().get_secret(secret_id="LINKUP_API_KEY")
        self._linkup_client = LinkupClient(api_key=api_key)

    def _classify_linkup_error(self, exc: Exception) -> SearchJobFailureError:
        """Classify a Linkup SDK error into a categorized SearchJobFailureError.

        The returned error carries a structured ``provider_metadata`` and a
        semantic ``UserActionKind`` so downstream consumers (retry, CLI,
        telemetry) get uniform shape across providers.
        """
        metadata = extract_linkup_metadata(exc)
        if isinstance(exc, LinkupAuthenticationError):
            msg = f"Linkup authentication error: {exc}"
            return SearchJobFailureError(
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
            return SearchJobFailureError(
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
            return SearchJobFailureError(
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
            return SearchJobFailureError(
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
            return SearchJobFailureError(
                msg,
                error_category=InferenceErrorCategory.CONTENT,
                user_action=UserAction(
                    kind=UserActionKind.CHANGE_INPUT,
                    detail="Linkup rejected the request — review the query and parameters",
                ),
                provider_metadata=metadata,
            )
        msg = f"Linkup error: {exc}"
        return SearchJobFailureError(
            msg,
            error_category=InferenceErrorCategory.TRANSIENT,
            user_action=UserAction(
                kind=UserActionKind.WAIT_AND_RETRY,
                detail="Linkup returned an unexpected error — the system will retry automatically",
            ),
            provider_metadata=metadata,
        )

    def _parse_date(self, date_str: str | None) -> date | None:
        if date_str is None:
            return None
        return date.fromisoformat(date_str)

    @override
    async def _search_sourced_answer(
        self,
        search_job: SearchJob,
    ) -> SearchResultContent:
        job_params = search_job.job_params
        search_setting = job_params.search_setting

        depth_value = SearchDepth(self.inference_model.model_id.rsplit("/", 1)[-1])
        try:
            response: LinkupSourcedAnswer = await self._linkup_client.async_search(
                query=search_job.query,
                depth=depth_value,  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]
                output_type="sourcedAnswer",
                include_images=search_setting.include_images,
                include_inline_citations=search_setting.include_inline_citations,
                max_results=search_setting.max_results,
                include_domains=job_params.include_domains,
                exclude_domains=job_params.exclude_domains,
                from_date=self._parse_date(job_params.from_date),
                to_date=self._parse_date(job_params.to_date),
            )
        except (
            LinkupAuthenticationError,
            LinkupInsufficientCreditError,
            LinkupTooManyRequestsError,
            LinkupTimeoutError,
            LinkupInvalidRequestError,
            LinkupNoResultError,
            LinkupUnknownError,
        ) as exc:
            raise self._classify_linkup_error(exc) from exc

        # Per-request cost model: costs are defined per million, so 1 request = 1_000_000
        if search_tokens_usage := search_job.job_report.search_tokens_usage:
            search_tokens_usage.nb_tokens_by_category = {TokenCategory.INPUT: 1_000_000, TokenCategory.OUTPUT: 1_000_000}

        sources: list[DocumentContent] = []
        for source in response.sources:
            sources.append(
                DocumentContent(
                    title=source.name,
                    url=source.url,
                    public_url=source.url,
                    snippet=source.snippet,
                    mime_type="text/html",
                )
            )

        return SearchResultContent(
            answer=response.answer,
            sources=sources,
        )

    @override
    async def _search_structured(
        self,
        search_job: SearchJob,
        schema: type[BaseModelTypeVar],
    ) -> dict[str, Any]:
        job_params = search_job.job_params
        search_setting = job_params.search_setting

        depth_value = SearchDepth(self.inference_model.model_id.rsplit("/", 1)[-1])
        try:
            response = await self._linkup_client.async_search(
                query=search_job.query,
                depth=depth_value,  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]
                output_type="structured",
                structured_output_schema=schema,
                include_images=search_setting.include_images,
                max_results=search_setting.max_results,
                include_domains=job_params.include_domains,
                exclude_domains=job_params.exclude_domains,
                from_date=self._parse_date(job_params.from_date),
                to_date=self._parse_date(job_params.to_date),
                include_sources=True,
            )
        except (
            LinkupAuthenticationError,
            LinkupInsufficientCreditError,
            LinkupTooManyRequestsError,
            LinkupTimeoutError,
            LinkupInvalidRequestError,
            LinkupNoResultError,
            LinkupUnknownError,
        ) as exc:
            raise self._classify_linkup_error(exc) from exc

        # Per-request cost model: costs are defined per million, so 1 request = 1_000_000
        if search_tokens_usage := search_job.job_report.search_tokens_usage:
            search_tokens_usage.nb_tokens_by_category = {TokenCategory.INPUT: 1_000_000, TokenCategory.OUTPUT: 1_000_000}

        # If response is a Pydantic model, convert to dict
        if hasattr(response, "model_dump"):
            result: dict[str, Any] = response.model_dump()
            return result
        return dict(response)  # type: ignore[arg-type]
