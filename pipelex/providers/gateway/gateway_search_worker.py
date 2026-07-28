import json
from typing import Any, cast

from portkey_ai import AsyncPortkey
from portkey_ai.api_resources import exceptions as portkey_exceptions
from portkey_ai.api_resources.utils import GenericResponse
from typing_extensions import override

from pipelex import log
from pipelex.cogt.exceptions import InferenceErrorCategory, SdkTypeError
from pipelex.cogt.inference.error_classification import UserAction, UserActionKind, extract_gateway_metadata
from pipelex.cogt.inference.error_classify import classify_inference_error
from pipelex.cogt.inference.error_render import InferenceErrorFamily, render_inference_error
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.search.search_depth import SearchDepth
from pipelex.cogt.search.search_job import SearchJob
from pipelex.cogt.search.search_worker_abstract import SearchWorkerAbstract
from pipelex.cogt.usage.token_category import NbTokensByCategoryDict, TokenCategory
from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.core.stuffs.search_result_content import SearchResultContent
from pipelex.providers.gateway.gateway_deck import GatewayDeck
from pipelex.providers.gateway.gateway_exceptions import GatewaySearchResponseError
from pipelex.providers.gateway.gateway_search_schemas import GatewaySearchRequestParams
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.tools.typing.pydantic_utils import BaseModelTypeVar


class GatewaySearchWorker(SearchWorkerAbstract):
    """Search worker that routes through Portkey to the pipelex-relay LinkUp endpoints."""

    def __init__(
        self,
        sdk_instance: Any,
        inference_model: InferenceModelSpec,
        reporting_delegate: ReportingProtocol | None = None,
    ):
        super().__init__(inference_model=inference_model, reporting_delegate=reporting_delegate)

        if not isinstance(sdk_instance, AsyncPortkey):
            msg = f"Provided sdk_instance for {self.__class__.__name__} is not of type AsyncPortkey: it's a '{type(sdk_instance)}'"
            raise SdkTypeError(msg)

        self.portkey_client: AsyncPortkey = sdk_instance

    @override
    async def _search_sourced_answer(
        self,
        search_job: SearchJob,
    ) -> SearchResultContent:
        job_params = search_job.job_params
        search_setting = job_params.search_setting

        params = GatewaySearchRequestParams(
            query=search_job.query,
            depth=SearchDepth(self.inference_model.model_id.rsplit("/", 1)[-1]),
            include_images=search_setting.include_images,
            include_inline_citations=search_setting.include_inline_citations,
            max_results=search_setting.max_results,
            include_domains=job_params.include_domains,
            exclude_domains=job_params.exclude_domains,
            from_date=job_params.from_date,
            to_date=job_params.to_date,
        )

        response = await self._call_relay(
            model=self.inference_model.model_id,
            content=params.model_dump_json(),
        )

        self._extract_usage(response=response, search_job=search_job)

        content_str = self._extract_content(response)
        result_dict: dict[str, Any] = json.loads(content_str)

        sources = [
            DocumentContent(
                title=source["name"],
                url=source["url"],
                public_url=source["url"],
                snippet=source["snippet"],
                mime_type="text/html",
            )
            for source in result_dict.get("sources", [])
        ]

        return SearchResultContent(
            answer=result_dict["answer"],
            sources=sources,
        )

    @override
    async def _search_structured(
        self,
        search_job: SearchJob,
        *,
        schema: type[BaseModelTypeVar],
    ) -> dict[str, Any]:
        job_params = search_job.job_params
        search_setting = job_params.search_setting

        # Convert Pydantic model class to JSON Schema dict for the relay
        schema_dict: dict[str, Any] = schema.model_json_schema()

        params = GatewaySearchRequestParams(
            query=search_job.query,
            depth=SearchDepth(self.inference_model.model_id.rsplit("/", 1)[-1]),
            include_images=search_setting.include_images,
            include_inline_citations=search_setting.include_inline_citations,
            max_results=search_setting.max_results,
            include_domains=job_params.include_domains,
            exclude_domains=job_params.exclude_domains,
            from_date=job_params.from_date,
            to_date=job_params.to_date,
            output_schema=schema_dict,
        )

        response = await self._call_relay(
            model=self.inference_model.model_id,
            content=params.model_dump_json(),
        )

        self._extract_usage(response=response, search_job=search_job)

        content_str = self._extract_content(response)
        result: dict[str, Any] = json.loads(content_str)
        return result

    def _extract_usage(self, response: GenericResponse, *, search_job: SearchJob) -> None:
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

    async def _call_relay(self, *, model: str, content: str) -> GenericResponse:
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

        try:
            response = await self.portkey_client.with_options(config=config_id).post(  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
                "/chat/completions",
                model=model,
                messages=messages,
            )
        except portkey_exceptions.APIError as sdk_exc:
            metadata = extract_gateway_metadata(sdk_exc)
            classification = classify_inference_error(metadata)
            raise render_inference_error(
                metadata=metadata,
                classification=classification,
                family=InferenceErrorFamily.SEARCH,
                model_desc=self.inference_model.desc,
                model_handle=self.inference_model.name,
            ) from sdk_exc

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
                raise GatewaySearchResponseError(
                    msg,
                    error_category=InferenceErrorCategory.UNKNOWN,
                    user_action=UserAction(
                        kind=UserActionKind.CHANGE_MODEL,
                        detail="The Gateway returned a malformed search response — try a different model",
                    ),
                    provider_metadata=None,
                )
            return content
        except (KeyError, IndexError, TypeError) as exc:
            msg = "Could not extract content from gateway search response"
            raise GatewaySearchResponseError(
                msg,
                error_category=InferenceErrorCategory.UNKNOWN,
                user_action=UserAction(
                    kind=UserActionKind.CHANGE_MODEL,
                    detail="The Gateway returned a malformed search response — try a different model",
                ),
                provider_metadata=None,
            ) from exc
