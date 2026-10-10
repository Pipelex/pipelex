"""The one event an inference call ends with, whichever way it ends: what a dashboard of inference is built from.

Every worker base wraps the call its public method makes in an ``InferenceCallSummary``, the LLM, image-generation,
extraction, search, judgment and document-generation bases alike, so a provider's worker and a plugin's, which
subclass those bases and implement only the provider half, end every call with the event and log nothing for it
themselves. The block starts before the checks that may refuse the call, so a refused call ends with the event too.
The event is logged once, when the call returns or raises, at INFO, under the fixed message ``Inference call ends``,
so a log store selects every call by that message and groups them by its fields.

The fields are the call's dimensions. ``gen_ai.operation.name`` is the operation, OpenTelemetry's name where its
semantic conventions define one (``chat`` for an LLM call) and the inference family's own name otherwise. The model
rides under the ``gen_ai.*`` keys with the meaning Pipelex's LLM span gives them, the handle requested under
``gen_ai.request.model`` and the provider's id of the model serving it under ``gen_ai.response.model``, beside
``model_handle``, ``backend_name`` and ``sdk``. A handle names one model per model type, so a query groups by the
operation and the model together. Then the tokens in and out, the cost in US dollars, the duration in milliseconds
and the outcome, with ``error.type`` on failure, and ``cancelled`` for a call stopped from outside.

The usage is the one the call recorded on its job report, the ``*TokensUsage`` object the base hands to
``ReportingProtocol.report_inference_job`` when it reports the job, priced with ``compute_tokens_usage_cost``, the
cost engine the client-facing usage records and the run graph read, so a usage gets the same price on the event and
in the cost report. The event reads it whether or not the job was reported: a failure the provider billed carries the
cost it recorded even where the base reports only a success, so the event may price a call the cost report never
sees. A token count or a cost the call did not record is left off the event, never written as zero: a family that
reports no usage, document generation, carries neither, and a call that failed before the provider answered recorded
none. A usage billed by the request or by the page, a Linkup search or fetch, or an extraction whose provider reports
no usage and is priced by its pages, records each unit as a million tokens in and out so the rate table prices one,
and says so in its ``pricing_unit``: that call carries its cost and no token counts, since a request or a page is not
a token.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Any

from typing_extensions import override

from pipelex import log
from pipelex.cogt.usage.token_category import TokenCategory
from pipelex.cogt.usage.usage_cost import compute_tokens_usage_cost
from pipelex.system.telemetry.otel_constants import GenAISpanAttr
from pipelex.tools.log.console_layouts import LogLayout
from pipelex.tools.log.summary_event import SummaryEvent
from pipelex.tools.log.summary_fields import COST_USD_FIELD

if TYPE_CHECKING:
    from collections.abc import Callable

    from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
    from pipelex.cogt.usage.usage_cost import TokensUsage

#: The message every inference call ends with; the call is in the fields.
INFERENCE_CALL_ENDS_MESSAGE = "Inference call ends"


class InferenceOperation(StrEnum):
    """The values of ``gen_ai.operation.name`` on the event an inference call ends with.

    OpenTelemetry's operation name where its GenAI conventions define one for the call, and the inference family's
    own name otherwise. An LLM call is a chat completion. The conventions name no operation for generating an image
    outside a multimodal chat, for reading a document's text, for a search that answers with its sources, for a
    judgment or for printing a document, and their ``retrieval`` is a search of a vector store, so those take the
    family's name.
    """

    CHAT = "chat"
    IMG_GEN = "img_gen"
    EXTRACT = "extract"
    SEARCH = "search"
    JUDGMENT = "judgment"
    DOC_GEN = "doc_gen"


class InferenceCallSummary(SummaryEvent):
    """Times one inference call and logs the event it ends with, once, when it ends, however it ends.

    A context manager around the call, the checks that may refuse it included: entering it starts the clock, and
    leaving it logs the event, the outcome read off the exception leaving the block, if any, with ``cancelled`` for a
    call stopped from outside. It never handles that exception, which goes on as it came, and a failure to build or log
    the event is logged as a warning in its place, never raised. A worker base whose call runs under a span enters
    ``ends_here`` around the block the span is active in, so the event is logged inside it.

    Args:
        operation: The call's operation, ``gen_ai.operation.name``.
        inference_model: The model the worker calls.
        read_tokens_usage: Reads the usage the call recorded, from the job report the worker hands to the reporting
            path, when the call ends; ``None`` for a family that reports no usage.
        request_model: ``gen_ai.request.model``, the model's handle unless the worker names it otherwise.
        response_model: ``gen_ai.response.model``, the provider's id of the model unless the worker names it otherwise.
    """

    def __init__(
        self,
        *,
        operation: InferenceOperation,
        inference_model: InferenceModelSpec,
        read_tokens_usage: Callable[[], TokensUsage | None] | None,
        request_model: str | None = None,
        response_model: str | None = None,
    ) -> None:
        super().__init__(message=INFERENCE_CALL_ENDS_MESSAGE)
        self._operation = operation
        self._inference_model = inference_model
        self._read_tokens_usage = read_tokens_usage
        self._request_model = request_model or inference_model.name
        self._response_model = response_model or inference_model.model_id

    @override
    def _work_fields(self) -> dict[str, Any]:
        """The call's operation, its model under every key that names it, and the usage it recorded."""
        return {
            GenAISpanAttr.OPERATION_NAME: self._operation,
            "model_handle": self._inference_model.name,
            "backend_name": self._inference_model.backend_name,
            "sdk": self._inference_model.sdk,
            GenAISpanAttr.REQUEST_MODEL: self._request_model,
            GenAISpanAttr.RESPONSE_MODEL: self._response_model,
            **self._usage_fields(),
        }

    @override
    def _log_event(self, *, fields: dict[str, Any]) -> None:
        log.info(INFERENCE_CALL_ENDS_MESSAGE, fields=fields, layout=LogLayout.INFERENCE_CALL_END)

    def _usage_fields(self) -> dict[str, Any]:
        """The tokens in and out and the cost the call recorded, each left out when it recorded none.

        A usage priced by the request or by the page counts units, not tokens, so it gives its cost and no counts.
        """
        tokens_usage = self._read_tokens_usage() if self._read_tokens_usage is not None else None
        if tokens_usage is None or not tokens_usage.nb_tokens_by_category:
            return {}
        nb_tokens_by_category = tokens_usage.nb_tokens_by_category
        usage_fields: dict[str, Any] = {}
        if tokens_usage.pricing_unit.counts_tokens:
            if TokenCategory.INPUT in nb_tokens_by_category:
                usage_fields[GenAISpanAttr.USAGE_INPUT_TOKENS] = nb_tokens_by_category[TokenCategory.INPUT]
            if TokenCategory.OUTPUT in nb_tokens_by_category:
                usage_fields[GenAISpanAttr.USAGE_OUTPUT_TOKENS] = nb_tokens_by_category[TokenCategory.OUTPUT]
        cost = compute_tokens_usage_cost(tokens_usage)
        if cost is not None:
            usage_fields[COST_USD_FIELD] = cost
        return usage_fields
