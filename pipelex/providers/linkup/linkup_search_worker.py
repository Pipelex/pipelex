import html
import json
import re
from datetime import date
from html.entities import html5
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

from pipelex.cogt.exceptions import InferenceErrorCategory
from pipelex.cogt.inference.error_classification import UserAction, UserActionKind, extract_linkup_metadata
from pipelex.cogt.inference.error_classify import InferenceErrorFamily, classify_inference_error
from pipelex.cogt.inference.error_render import render_inference_error
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.search.search_depth import SearchDepth
from pipelex.cogt.search.search_job import SearchJob
from pipelex.cogt.search.search_worker_abstract import SearchWorkerAbstract
from pipelex.cogt.search.structured_search_payload import extract_structured_search_payload
from pipelex.cogt.usage.pricing_unit import PricingUnit
from pipelex.cogt.usage.usage_cost import record_unit_priced_usage
from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.core.stuffs.search_result_content import SearchResultContent
from pipelex.providers.linkup.linkup_exceptions import LinkupSearchEmptyResultError, LinkupSearchResponseError
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.tools.typing.pydantic_utils import BaseModelTypeVar

# A complete HTML character reference, ending in `;`: named (`&amp;`), decimal (`&#39;`) or hexadecimal (`&#x27;`)
_CHARACTER_REFERENCE = re.compile(r"&(?:[A-Za-z][A-Za-z0-9]*|#[0-9]+|#[xX][0-9A-Fa-f]+);")
_NO_BREAK_SPACE = "\u00a0"


def _decoded_character_reference(match: re.Match[str]) -> str:  # kw-only: ignore — ``re.sub`` calls its replacement positionally
    reference = match.group(0)
    if reference.startswith("&#") or reference[1:] in html5:
        return html.unescape(reference)
    # A name HTML does not define is left as written: `html.unescape` would decode its longest legacy prefix,
    # turning `&notable;` into `¬able;`.
    return reference


def _plain_text_title(*, name: str) -> str:
    """Decode, once, the HTML character references Linkup can leave in a source's name, into the plain text consumers draw.

    Only a complete reference is decoded, one ending in `;`. `html.unescape` on the whole name would also apply HTML's
    legacy rules for a reference written without its `;`, turning a title such as `Health &notable` into `Health ¬able`
    and `R&D &copy editing` into `R&D © editing`. A no-break space, which `&nbsp;` decodes to, becomes an ordinary space.
    """
    return _CHARACTER_REFERENCE.sub(_decoded_character_reference, name).replace(_NO_BREAK_SPACE, " ")


