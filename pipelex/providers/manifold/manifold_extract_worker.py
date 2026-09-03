"""Document extraction over the Pipelex Manifold service's own route.

Thin on purpose. The gateway's ``POST /v1/pipelex/extract`` answers in the runtime's *own* model —
an ``ExtractOutput`` of ``Page``s, keyed by page index — so the whole response side is one
``model_validate``, whichever provider the gateway picked. That is the largest deletion the native
route buys over the chat costume, where each provider's wire shape needed its own parser.

Two things this worker does that a thinner one would get wrong.

**It builds the request body field by field.** Several ``ExtractJobParams`` fields are deliberately
not part of the contract, and the gateway refuses them at *any* value including their own defaults —
so a ``model_dump()`` of the params would send ``should_caption_images=false`` and be refused. See
``manifold_schemas``.

**It translates the service's usage units into the runtime's.** The route reports honest counts
(``usage.pages``), and the runtime's cost model is per million tokens. Left untranslated the job
would report a cost of zero — silently, because ``nb_tokens_by_category`` simply stays empty and
nothing raises. The megatoken convention is inherited from the chat costume and kept deliberately:
it is what makes an extraction's cost figure directly comparable between the two dialects, which is
what the mixed-profile bring-up needs in order to mean anything.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from pydantic import ValidationError
from typing_extensions import override

from pipelex.cogt.exceptions import SdkTypeError
from pipelex.cogt.extract.exceptions import ExtractInputError
from pipelex.cogt.extract.extract_output import ExtractOutput
from pipelex.cogt.extract.extract_worker_abstract import ExtractWorkerAbstract
from pipelex.cogt.inference.error_render import InferenceErrorFamily
from pipelex.cogt.usage.token_category import NbTokensByCategoryDict, TokenCategory
from pipelex.providers.manifold.manifold_constants import MANIFOLD_EXTRACT_ROUTE
from pipelex.providers.manifold.manifold_exceptions import ManifoldExtractResponseError
from pipelex.providers.manifold.manifold_native_client import ManifoldNativeClient
from pipelex.providers.manifold.manifold_schemas import ManifoldExtractInput, ManifoldExtractParams, ManifoldExtractRequest
from pipelex.runtime_hub import get_storage_provider
from pipelex.tools.typing.pydantic_utils import format_pydantic_validation_error
from pipelex.tools.uri.uri_resolver import make_base64_url_from_any_uri

if TYPE_CHECKING:
    from pipelex.cogt.extract.extract_job import ExtractJob
    from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
    from pipelex.reporting.reporting_protocol import ReportingProtocol

# The runtime prices per million; the route counts pages. One page is one megatoken, in both
# categories, which is exactly what the chat costume reports and what the abstract worker's own
# fallback would produce — so a cost figure means the same thing on either dialect.
MANIFOLD_UNIT_TOKENS = 1_000_000


class ManifoldExtractWorker(ExtractWorkerAbstract):
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

        if not isinstance(sdk_instance, ManifoldNativeClient):
            msg = f"Provided extraction sdk_instance for {self.__class__.__name__} is not a ManifoldNativeClient: it's a '{type(sdk_instance)}'"
            raise SdkTypeError(msg)

        self.client: ManifoldNativeClient = sdk_instance

    @override
    async def _extract_pages(
        self,
        extract_job: ExtractJob,
    ) -> ExtractOutput:
        request = await self._make_request(extract_job=extract_job)
        response_body = await self.client.post_json(
            route=MANIFOLD_EXTRACT_ROUTE,
            body=request.model_dump(exclude_none=True),
            family=InferenceErrorFamily.EXTRACT,
            inference_model=self.inference_model,
        )
        self._record_usage(response_body=response_body, extract_job=extract_job)
        try:
            return ExtractOutput.model_validate(response_body)
        except ValidationError as exc:
            msg = f"Could not parse the extraction response for model '{self.inference_model.name}': {format_pydantic_validation_error(exc)}"
            raise ManifoldExtractResponseError(msg) from exc

    async def _make_request(self, *, extract_job: ExtractJob) -> ManifoldExtractRequest:
        """The body, with the input in the form the picked provider can actually reach.

        Which form that is follows from what the *catalog* says the model takes, not from a list of
        model names kept in step by hand: a web-page extractor is handed the page's own URL, and
        everything else is handed the bytes inline. The gateway fetches ``https:`` and reads
        ``data:``, and nothing else — a local path or a ``pipelex-storage://`` URI has to become
        bytes on this side, because the gateway holds no credentials for our storage.
        """
        extract_input = extract_job.extract_input
        job_params = extract_job.job_params
        params = ManifoldExtractParams(
            max_nb_images=job_params.max_nb_images,
            render_js=job_params.render_js,
            include_raw_html=job_params.include_raw_html,
        )

        if self.is_web_page_supported:
            if not extract_input.document_uri:
                msg = f"Extract model '{self.inference_model.name}' fetches web pages and needs a document_uri"
                raise ExtractInputError(msg)
            return ManifoldExtractRequest(
                model=self.inference_model.model_id,
                input=ManifoldExtractInput(document_uri=extract_input.document_uri),
                params=params,
            )

        storage = get_storage_provider()
        if image_uri := extract_input.image_uri:
            base64_url = await make_base64_url_from_any_uri(uri=image_uri, storage_provider=storage)
            return ManifoldExtractRequest(
                model=self.inference_model.model_id,
                input=ManifoldExtractInput(image_uri=base64_url),
                params=params,
            )
        if document_uri := extract_input.document_uri:
            base64_url = await make_base64_url_from_any_uri(uri=document_uri, storage_provider=storage)
            return ManifoldExtractRequest(
                model=self.inference_model.model_id,
                input=ManifoldExtractInput(document_uri=base64_url),
                params=params,
            )
        msg = "No image nor document URI provided in ExtractJob"
        raise ExtractInputError(msg)

    def _record_usage(self, *, response_body: dict[str, Any], extract_job: ExtractJob) -> None:
        extract_tokens_usage = extract_job.job_report.extract_tokens_usage
        if not extract_tokens_usage:
            return
        usage: object = response_body.get("usage")
        if not isinstance(usage, dict):
            return
        nb_pages: object = cast("dict[str, Any]", usage).get("pages")
        if not isinstance(nb_pages, int):
            return
        nb_tokens: NbTokensByCategoryDict = {
            TokenCategory.INPUT: nb_pages * MANIFOLD_UNIT_TOKENS,
            TokenCategory.OUTPUT: nb_pages * MANIFOLD_UNIT_TOKENS,
        }
        extract_tokens_usage.nb_tokens_by_category = nb_tokens
