"""Web search over the Pipelex Manifold service's own route.

Thin, like its extraction sibling, and for the same reason: ``POST /v1/pipelex/search`` answers with
the search itself rather than with a chat completion whose message content is a JSON string that has
to be decoded before it means anything.

**No ``depth`` on the wire.** The model id carries it — ``linkup/standard`` versus ``linkup/deep`` —
and a second source for a decision the gateway takes from one place is a source of disagreement, not
of flexibility.

**Usage arrives as searches and has to become tokens.** See ``manifold_extract_worker`` for the
whole of that reasoning; the failure it prevents is a cost of zero reported with no error at all.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from typing_extensions import override

from pipelex.cogt.exceptions import InferenceErrorCategory, SdkTypeError
from pipelex.cogt.inference.error_classification import UserAction, UserActionKind
from pipelex.cogt.inference.error_render import InferenceErrorFamily
from pipelex.cogt.search.search_worker_abstract import SearchWorkerAbstract
from pipelex.cogt.search.structured_search_payload import extract_structured_search_payload
from pipelex.cogt.usage.token_category import NbTokensByCategoryDict, TokenCategory
from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.core.stuffs.search_result_content import SearchResultContent
from pipelex.providers.manifold.manifold_constants import MANIFOLD_SEARCH_ROUTE
from pipelex.providers.manifold.manifold_exceptions import ManifoldSearchEmptyResultError, ManifoldSearchResponseError
from pipelex.providers.manifold.manifold_extract_worker import MANIFOLD_UNIT_TOKENS
from pipelex.providers.manifold.manifold_native_client import ManifoldNativeClient
from pipelex.providers.manifold.manifold_schemas import ManifoldSearchRequest

if TYPE_CHECKING:
    from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
    from pipelex.cogt.search.search_job import SearchJob
    from pipelex.reporting.reporting_protocol import ReportingProtocol
    from pipelex.tools.typing.pydantic_utils import BaseModelTypeVar


class ManifoldSearchWorker(SearchWorkerAbstract):
    def __init__(
        self,
        sdk_instance: Any,
        inference_model: InferenceModelSpec,
        reporting_delegate: ReportingProtocol | None = None,
    ):
        super().__init__(inference_model=inference_model, reporting_delegate=reporting_delegate)

        if not isinstance(sdk_instance, ManifoldNativeClient):
            msg = f"Provided search sdk_instance for {self.__class__.__name__} is not a ManifoldNativeClient: it's a '{type(sdk_instance)}'"
            raise SdkTypeError(msg)

        self.client: ManifoldNativeClient = sdk_instance

    @override
    async def _search_sourced_answer(
        self,
        search_job: SearchJob,
    ) -> SearchResultContent:
        response_body = await self._call_search(search_job=search_job, output_schema=None)

        answer: Any = response_body.get("answer")
        if not isinstance(answer, str):
            msg = f"The search response for model '{self.inference_model.name}' carries no answer"
            raise ManifoldSearchResponseError(
                msg,
                error_category=InferenceErrorCategory.UNKNOWN,
                user_action=UserAction(
                    kind=UserActionKind.CHANGE_MODEL,
                    detail="The gateway returned a malformed search response — try a different model",
                ),
                provider_metadata=None,
            )

        raw_sources: Any = response_body.get("sources") or []
        sources = [
            DocumentContent(
                title=source["name"],
                url=source["url"],
                public_url=source["url"],
                snippet=source["snippet"],
                mime_type="text/html",
            )
            for source in cast("list[dict[str, Any]]", raw_sources)
        ]

        return SearchResultContent(answer=answer, sources=sources)

    @override
    async def _search_structured(
        self,
        search_job: SearchJob,
        *,
        schema: type[BaseModelTypeVar],
    ) -> dict[str, Any]:
        response_body = await self._call_search(search_job=search_job, output_schema=schema.model_json_schema())

        # The route answers with a `{data, sources}` envelope, and the contract of a structured
        # search is the payload alone — it is validated against the caller's output structure class,
        # which has nowhere to put sources. The envelope is recognised *structurally* rather than
        # demanded, so the day the gateway stops asking for sources this worker keeps working on the
        # bare payload it then returns.
        #
        # `usage` is dropped first, and that line is load-bearing. On this route usage sits *beside*
        # the envelope rather than inside a chat completion the way the costume put it, and the
        # recognition is by the key set being exactly {data, sources} — so leaving a third key there
        # makes the whole response look like the payload, which then validates against an output
        # class whose fields have defaults and returns an all-defaults object with no error
        # anywhere. Usage has already been recorded by the time this runs.
        envelope = {key: value for key, value in response_body.items() if key != "usage"}
        payload = extract_structured_search_payload(response=envelope, schema=schema)
        if payload is not None:
            return payload
        # The response was an object but carried no structured payload: the search ran and found
        # nothing to fill the output structure with. That is the query's fault, not the model's.
        msg = f"The structured search for model '{self.inference_model.name}' returned an empty structured result"
        raise ManifoldSearchEmptyResultError(
            msg,
            error_category=InferenceErrorCategory.UNKNOWN,
            user_action=UserAction(
                kind=UserActionKind.CHANGE_INPUT,
                detail="The search found nothing to fill your output structure — try a broader query or a wider date range",
            ),
            provider_metadata=None,
        )

    async def _call_search(self, *, search_job: SearchJob, output_schema: dict[str, Any] | None) -> dict[str, Any]:
        job_params = search_job.job_params
        search_setting = job_params.search_setting
        request = ManifoldSearchRequest(
            model=self.inference_model.model_id,
            query=search_job.query,
            include_images=search_setting.include_images,
            include_inline_citations=search_setting.include_inline_citations,
            max_results=search_setting.max_results,
            include_domains=job_params.include_domains,
            exclude_domains=job_params.exclude_domains,
            from_date=job_params.from_date,
            to_date=job_params.to_date,
            output_schema=output_schema,
        )
        response_body = await self.client.post_json(
            route=MANIFOLD_SEARCH_ROUTE,
            body=request.model_dump(exclude_none=True),
            family=InferenceErrorFamily.SEARCH,
            inference_model=self.inference_model,
        )
        self._record_usage(response_body=response_body, search_job=search_job)
        return response_body

    def _record_usage(self, *, response_body: dict[str, Any], search_job: SearchJob) -> None:
        search_tokens_usage = search_job.job_report.search_tokens_usage
        if not search_tokens_usage:
            return
        usage: object = response_body.get("usage")
        if not isinstance(usage, dict):
            return
        nb_searches: object = cast("dict[str, Any]", usage).get("searches")
        if not isinstance(nb_searches, int):
            return
        nb_tokens: NbTokensByCategoryDict = {
            TokenCategory.INPUT: nb_searches * MANIFOLD_UNIT_TOKENS,
            TokenCategory.OUTPUT: nb_searches * MANIFOLD_UNIT_TOKENS,
        }
        search_tokens_usage.nb_tokens_by_category = nb_tokens