class LinkupSearchWorker(SearchWorkerAbstract):
    def __init__(
        self,
        inference_model: InferenceModelSpec,
        api_key: str,
        reporting_delegate: ReportingProtocol | None = None,
    ) -> None:
        SearchWorkerAbstract.__init__(self, inference_model=inference_model, reporting_delegate=reporting_delegate)
        self._linkup_client = LinkupClient(api_key=api_key)

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
        ) as sdk_exc:
            metadata = extract_linkup_metadata(sdk_exc)
            classification = classify_inference_error(metadata, family=InferenceErrorFamily.SEARCH)
            raise render_inference_error(
                metadata=metadata,
                classification=classification,
                family=InferenceErrorFamily.SEARCH,
                model_desc=self.inference_model.desc,
                model_handle=self.inference_model.name,
            ) from sdk_exc

        # Linkup bills by the request, which the usage records as one request priced at the model's rate
        if search_tokens_usage := search_job.job_report.search_tokens_usage:
            record_unit_priced_usage(tokens_usage=search_tokens_usage, pricing_unit=PricingUnit.REQUEST, nb_units=1)

        sources: list[DocumentContent] = []
        for source in response.sources:
            sources.append(
                DocumentContent(
                    # Linkup can hand a source's name over with the HTML character references of the page it
                    # was read from still encoded (`Requirements &amp; SAP Integration`), so it is decoded into
                    # plain text. The snippet is the page's extracted text, in which no reference has been seen,
                    # so it is left as sent: decoding it would turn a reference the page itself quotes, as an
                    # HTML tutorial does, into the character it names.
                    title=_plain_text_title(name=source.name),
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
        *,
        schema: type[BaseModelTypeVar],
    ) -> dict[str, Any]:
        job_params = search_job.job_params
        search_setting = job_params.search_setting

        # The schema crosses as a JSON string, which is byte-for-byte what the SDK puts on the wire when
        # handed the class itself. Handing it the class would *also* make it instantiate that class from
        # the response — running the caller's validators inside the SDK, and then again when the leaf
        # validates the dict this returns. Serializing the schema here keeps the response raw and the
        # validation single, at the leaf, where the run mode and the fidelity contract live.
        schema_json = json.dumps(schema.model_json_schema())

        depth_value = SearchDepth(self.inference_model.model_id.rsplit("/", 1)[-1])
        try:
            response = await self._linkup_client.async_search(
                query=search_job.query,
                depth=depth_value,  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]
                output_type="structured",
                structured_output_schema=schema_json,
                include_images=search_setting.include_images,
                max_results=search_setting.max_results,
                include_domains=job_params.include_domains,
                exclude_domains=job_params.exclude_domains,
                from_date=self._parse_date(job_params.from_date),
                to_date=self._parse_date(job_params.to_date),
                include_sources=False,
            )
        except (
            LinkupAuthenticationError,
            LinkupInsufficientCreditError,
            LinkupTooManyRequestsError,
            LinkupTimeoutError,
            LinkupInvalidRequestError,
            LinkupNoResultError,
            LinkupUnknownError,
        ) as sdk_exc:
            metadata = extract_linkup_metadata(sdk_exc)
            classification = classify_inference_error(metadata, family=InferenceErrorFamily.SEARCH)
            raise render_inference_error(
                metadata=metadata,
                classification=classification,
                family=InferenceErrorFamily.SEARCH,
                model_desc=self.inference_model.desc,
                model_handle=self.inference_model.name,
            ) from sdk_exc

        # Linkup bills by the request, which the usage records as one request priced at the model's rate
        if search_tokens_usage := search_job.job_report.search_tokens_usage:
            record_unit_priced_usage(tokens_usage=search_tokens_usage, pricing_unit=PricingUnit.REQUEST, nb_units=1)

        # The contract of a structured search is the structured payload itself — it is validated against
        # the caller's output structure class, which has nowhere to put sources. Asking for them wraps the
        # payload in a {data, sources} envelope no output class could accept, so this asks for the payload
        # alone — but it does not *trust* that flag. A provider that ignored it would hand back the
        # envelope, and an output structure whose fields all carry defaults validates that envelope
        # *silently* into an all-defaults object (pydantic's default `extra="ignore"` drops both keys), so
        # the failure would be wrong answers rather than an error. The extractor recognises the envelope
        # structurally instead, which is also what lets both backends share one rule.
        # The schema crossed as a string, so the SDK did no validation of its own: `response` is the
        # provider's JSON verbatim, typed `Any`.
        payload = extract_structured_search_payload(response=response, schema=schema)
        if payload is not None:
            return payload
        if isinstance(response, dict):
            # The envelope was there but carried no object payload: the search ran and found nothing to
            # fill the output structure with. That is the query's fault, not the model's — advising a
            # model change here would send the user after the wrong thing.
            msg = "Linkup structured search returned an empty structured result"
            raise LinkupSearchEmptyResultError(
                msg,
                error_category=InferenceErrorCategory.UNKNOWN,
                user_action=UserAction(
                    kind=UserActionKind.CHANGE_INPUT,
                    detail="The search found nothing to fill your output structure — try a broader query or a wider date range",
                ),
                provider_metadata=None,
            )
        msg = f"Linkup structured search returned a non-object payload of type '{type(response).__name__}'"
        raise LinkupSearchResponseError(
            msg,
            error_category=InferenceErrorCategory.UNKNOWN,
            user_action=UserAction(
                kind=UserActionKind.CHANGE_MODEL,
                detail="Linkup returned a malformed structured search response — try a different model",
            ),
            provider_metadata=None,
        )
