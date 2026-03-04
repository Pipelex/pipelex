import json
from typing import Any, cast

from portkey_ai import AsyncPortkey
from portkey_ai.api_resources import exceptions as portkey_exceptions
from portkey_ai.api_resources.utils import GenericResponse
from tenacity import AsyncRetrying, RetryCallState, retry_if_exception, stop_after_attempt, wait_random_exponential
from typing_extensions import override

from pipelex import log
from pipelex.cogt.exceptions import SdkTypeError
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.search.search_depth import SearchDepth
from pipelex.cogt.search.search_job import SearchJob
from pipelex.cogt.search.search_job_factory import SearchJobFactory
from pipelex.cogt.search.search_setting import SearchSetting
from pipelex.cogt.search.search_worker_abstract import SearchWorkerAbstract
from pipelex.cogt.usage.token_category import NbTokensByCategoryDict, TokenCategory
from pipelex.config import get_config
from pipelex.core.stuffs.search_result_content import SearchResultContent, SearchSourceContent
from pipelex.pipeline.job_metadata import JobMetadata, UnitJobId
from pipelex.plugins.gateway.gateway_deck import GatewayDeck
from pipelex.plugins.gateway.gateway_exceptions import GatewaySearchResponseError
from pipelex.plugins.gateway.gateway_factory import GatewayFactory
from pipelex.plugins.gateway.gateway_search_schemas import GatewaySearchRequestParams
from pipelex.reporting.reporting_protocol import ReportingProtocol


