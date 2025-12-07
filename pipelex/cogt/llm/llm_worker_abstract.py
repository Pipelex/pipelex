from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import nullcontext
from typing import TYPE_CHECKING, Any

from opentelemetry import trace
from opentelemetry.trace import NonRecordingSpan, Span, SpanContext, SpanKind, Status, StatusCode, TraceFlags, Tracer
from typing_extensions import override

from pipelex import log
from pipelex.cogt.inference.inference_worker_abstract import InferenceWorkerAbstract
from pipelex.cogt.usage.token_category import TokenCategory
from pipelex.pipeline.job_metadata import UnitJobId
from pipelex.system.telemetry.otel_constants import GenAISpanAttr
from pipelex.system.telemetry.telemetry_constants import REDACTED, UNKNOWN_JOB, UNKNOWN_PIPE, OutputDesc, PipelexSpanAttr, SpanCategory
from pipelex.system.telemetry.telemetry_manager_abstract import TelemetryManagerAbstract

if TYPE_CHECKING:
    from opentelemetry.util.types import AttributeValue

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

    def _get_tracer(self) -> Tracer | None:
        """Get the OTel tracer. Override in subclass to provide actual tracer."""
        return None

    def _get_provider_name(self) -> str:
        """Get the GenAI provider name (e.g., 'openai', 'anthropic'). Override in subclass."""
        return "unknown"

    def _get_model_name(self) -> str:
        """Get the model name. Override in subclass."""
        return "unknown"

    def _should_capture_content(self) -> bool:
        """Return whether prompt/response content should be captured. Override in subclass."""
        return False

    def _start_otel_span_llm(self, llm_job: LLMJob, output_desc: str) -> None:
        """Start an OTel span and attach it to the llm_job. Safe to call if otel_context is None."""
        # Get context from job metadata
        metadata = llm_job.job_metadata
        otel_context = metadata.otel_context

        # Skip if telemetry is disabled (no otel_context)
        if otel_context is None:
            log.dev("[OTel] No otel_context - skipping LLM span")
            return

        tracer = self._get_tracer()
        if tracer is None:
            log.dev("[OTel] No tracer available for LLM span")
            return

        unit_job_id = metadata.unit_job_id or UNKNOWN_JOB
        pipeline_run_id = metadata.pipeline_run_id
        pipe_code = metadata.pipe_code or UNKNOWN_PIPE

        # Determine if we need to redact output class names
        if not TelemetryManagerAbstract.is_capture_output_class_name_enabled() and not OutputDesc.is_text(output_desc):
            output_desc = OutputDesc.OBJECT

        # Determine if we need to redact pipe code
        if TelemetryManagerAbstract.is_capture_pipe_codes_enabled():
            pipe_code_attr = pipe_code
        else:
            pipe_code_attr = REDACTED

        model_name = self._get_model_name()
        span_name = f"{pipe_code_attr}: {unit_job_id} ({model_name}) -> {output_desc}"

        # Build all span attributes upfront
        span_attributes: dict[str, AttributeValue] = {
            # GenAI standard attributes
            GenAISpanAttr.PROVIDER_NAME: self._get_provider_name(),
            GenAISpanAttr.REQUEST_MODEL: model_name,
            GenAISpanAttr.OPERATION_NAME: unit_job_id,
            # Pipelex specific context attributes
            PipelexSpanAttr.SPAN_CATEGORY: SpanCategory.INFERENCE,
            PipelexSpanAttr.PIPELINE_RUN_ID: pipeline_run_id,
            PipelexSpanAttr.PIPE_CODE: pipe_code_attr,
        }
        if metadata.job_name:
            span_attributes[PipelexSpanAttr.JOB_NAME] = metadata.job_name
        if self._should_capture_content() and llm_job.llm_prompt.user_text:
            span_attributes[GenAISpanAttr.PROMPT_CONTENT] = llm_job.llm_prompt.user_text

        # Use trace_id and span_id from otel_context (precomputed)
        # The span_id in otel_context is the parent pipe's span - use it as parent
        parent_span_id = otel_context.span_id
        log.dev(f"[OTel] LLM span:\n  pipe_code='{pipe_code}'\n  pipeline_run_id='{pipeline_run_id}'\n  parent_span_id={parent_span_id:016x}")

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
        log.dev(
            f"[OTel] LLM SPAN STARTED:\n"
            f"  pipe_code='{pipe_code}'\n"
            f"  pipeline_run_id='{pipeline_run_id}'\n"
            f"  trace_id={span_ctx.trace_id:032x}\n"
            f"  span_id={span_ctx.span_id:016x}\n"
            f"  parent_span_id={parent_span_id:016x}"
        )

        # Store span on job for later retrieval
        llm_job.set_otel_span(span)

    def _get_otel_span(self, llm_job: LLMJob) -> Span | None:
        """Get the OTel span from the llm_job, if any."""
        return llm_job.get_otel_span()

    def _end_otel_span(self, llm_job: LLMJob, result: Any, is_error: bool = False, error: Exception | None = None) -> None:
        """End the OTel span, recording usage and status. Safe to call if no span exists."""
        span = self._get_otel_span(llm_job)
        if span is None:
            return

        metadata = llm_job.job_metadata
        span_ctx = span.get_span_context()
        log.dev(
            f"[OTel] LLM SPAN ENDING:\n"
            f"  pipe_code='{metadata.pipe_code}'\n"
            f"  pipeline_run_id='{metadata.pipeline_run_id}'\n"
            f"  trace_id={span_ctx.trace_id:032x}\n"
            f"  span_id={span_ctx.span_id:016x}"
        )

        if is_error and error is not None:
            span.record_exception(error)
            span.set_status(Status(StatusCode.ERROR, str(error)))
        else:
            # Record token usage if available
            if llm_job.job_report.llm_tokens_usage:
                tokens = llm_job.job_report.llm_tokens_usage.nb_tokens_by_category
                input_tokens = tokens.get(TokenCategory.INPUT, 0)
                output_tokens = tokens.get(TokenCategory.OUTPUT, 0)
                span.set_attribute(GenAISpanAttr.USAGE_INPUT_TOKENS, input_tokens)
                span.set_attribute(GenAISpanAttr.USAGE_OUTPUT_TOKENS, output_tokens)

            # Capture response content if enabled and result is a string
            if self._should_capture_content() and isinstance(result, str):
                span.set_attribute(GenAISpanAttr.COMPLETION_CONTENT, result)

            span.set_status(Status(StatusCode.OK))

        span.end()
        llm_job.set_otel_span(None)

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

    async def _after_job(
        self,
        llm_job: LLMJob,
        result: Any,
    ):
        # Report job
        llm_job.llm_job_after_complete()
        if self.reporting_delegate:
            self.reporting_delegate.report_inference_job(inference_job=llm_job)

        # End OTel span with success status and usage data
        self._end_otel_span(llm_job=llm_job, result=result)

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
        self._start_otel_span_llm(llm_job=llm_job, output_desc="Text")

        # Get span and create context manager
        span = self._get_otel_span(llm_job)
        ctx_manager = trace.use_span(span, end_on_exit=False) if span else nullcontext()

        try:
            with ctx_manager:
                result = await self._gen_text(llm_job=llm_job)
        except Exception as exc:
            self._end_otel_span(llm_job=llm_job, result=None, is_error=True, error=exc)
            raise

        await self._after_job(llm_job=llm_job, result=result)

        return result

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
        self._start_otel_span_llm(llm_job=llm_job, output_desc=schema.__name__)

        # Get span and create context manager
        span = self._get_otel_span(llm_job)
        ctx_manager = trace.use_span(span, end_on_exit=False) if span else nullcontext()

        try:
            with ctx_manager:
                # Execute job
                result = await self._gen_object(llm_job=llm_job, schema=schema)

                # Cleanup result
                if hasattr(result, "_raw_response"):
                    delattr(result, "_raw_response")
        except Exception as exc:
            self._end_otel_span(llm_job=llm_job, result=None, is_error=True, error=exc)
            raise

        await self._after_job(llm_job=llm_job, result=result)

        return result

    @abstractmethod
    async def _gen_object(
        self,
        llm_job: LLMJob,
        schema: type[BaseModelTypeVar],
    ) -> BaseModelTypeVar:
        pass
