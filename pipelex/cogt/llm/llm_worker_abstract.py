from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from opentelemetry import trace
from opentelemetry.trace import NonRecordingSpan, Span, SpanContext, SpanKind, Status, StatusCode, TraceFlags
from typing_extensions import override

from pipelex import log
from pipelex.cogt.inference.inference_constants import InferenceOutputType
from pipelex.cogt.inference.inference_worker_abstract import InferenceWorkerAbstract
from pipelex.cogt.usage.token_category import TokenCategory
from pipelex.pipeline.exceptions import JobMetadataError
from pipelex.pipeline.job_metadata import UnitJobId
from pipelex.system.telemetry.otel_constants import (
    GenAISpanAttr,
    LangfuseSpanAttr,
    PipelexSpanAttr,
    SpanCategory,
    make_otel_gen_ai_output_type,
)
from pipelex.system.telemetry.otel_factory import OtelFactory
from pipelex.system.telemetry.telemetry_manager_abstract import TelemetryManagerAbstract
from pipelex.tools.misc.package_utils import get_package_version

if TYPE_CHECKING:
    from opentelemetry.util.types import AttributeValue
    from pydantic import BaseModel

    from pipelex.cogt.llm.llm_job import LLMJob
    from pipelex.reporting.reporting_protocol import ReportingProtocol
    from pipelex.tools.typing.pydantic_utils import BaseModelTypeVar