class GatewaySearchWorker(SearchWorkerAbstract):
    """Search worker that routes through Portkey to the pipelex-relay LinkUp endpoints."""

    def __init__(
        self,
        sdk_instance: Any,
        inference_model: InferenceModelSpec,
        reporting_delegate: ReportingProtocol | None = None,
    ):
        super().__init__(reporting_delegate=reporting_delegate)

        if not isinstance(sdk_instance, AsyncPortkey):
            msg = f"Provided sdk_instance for {self.__class__.__name__} is not of type AsyncPortkey: it's a '{type(sdk_instance)}'"
            raise SdkTypeError(msg)

        self.portkey_client: AsyncPortkey = sdk_instance
        self.inference_model = inference_model
        self._tenacity_config = get_config().cogt.tenacity_config

    def _make_retryer(self) -> AsyncRetrying:
        """Create a fresh AsyncRetrying instance for each call."""
        return AsyncRetrying(
            retry=retry_if_exception(self._is_retryable_portkey_error),
            before_sleep=self._log_retry,
            wait=wait_random_exponential(
                multiplier=self._tenacity_config.wait_multiplier,
                max=self._tenacity_config.wait_max,
                exp_base=self._tenacity_config.wait_exp_base,
            ),
            reraise=True,
            stop=stop_after_attempt(self._tenacity_config.max_retries),
        )

    @override
    async def search_sourced_answer(
        self,
        query: str,
        search_setting: SearchSetting,
        job_metadata: JobMetadata,
        include_domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> SearchResultContent:
        job_metadata.unit_job_id = UnitJobId.SEARCH_SOURCED_ANSWER
        search_job = SearchJobFactory.make_search_job(job_metadata=job_metadata)
        search_job.search_job_before_start(inference_model=self.inference_model)

        params = GatewaySearchRequestParams(
            query=query,
            depth=SearchDepth(self.inference_model.model_id.rsplit("/", 1)[-1]),
            include_images=search_setting.include_images,
            include_inline_citations=search_setting.include_inline_citations,
            max_results=search_setting.max_results,
            include_domains=include_domains,
            exclude_domains=exclude_domains,
            from_date=from_date,
            to_date=to_date,
        )

        response = await self._call_relay(
            model=self.inference_model.model_id,
            content=params.model_dump_json(),
        )

        self._extract_usage(response=response, search_job=search_job)
        search_job.search_job_after_complete()
        if self.reporting_delegate:
            self.reporting_delegate.report_inference_job(inference_job=search_job)

        content_str = self._extract_content(response)
        result_dict: dict[str, Any] = json.loads(content_str)

        sources = [
            SearchSourceContent(
                name=source["name"],
                url=source["url"],
                snippet=source["snippet"],
            )
            for source in result_dict.get("sources", [])
        ]

        return SearchResultContent(
            answer=result_dict["answer"],
            sources=sources,
        )

    @override
    async def search_structured(
        self,
        query: str,
        search_setting: SearchSetting,
        output_schema: type,
        job_metadata: JobMetadata,
        include_domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> dict[str, Any]:
        job_metadata.unit_job_id = UnitJobId.SEARCH_STRUCTURED
        search_job = SearchJobFactory.make_search_job(job_metadata=job_metadata)
        search_job.search_job_before_start(inference_model=self.inference_model)

        # Convert Pydantic model class to JSON Schema dict for the relay
        schema_dict: dict[str, Any]
        if hasattr(output_schema, "model_json_schema"):
            schema_dict = cast("dict[str, Any]", output_schema.model_json_schema())  # pyright: ignore[reportUnknownMemberType]
        else:
            msg = f"output_schema must be a Pydantic model class with model_json_schema(), got {output_schema}"
            raise SdkTypeError(msg)

        params = GatewaySearchRequestParams(
            query=query,
            depth=SearchDepth(self.inference_model.model_id.rsplit("/", 1)[-1]),
            include_images=search_setting.include_images,
            include_inline_citations=search_setting.include_inline_citations,
            max_results=search_setting.max_results,
            include_domains=include_domains,
            exclude_domains=exclude_domains,
            from_date=from_date,
            to_date=to_date,
            output_schema=schema_dict,
        )

        response = await self._call_relay(
            model=self.inference_model.model_id,
            content=params.model_dump_json(),
        )

        self._extract_usage(response=response, search_job=search_job)
        search_job.search_job_after_complete()
        if self.reporting_delegate:
            self.reporting_delegate.report_inference_job(inference_job=search_job)

        content_str = self._extract_content(response)
        result: dict[str, Any] = json.loads(content_str)
        return result

    def _extract_usage(self, response: GenericResponse, search_job: SearchJob) -> None:
        """Extract token usage from the GenericResponse and populate the search job report."""
        response_dict: dict[str, Any] = response.model_dump(serialize_as_any=True)
        search_tokens_usage = search_job.job_report.search_tokens_usage
        if (usage_dict := response_dict.get("usage")) and search_tokens_usage:
            nb_tokens: NbTokensByCategoryDict = {}
            if input_tokens := usage_dict.get("prompt_tokens") or usage_dict.get("input_tokens"):
                nb_tokens[TokenCategory.INPUT] = input_tokens
            if output_tokens := usage_dict.get("completion_tokens") or usage_dict.get("output_tokens"):
                nb_tokens[TokenCategory.OUTPUT] = output_tokens
            search_tokens_usage.nb_tokens_by_category = nb_tokens

    async def _call_relay(self, model: str, content: str) -> GenericResponse:
        """Send a request through Portkey to the relay.

        Args:
            model: The relay model identifier (e.g., "linkup-sourced-answer")
            content: JSON-encoded request parameters

        Returns:
            The Portkey GenericResponse
        """
        config_id = GatewayDeck.get_config_id(headers=self.inference_model.extra_headers or {})
        log.dev(f"Search via gateway config '{config_id}' with model '{model}'")

        messages: list[dict[str, str]] = [{"role": "user", "content": content}]

        attempt_number = 0
        response: GenericResponse | None = None
        retryer = self._make_retryer()
        try:
            async for attempt in retryer:
                with attempt:
                    attempt_number += 1
                    response = await self.portkey_client.with_options(config=config_id).post(  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
                        "/chat/completions",
                        model=model,
                        messages=messages,
                    )
        except portkey_exceptions.APIError as exc:
            error_summary = GatewayFactory.make_error_summary_from_portkey_error(exc)
            msg = f"Search service error for model '{model}' after {attempt_number} attempt(s): {error_summary}"
            raise GatewaySearchResponseError(msg) from exc

        if response is None:
            msg = f"Could not get a response for model '{model}' via Portkey after {attempt_number} attempts"
            raise GatewaySearchResponseError(msg)

        if not isinstance(response, GenericResponse):
            msg = "Response is not of type GenericResponse"
            raise TypeError(msg)

        return response

    def _extract_content(self, response: GenericResponse) -> str:
        """Extract the content string from a GenericResponse.

        GenericResponse uses Pydantic's extra="allow", so `choices` is a raw
        list[dict] rather than a list of typed objects — use dict access.
        """
        try:
            choice: dict[str, Any] = response.choices[0]  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
            content = cast("object", choice["message"]["content"])
            if not isinstance(content, str):
                msg = f"Expected string content in response, got {type(content)}"
                raise GatewaySearchResponseError(msg)
            return content
        except (KeyError, IndexError, TypeError) as exc:
            msg = "Could not extract content from gateway search response"
            raise GatewaySearchResponseError(msg) from exc

    def _is_retryable_portkey_error(self, exc: BaseException) -> bool:
        if isinstance(exc, portkey_exceptions.NotFoundError):
            msg = str(exc).lower()
            return "specified deployment could not be found" in msg
        return False

    def _log_retry(self, retry_state: RetryCallState) -> None:
        """Called before sleeping between retries."""
        if not retry_state.outcome:
            log.error("Tenacity retry state outcome is None")
            return
        exc = retry_state.outcome.exception()
        attempt = retry_state.attempt_number
        wait_duration = retry_state.next_action.sleep if retry_state.next_action else 0.0
        log.dev(f"{self.__class__.__name__} retry #{attempt} for search due to '{type(exc).__name__}'.")
        log.verbose(f"Wait duration before next attempt: {wait_duration:.4f}s")
