from __future__ import annotations

import hashlib
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
from pipelex.system.telemetry.otel_utils import (
    GEN_AI_COMPLETION_CONTENT,
    GEN_AI_OPERATION_NAME,
    GEN_AI_PROMPT_CONTENT,
    GEN_AI_REQUEST_MODEL,
    GEN_AI_SYSTEM,
    GEN_AI_USAGE_INPUT_TOKENS,
    GEN_AI_USAGE_OUTPUT_TOKENS,
)

if TYPE_CHECKING:
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

    def _get_system(self) -> str:
        """Get the GenAI system/provider name (e.g., 'openai', 'anthropic'). Override in subclass."""
        return "unknown"

    def _get_model_name(self) -> str:
        """Get the model name/id (e.g., 'gpt-4'). Override in subclass."""
        return "unknown"

    def _should_capture_content(self) -> bool:
        """Return whether prompt/response content should be captured. Override in subclass."""
        return False

    def _start_otel_span(self, llm_job: LLMJob) -> None:
        """Start an OTel span and attach it to the llm_job. Safe to call if tracer is None."""
        tracer = self._get_tracer()
        if tracer is None:
            return

        # Get context from job metadata
        metadata = llm_job.job_metadata
        unit_job_id = metadata.unit_job_id or "unknown"
        pipeline_run_id = metadata.pipeline_run_id
        pipe_job_id = metadata.pipe_job_ids[-1] if metadata.pipe_job_ids else "main"

        # Construct span name similar to GatewayFactory
        # Format: "{pipe_job_id}: {unit_job_id} {model_name}"
        model_name = self._get_model_name()
        span_name = f"{pipe_job_id}: {unit_job_id} {model_name}"

        # 1. Generate deterministic 128-bit Trace ID from pipeline_run_id
        trace_id_int = int(hashlib.md5(pipeline_run_id.encode("utf-8")).hexdigest(), 16)  # noqa: S324

        # 2. Create a virtual parent context
        # We pretend all these calls are children of a remote parent representing the run
        span_context = SpanContext(
            trace_id=trace_id_int,
            span_id=1,  # Arbitrary valid span ID for the virtual parent
            is_remote=True,
            trace_flags=TraceFlags(TraceFlags.SAMPLED),
        )
        parent_ctx = trace.set_span_in_context(NonRecordingSpan(span_context))

        # 3. Start span with this parent context
        span = tracer.start_span(
            name=span_name,
            kind=SpanKind.CLIENT,
            context=parent_ctx,
        )

        # Set standard attributes
        span.set_attribute(GEN_AI_SYSTEM, self._get_system())
        span.set_attribute(GEN_AI_REQUEST_MODEL, model_name)
        span.set_attribute(GEN_AI_OPERATION_NAME, unit_job_id)

        # Set Pipelex specific context attributes
        span.set_attribute("pipelex.pipeline.run_id", pipeline_run_id)
        span.set_attribute("pipelex.pipe.job_id", pipe_job_id)
        if metadata.job_name:
            span.set_attribute("pipelex.job.name", metadata.job_name)

        # Capture prompt content if enabled
        if self._should_capture_content() and llm_job.llm_prompt.user_text:
            span.set_attribute(GEN_AI_PROMPT_CONTENT, llm_job.llm_prompt.user_text)

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

        if is_error and error is not None:
            span.record_exception(error)
            span.set_status(Status(StatusCode.ERROR, str(error)))
        else:
            # Record token usage if available
            if llm_job.job_report.llm_tokens_usage:
                tokens = llm_job.job_report.llm_tokens_usage.nb_tokens_by_category
                input_tokens = tokens.get(TokenCategory.INPUT, 0)
                output_tokens = tokens.get(TokenCategory.OUTPUT, 0)
                span.set_attribute(GEN_AI_USAGE_INPUT_TOKENS, input_tokens)
                span.set_attribute(GEN_AI_USAGE_OUTPUT_TOKENS, output_tokens)

            # Capture response content if enabled and result is a string
            if self._should_capture_content() and isinstance(result, str):
                span.set_attribute(GEN_AI_COMPLETION_CONTENT, result)

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
        self._start_otel_span(llm_job=llm_job)

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
        self._start_otel_span(llm_job=llm_job)

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