class LLMWorkerAbstract(InferenceWorkerAbstract, ABC):
    def __init__(
        self,
        reporting_delegate: ReportingProtocol | None = None,
    ):
        """Initialize the LLMWorker.

        Args:
            reporting_delegate (ReportingProtocol | None): An optional report delegate for reporting unit jobs.

        """
        InferenceWorkerAbstract.__init__(self, reporting_delegate=reporting_delegate)

    #########################################################
    # Instance methods
    #########################################################

    @property
    @override
    def desc(self) -> str:
        return "If you're using an external plugin, override this method to describe your llm worker"

    @property
    @abstractmethod
    def is_gen_object_supported(self) -> bool:
        return False

    @property
    @abstractmethod
    def is_vision_supported(self) -> bool:
        return False

    #########################################################
    # OTel helper methods - override in subclasses with model info
    #########################################################

    def _get_provider_name(self) -> str:
        """Get the GenAI provider name (e.g., 'openai', 'anthropic'). Override in subclass."""
        return "unknown"

    def _get_request_model_name(self) -> str:
        """Get the request model name. Override in subclass."""
        return "unknown"

    def _get_response_model_name(self) -> str:
        """Get the response model name. Override in subclass."""
        return "unknown"

    def _start_otel_span_llm(self, llm_job: LLMJob, output_type: InferenceOutputType, output_class_name: str | None = None) -> Span | None:
        """Start an OTel span for the LLM job and return it.

        Always includes full (non-redacted) values in Pipelex attributes for PostHog exporters.
        Redaction is handled by individual exporters based on their TelemetryRedactionConfig.
        Safe to call if otel_context is None.
        """
        # Get context from job metadata
        job_metadata = llm_job.job_metadata
        otel_context = job_metadata.otel_context
        job_params = llm_job.applied_job_params or llm_job.job_params

        # Skip if telemetry is disabled (no otel_context)
        if otel_context is None:
            log.verbose("[OTel] No otel_context - skipping LLM span")
            return None

        tracer = TelemetryManagerAbstract.get_instance_tracer()
        if tracer is None:
            log.verbose("[OTel] No tracer available for LLM span")
            return None

        unit_job_id = job_metadata.unit_job_id
        if not unit_job_id:
            msg = "unit_job_id is required for LLM span"
            raise JobMetadataError(msg)
        pipe_code = job_metadata.pipe_code
        if not pipe_code:
            msg = "pipe_code is required for LLM span"
            raise JobMetadataError(msg)
        pipeline_run_id = job_metadata.pipeline_run_id

        # Build output description for span name (full values - exporter handles redaction)
        output_desc: str
        match output_type:
            case InferenceOutputType.TEXT:
                output_desc = output_type
            case InferenceOutputType.OBJECT:
                # Always use full class name in span name, exporter will redact if needed
                output_desc = output_class_name or output_type
            case InferenceOutputType.IMAGE | InferenceOutputType.PAGES:
                msg = "Image output type is not supported for LLM span"
                raise NotImplementedError(msg)

        model_name = self._get_request_model_name()
        # Always use full pipe code and class name - exporter handles redaction
        span_name = f"{pipe_code}: {unit_job_id} ({model_name}) -> {output_desc}"

        # Build all span attributes with FULL (non-redacted) values
        # PostHog exporters will apply redaction based on their TelemetryRedactionConfig
        span_attributes: dict[str, AttributeValue] = {
            # GenAI standard attributes
            GenAISpanAttr.OPERATION_NAME: unit_job_id,
            GenAISpanAttr.OUTPUT_TYPE: make_otel_gen_ai_output_type(output_type=output_type).value,
            GenAISpanAttr.PROVIDER_NAME: self._get_provider_name(),
            GenAISpanAttr.REQUEST_MODEL: model_name,
            GenAISpanAttr.RESPONSE_MODEL: self._get_response_model_name(),
            GenAISpanAttr.REQUEST_TEMPERATURE: job_params.temperature,
            # Pipelex specific context attributes (always full values, exporters redact as needed)
            PipelexSpanAttr.TRACE_NAME: otel_context.trace_name,
            PipelexSpanAttr.TRACE_NAME_REDACTED: otel_context.trace_name_redacted,
            PipelexSpanAttr.SPAN_CATEGORY: SpanCategory.INFERENCE,
            PipelexSpanAttr.PIPELINE_RUN_ID: pipeline_run_id,
            PipelexSpanAttr.PIPE_CODE: pipe_code,  # Full pipe code, exporter handles redaction
        }

        # Store output class name as separate attribute so exporter can rebuild span name with redaction
        if output_class_name:
            span_attributes[PipelexSpanAttr.OUTPUT_CLASS_NAME] = output_class_name

        if TelemetryManagerAbstract.get_langfuse_enabled():
            span_attributes[LangfuseSpanAttr.TRACE_NAME] = otel_context.trace_name
            span_attributes[LangfuseSpanAttr.RELEASE] = get_package_version()
        if job_params.max_tokens:
            span_attributes[GenAISpanAttr.REQUEST_MAX_TOKENS] = job_params.max_tokens
        if job_params.seed:
            span_attributes[GenAISpanAttr.REQUEST_SEED] = job_params.seed

        # Always capture full prompt content - exporters handle redaction as needed
        messages: list[dict[str, Any]] = []
        if llm_job.llm_prompt.system_text:
            system_text_dict = {
                "role": "system",
                "content": llm_job.llm_prompt.system_text,
            }
            messages.append(system_text_dict)
        if llm_job.llm_prompt.user_text or llm_job.llm_prompt.user_images:
            content_dict: list[dict[str, Any]] = []
            if llm_job.llm_prompt.user_text:
                user_text_dict = {
                    "type": "text",
                    "text": llm_job.llm_prompt.user_text,
                }
                content_dict.append(user_text_dict)
            for prompt_image in llm_job.llm_prompt.user_images:
                image_dict = {
                    "type": "image",
                    "image": prompt_image.short_description(),
                }
                content_dict.append(image_dict)
            user_dict = {
                "role": "user",
                "content": content_dict,
            }
            messages.append(user_dict)

        messages_json = OtelFactory.stringify_json(json_conent=messages)
        span_attributes[GenAISpanAttr.PROMPT_CONTENT] = messages_json
        if TelemetryManagerAbstract.get_langfuse_enabled():
            span_attributes[LangfuseSpanAttr.OBSERVATION_INPUT] = messages_json

        # Use trace_id and span_id from otel_context (precomputed)
        # The span_id in otel_context is the parent pipe's span - use it as parent
        parent_span_id = otel_context.span_id
        log.verbose(f"[OTel] LLM span:\n  pipe_code='{pipe_code}'\n  pipeline_run_id='{pipeline_run_id}'\n  parent_span_id={parent_span_id:016x}")

        parent_span_context = SpanContext(
            trace_id=otel_context.trace_id,
            span_id=parent_span_id,
            is_remote=True,
            trace_flags=TraceFlags(TraceFlags.SAMPLED),
        )
        parent_ctx = trace.set_span_in_context(NonRecordingSpan(parent_span_context))

        # Start span with our context and all attributes
        span = tracer.start_span(
            name=span_name,
            kind=SpanKind.CLIENT,
            context=parent_ctx,
            attributes=span_attributes,
        )

        # Debug logging
        span_ctx = span.get_span_context()
        log.verbose(
            f"[OTel] LLM SPAN STARTED:\n"
            f"  pipe_code='{pipe_code}'\n"
            f"  pipeline_run_id='{pipeline_run_id}'\n"
            f"  trace_id={span_ctx.trace_id:032x}\n"
            f"  span_id={span_ctx.span_id:016x}\n"
            f"  parent_span_id={parent_span_id:016x}"
        )

        return span

    def _end_otel_span_with_completion_text(self, span: Span | None, llm_job: LLMJob, completion_text: str) -> None:
        """End the OTel span, recording usage and status. Safe to call if span is None."""
        if span is None:
            return

        job_metadata = llm_job.job_metadata
        span_ctx = span.get_span_context()
        log.verbose(
            f"[OTel] LLM SPAN ENDING:\n"
            f"  pipe_code='{job_metadata.pipe_code}'\n"
            f"  pipeline_run_id='{job_metadata.pipeline_run_id}'\n"
            f"  trace_id={span_ctx.trace_id:032x}\n"
            f"  span_id={span_ctx.span_id:016x}"
        )

        # Record token usage if available
        if llm_job.job_report.llm_tokens_usage:
            tokens = llm_job.job_report.llm_tokens_usage.nb_tokens_by_category
            input_tokens = tokens.get(TokenCategory.INPUT, 0)
            output_tokens = tokens.get(TokenCategory.OUTPUT, 0)
            span.set_attribute(GenAISpanAttr.USAGE_INPUT_TOKENS, input_tokens)
            span.set_attribute(GenAISpanAttr.USAGE_OUTPUT_TOKENS, output_tokens)

        # Always capture full completion content - exporters handle redaction as needed
        span.set_attribute(GenAISpanAttr.COMPLETION_CONTENT, completion_text)
        if TelemetryManagerAbstract.get_langfuse_enabled():
            span.set_attribute(LangfuseSpanAttr.OBSERVATION_OUTPUT, completion_text)

        span.set_status(Status(StatusCode.OK))
        span.end()

    def _end_otel_span_with_completion_object(self, span: Span | None, llm_job: LLMJob, completion_object: BaseModel) -> None:
        """End the OTel span, recording usage and status. Safe to call if span is None."""
        if span is None:
            return

        job_metadata = llm_job.job_metadata
        span_ctx = span.get_span_context()
        log.verbose(
            f"[OTel] LLM SPAN ENDING:\n"
            f"  pipe_code='{job_metadata.pipe_code}'\n"
            f"  pipeline_run_id='{job_metadata.pipeline_run_id}'\n"
            f"  trace_id={span_ctx.trace_id:032x}\n"
            f"  span_id={span_ctx.span_id:016x}"
        )

        # Record token usage if available
        if llm_job.job_report.llm_tokens_usage:
            tokens = llm_job.job_report.llm_tokens_usage.nb_tokens_by_category
            input_tokens = tokens.get(TokenCategory.INPUT, 0)
            output_tokens = tokens.get(TokenCategory.OUTPUT, 0)
            span.set_attribute(GenAISpanAttr.USAGE_INPUT_TOKENS, input_tokens)
            span.set_attribute(GenAISpanAttr.USAGE_OUTPUT_TOKENS, output_tokens)

        # Always capture full completion content - exporters handle redaction as needed
        completion_object_json = OtelFactory.stringify_json(json_conent=completion_object.model_dump(serialize_as_any=True))
        span.set_attribute(GenAISpanAttr.COMPLETION_CONTENT, completion_object_json)
        if TelemetryManagerAbstract.get_langfuse_enabled():
            span.set_attribute(LangfuseSpanAttr.OBSERVATION_OUTPUT, completion_object_json)

        span.set_status(Status(StatusCode.OK))
        span.end()

    def _end_otel_span_with_error(self, span: Span | None, llm_job: LLMJob, error: Exception) -> None:
        """End the OTel span, recording the error. Safe to call if span is None."""
        if span is None:
            return

        job_metadata = llm_job.job_metadata
        span_ctx = span.get_span_context()
        log.verbose(
            f"[OTel] LLM SPAN ENDING WITH ERROR:\n"
            f"  pipe_code='{job_metadata.pipe_code}'\n"
            f"  pipeline_run_id='{job_metadata.pipeline_run_id}'\n"
            f"  trace_id={span_ctx.trace_id:032x}\n"
            f"  span_id={span_ctx.span_id:016x}"
        )

        span.record_exception(error)
        span.set_status(Status(StatusCode.ERROR, str(error)))
        span.end()

    #########################################################
    # Job lifecycle methods
    #########################################################

    async def _before_job(
        self,
        llm_job: LLMJob,
    ):
        # Verify that the job is valid
        llm_job.validate_before_execution()

        # Verify feasibility
        self._check_can_perform_job(llm_job=llm_job)

    async def _after_text_job(
        self,
        span: Span | None,
        llm_job: LLMJob,
        result_text: str,
    ):
        # Report job
        llm_job.llm_job_after_complete()
        if self.reporting_delegate:
            self.reporting_delegate.report_inference_job(inference_job=llm_job)

        # End OTel span with success status and usage data
        self._end_otel_span_with_completion_text(span=span, llm_job=llm_job, completion_text=result_text)

    async def _after_object_job(
        self,
        span: Span | None,
        llm_job: LLMJob,
        result_object: BaseModel,
    ):
        # Report job
        llm_job.llm_job_after_complete()
        if self.reporting_delegate:
            self.reporting_delegate.report_inference_job(inference_job=llm_job)

        # End OTel span with success status and usage data
        self._end_otel_span_with_completion_object(span=span, llm_job=llm_job, completion_object=result_object)

    def _check_can_perform_job(self, llm_job: LLMJob):
        # This can be overridden by subclasses for specific checks
        pass

    async def gen_text(
        self,
        llm_job: LLMJob,
    ) -> str:
        log.verbose("LLM Worker gen_text")
        log.verbose(llm_job.llm_prompt.desc(), title="llm_prompt")

        # metadata
        llm_job.job_metadata.unit_job_id = UnitJobId.LLM_GEN_TEXT

        await self._before_job(llm_job=llm_job)

        # Start OTel span after _before_job (which may set model info)
        span = self._start_otel_span_llm(llm_job=llm_job, output_type=InferenceOutputType.TEXT)

        try:
            text_result = await self._gen_text(llm_job=llm_job)
        except Exception as exc:
            self._end_otel_span_with_error(span=span, llm_job=llm_job, error=exc)
            raise

        await self._after_text_job(span=span, llm_job=llm_job, result_text=text_result)

        return text_result

    @abstractmethod
    async def _gen_text(
        self,
        llm_job: LLMJob,
    ) -> str:
        pass

    async def gen_object(
        self,
        llm_job: LLMJob,
        schema: type[BaseModelTypeVar],
    ) -> BaseModelTypeVar:
        log.verbose(f"LLM Worker gen_object using {self.desc}")
        log.verbose(llm_job.llm_prompt.desc(), title="llm_prompt")

        # metadata
        llm_job.job_metadata.unit_job_id = UnitJobId.LLM_GEN_OBJECT

        await self._before_job(llm_job=llm_job)

        # Start OTel span after _before_job (which may set model info)
        span = self._start_otel_span_llm(llm_job=llm_job, output_type=InferenceOutputType.OBJECT, output_class_name=schema.__name__)

        try:
            object_result = await self._gen_object(llm_job=llm_job, schema=schema)

            # Cleanup result
            if hasattr(object_result, "_raw_response"):
                delattr(object_result, "_raw_response")
        except Exception as exc:
            self._end_otel_span_with_error(span=span, llm_job=llm_job, error=exc)
            raise

        await self._after_object_job(span=span, llm_job=llm_job, result_object=object_result)

        return object_result

    @abstractmethod
    async def _gen_object(
        self,
        llm_job: LLMJob,
        schema: type[BaseModelTypeVar],
    ) -> BaseModelTypeVar:
        pass
