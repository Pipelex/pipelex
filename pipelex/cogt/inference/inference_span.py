"""The generation span every inference call reports under, whichever kind of inference it is.

Every worker base opens one span per call, the LLM, image-generation, extraction, search and judgment bases alike, and
the print stage of a document opens one for its engine, so a call of any kind reaches every telemetry destination: the
OpenTelemetry span is what Langfuse and every OTLP backend read, and what the PostHog span exporter maps to PostHog's
``$ai_generation``. The span follows the OpenTelemetry GenAI semantic conventions where they define an attribute, and
carries Pipelex's own beside them:

- ``gen_ai.operation.name`` is the operation, the one the call's summary event names (``chat`` for an LLM call, the
  inference family's own name otherwise), never Pipelex's unit-job id, which rides ``pipelex.unit_job_id``.
- ``gen_ai.provider.name`` is the serving provider, the Pipelex backend the call was sent to, which may differ from the
  model's maker: on the hosted plane it is the Pipelex gateway.
- ``gen_ai.request.model`` and ``gen_ai.response.model`` are the model id the call asked the backend for, the response
  model read again when the call ends, so a worker that learns from its provider which model served it names that one;
  the Pipelex handle and backend ride ``pipelex.model.handle`` and ``pipelex.inference.backend``.
- ``gen_ai.usage.*`` are the tokens the call recorded, summed over every attempt of a structured generation, and the
  ``pipelex.cost.*`` attributes price them with the model's declared rates, through the cost engine every usage report
  prices with; a usage priced by the request or by the page gives its cost and no token counts, and a model with no
  rates gives no cost.
- ``pipelex.inference.attempt_count`` says how many times the call asked the model, a structured generation's re-asks
  included.
- A failed call ends with the span's error status, the exception recorded on it, and ``error.type`` set to the failure's
  inference error category, a closed vocabulary (``transient``, ``configuration``, ``content``, ``capacity``,
  ``ambiguous``, ``unknown``), never a message. A call stopped from outside, cancelled rather than failed, ends with no
  error status, as its summary event ends ``cancelled`` rather than ``error``.

Telemetry never changes a call's outcome: a call with no tracer, no OpenTelemetry context or a tracer that records
nothing opens no span, and ending one never raises.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Self

from opentelemetry import trace
from opentelemetry.trace import NonRecordingSpan, Span, SpanContext, SpanKind, Status, StatusCode, TraceFlags

from pipelex import log
from pipelex.cogt.exceptions import InferenceErrorCategory, find_inference_error_category_in_chain
from pipelex.cogt.usage.token_category import TokenCategory
from pipelex.cogt.usage.usage_cost import compute_tokens_usage_cost_breakdown
from pipelex.system.telemetry.current_span import pipelex_span_active
from pipelex.system.telemetry.otel_constants import (
    GenAISpanAttr,
    LangfuseSpanAttr,
    OTelAttributeValue,
    PipelexSpanAttr,
    SpanCategory,
    make_otel_gen_ai_output_type,
)
from pipelex.system.telemetry.otel_factory import OtelFactory
from pipelex.system.telemetry.pipe_identity import make_run_method_span_attributes
from pipelex.system.telemetry.telemetry_identity import make_run_identity_span_attributes
from pipelex.system.telemetry.telemetry_manager_abstract import TelemetryManagerAbstract
from pipelex.tools.log.error_fields import error_fields
from pipelex.tools.misc.package_utils import get_package_version

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from contextlib import AbstractContextManager
    from types import TracebackType

    from pipelex.cogt.inference.inference_call_summary import InferenceOperation
    from pipelex.cogt.inference.inference_constants import InferenceOutputType
    from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
    from pipelex.cogt.usage.usage_cost import TokensUsage
    from pipelex.system.job_metadata import JobMetadata

#: The message of the debug line a span whose usage could not be priced writes, the span ending without it.
INFERENCE_SPAN_USAGE_FAILED_MESSAGE = "The usage of an inference call could not be recorded on its span"


def _output_description(*, output_type: InferenceOutputType | None, output_class_name: str | None) -> str:
    """What the call produces, as the span's name ends with it: the class of a structured output, else the output type.

    A call with no output type the conventions name, a document print, produces a document.
    """
    if output_class_name:
        return output_class_name
    if output_type is not None:
        return output_type
    return "Document"


def start_inference_span(
    *,
    job_metadata: JobMetadata,
    operation: InferenceOperation,
    inference_model: InferenceModelSpec,
    request_model: str,
    output_type: InferenceOutputType | None,
    output_class_name: str | None = None,
    request_attributes: Mapping[str, OTelAttributeValue] | None = None,
) -> Span | None:
    """Start the generation span of one inference call, as a child of the pipe span that made it, and return it.

    Every attribute holds its full value, the pipe code and the output class included; each PostHog exporter redacts
    them as its own configuration says.

    Args:
        job_metadata: The job's metadata, whose OpenTelemetry context names the trace and the pipe span the call is under.
        operation: The call's operation, `gen_ai.operation.name`.
        inference_model: The model serving the call.
        request_model: The model id the call asks the backend for, `gen_ai.request.model`.
        output_type: What the call produces, `gen_ai.output.type` when the conventions name it; `None` for a document print.
        output_class_name: The class of a structured output, which the span's name ends with.
        request_attributes: The request's own parameters, the GenAI conventions' `gen_ai.request.*` keys.

    Returns:
        The span, or `None` when the job carries no OpenTelemetry context, no tracer is available, or the tracer records
        nothing.
    """
    tracer = TelemetryManagerAbstract.get_instance_tracer()
    if tracer is None:
        log.verbose("No inference span was started, since no tracer is available")
        return None
    otel_context = job_metadata.otel_context
    if otel_context is None:
        log.verbose("No inference span was started, since the job carries no OpenTelemetry context")
        return None

    pipe_code = job_metadata.pipe_code
    unit_job_id = job_metadata.unit_job_id
    output_desc = _output_description(output_type=output_type, output_class_name=output_class_name)
    step_name = f"{unit_job_id or operation} ({inference_model.name}) -> {output_desc}"
    span_name = f"{pipe_code}: {step_name}" if pipe_code else step_name

    span_attributes: dict[str, OTelAttributeValue] = {
        # GenAI semantic-convention attributes
        GenAISpanAttr.OPERATION_NAME: operation,
        GenAISpanAttr.PROVIDER_NAME: inference_model.backend_name,
        GenAISpanAttr.REQUEST_MODEL: request_model,
        GenAISpanAttr.RESPONSE_MODEL: inference_model.model_id,
        # Pipelex's own, always full values: the exporters redact as their configuration says
        PipelexSpanAttr.TRACE_NAME: otel_context.trace_name,
        PipelexSpanAttr.TRACE_NAME_REDACTED: otel_context.trace_name_redacted,
        PipelexSpanAttr.SPAN_CATEGORY: SpanCategory.INFERENCE,
        PipelexSpanAttr.PIPELINE_RUN_ID: job_metadata.run_metadata.pipeline_run_id,
        PipelexSpanAttr.INFERENCE_KIND: operation.inference_kind,
        PipelexSpanAttr.INFERENCE_BACKEND: inference_model.backend_name,
        PipelexSpanAttr.MODEL_HANDLE: inference_model.name,
    }
    if output_type is not None:
        span_attributes[GenAISpanAttr.OUTPUT_TYPE] = make_otel_gen_ai_output_type(output_type=output_type)
    if pipe_code:
        span_attributes[PipelexSpanAttr.PIPE_CODE] = pipe_code
    if unit_job_id:
        span_attributes[PipelexSpanAttr.UNIT_JOB_ID] = unit_job_id
    # Kept apart so an exporter can rebuild the span's name with the class redacted
    if output_class_name:
        span_attributes[PipelexSpanAttr.OUTPUT_CLASS_NAME] = output_class_name
    if request_attributes:
        span_attributes.update(request_attributes)

    # The run's own identity, so a generation lands on the caller who asked for it rather than on the process that served it
    is_langfuse_enabled = TelemetryManagerAbstract.get_langfuse_enabled()
    span_attributes.update(make_run_identity_span_attributes(run_metadata=job_metadata.run_metadata, is_langfuse_enabled=is_langfuse_enabled))
    # The run's method, the stable identifier of the pipe that made this call, and the run's own pipe-code setting
    span_attributes.update(make_run_method_span_attributes(run_metadata=job_metadata.run_metadata, pipe_id=job_metadata.pipe_id))
    if is_langfuse_enabled:
        span_attributes[LangfuseSpanAttr.TRACE_NAME] = otel_context.trace_name
        span_attributes[LangfuseSpanAttr.RELEASE] = get_package_version()

    # The pipe span the call runs under is the parent, with the pipe's sampled flag, which follows the host's decision
    # on a run that joined the host's trace.
    parent_span_context = SpanContext(
        trace_id=otel_context.trace_id,
        span_id=otel_context.span_id,
        is_remote=True,
        trace_flags=TraceFlags(TraceFlags.SAMPLED if otel_context.is_sampled else TraceFlags.DEFAULT),
        trace_state=OtelFactory.make_trace_state(trace_state_header=otel_context.trace_state),
    )
    parent_ctx = trace.set_span_in_context(NonRecordingSpan(parent_span_context))
    span = tracer.start_span(name=span_name, kind=SpanKind.CLIENT, context=parent_ctx, attributes=span_attributes)
    # A tracer that records nothing, the no-op tracer `OTEL_SDK_DISABLED` hands out for one, gives back the parent it was
    # handed rather than a span of its own; that is no span, exactly as with no tracer.
    if span.get_span_context() == parent_span_context:
        return None
    return span


def record_inference_span_usage(*, span: Span | None, tokens_usage: TokensUsage | None) -> None:
    """Record the usage the call recorded on its span, the tokens in and out and what they cost, each when it is known.

    A usage priced by the request or by the page counts units, not tokens, so it gives its cost and no counts, as the
    call's summary event does. A usage the cost engine cannot price leaves the span without it, never fails the call.
    """
    if span is None or not span.is_recording() or tokens_usage is None or not tokens_usage.nb_tokens_by_category:
        return
    try:
        usage_attributes: dict[str, OTelAttributeValue] = {}
        nb_tokens_by_category = tokens_usage.nb_tokens_by_category
        if tokens_usage.pricing_unit.counts_tokens:
            if TokenCategory.INPUT in nb_tokens_by_category:
                usage_attributes[GenAISpanAttr.USAGE_INPUT_TOKENS] = nb_tokens_by_category[TokenCategory.INPUT]
            if TokenCategory.OUTPUT in nb_tokens_by_category:
                usage_attributes[GenAISpanAttr.USAGE_OUTPUT_TOKENS] = nb_tokens_by_category[TokenCategory.OUTPUT]
        if (usage_cost := compute_tokens_usage_cost_breakdown(tokens_usage=tokens_usage)) is not None:
            usage_attributes[PipelexSpanAttr.INPUT_COST_USD] = usage_cost.input_cost
            usage_attributes[PipelexSpanAttr.OUTPUT_COST_USD] = usage_cost.output_cost
            usage_attributes[PipelexSpanAttr.TOTAL_COST_USD] = usage_cost.total_cost
    except Exception as exc:  # ruff: ignore[blind-except]
        # (2) the usage is whatever the worker recorded, a provider's or a plugin's, so what reading and pricing it can raise
        # cannot be enumerated, and a span is the call's measurement, never part of its outcome.
        log.debug(INFERENCE_SPAN_USAGE_FAILED_MESSAGE, fields=error_fields(exc=exc))
        return
    span.set_attributes(usage_attributes)


def end_inference_span(
    *,
    span: Span | None,
    error: BaseException | None,
    tokens_usage: TokensUsage | None,
    attempt_count: int,
    response_model: str | None,
) -> None:
    """End the generation span of one inference call, recording its usage, its attempts and how it ended.

    A failed call records its exception and ends with the error status and `error.type` set to its inference error
    category, `unknown` for a failure nothing classified. A call cancelled from outside ends with no error status. A span
    already ended, or one that records nothing, is left alone, so ending it twice is harmless.

    Args:
        span: The span `start_inference_span` returned; `None` does nothing.
        error: The exception the call ended with, or `None` when it returned.
        tokens_usage: The usage the call recorded on its job report, summed over its attempts.
        attempt_count: How many times the call asked the model.
        response_model: The model that served the call, as the worker names it when the call ends.
    """
    if span is None or not span.is_recording():
        return
    record_inference_span_usage(span=span, tokens_usage=tokens_usage)
    span.set_attribute(PipelexSpanAttr.ATTEMPT_COUNT, attempt_count)
    if response_model:
        span.set_attribute(GenAISpanAttr.RESPONSE_MODEL, response_model)
    if error is None:
        span.set_status(Status(StatusCode.OK))
    elif isinstance(error, Exception):
        error_category = find_inference_error_category_in_chain(error) or InferenceErrorCategory.UNKNOWN
        span.record_exception(error)
        span.set_attribute(GenAISpanAttr.ERROR_TYPE, error_category)
        span.set_status(Status(StatusCode.ERROR, str(error)))
    span.end()


class InferenceSpanScope:
    """The block an inference call runs in under its generation span, which ends the span however the block ends.

    Entering it holds the span as the Pipelex span active for the block, made OpenTelemetry's current span too when the
    operator turned `join_host_trace` on, and enters the call's summary event again, so the event is logged as the block
    ends, naming the span. Leaving it ends the span with the call's usage, attempts and outcome, read then, before the
    event is logged; it never handles the exception leaving the block.

    Args:
        span: The call's span, `None` when it has none.
        call_summary: The summary event the call ends with, entered again around the block.
        read_tokens_usage: Reads the usage the call recorded when the block ends; `None` for a family that records none.
        read_response_model: Reads the model that served the call when the block ends.
        read_attempt_count: Reads how many times the call asked the model; `None` for a call that asks once.
    """

    def __init__(
        self,
        *,
        span: Span | None,
        call_summary: AbstractContextManager[Any],
        read_tokens_usage: Callable[[], TokensUsage | None] | None,
        read_response_model: Callable[[], str | None],
        read_attempt_count: Callable[[], int] | None = None,
    ) -> None:
        self.span = span
        self._call_summary = call_summary
        self._read_tokens_usage = read_tokens_usage
        self._read_response_model = read_response_model
        self._read_attempt_count = read_attempt_count
        self._span_active: AbstractContextManager[None] | None = None

    def __enter__(self) -> Self:
        self._span_active = pipelex_span_active(span=self.span, make_current=TelemetryManagerAbstract.is_join_host_trace_enabled())
        self._span_active.__enter__()
        self._call_summary.__enter__()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        exc_traceback: TracebackType | None,
    ) -> None:
        try:
            end_inference_span(
                span=self.span,
                error=exc_value,
                tokens_usage=self._read_tokens_usage() if self._read_tokens_usage is not None else None,
                attempt_count=self._read_attempt_count() if self._read_attempt_count is not None else 1,
                response_model=self._read_response_model(),
            )
        finally:
            try:
                self._call_summary.__exit__(exc_type, exc_value, exc_traceback)
            finally:
                if self._span_active is not None:
                    self._span_active.__exit__(exc_type, exc_value, exc_traceback)
