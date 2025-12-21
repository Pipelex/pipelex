from types import TracebackType

from opentelemetry import trace
from opentelemetry.trace import NonRecordingSpan, Span, SpanContext, SpanKind, Status, StatusCode, TraceFlags

from pipelex import log
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.inputs.input_stuff_specs import InputStuffSpecs
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.pipeline.job_metadata import OtelContext
from pipelex.system.telemetry.otel_constants import (
    LangfuseSpanAttr,
    OTelConstants,
    PipelexSpanAttr,
    SpanCategory,
    SpanOutcome,
)
from pipelex.system.telemetry.otel_factory import OtelFactory
from pipelex.system.telemetry.telemetry_manager_abstract import TelemetryManagerAbstract
from pipelex.tools.misc.package_utils import get_package_version
from pipelex.types import Self


class PipeTelemetryContext:
    """Context manager for pipe telemetry spans."""

    def __init__(
        self,
        pipe_code: str,
        pipe_type: str,
        pipe_category: str,
        description: str | None,
        parent_otel_context: OtelContext | None,
        pipeline_run_id: str,
        working_memory: WorkingMemory,
        needed_inputs: InputStuffSpecs,
    ):
        self._pipe_code = pipe_code
        self._pipe_type = pipe_type
        self._pipe_category = pipe_category
        self._description = description
        self._parent_otel_context = parent_otel_context
        self._pipeline_run_id = pipeline_run_id
        self._working_memory = working_memory
        self._needed_inputs = needed_inputs

        self._span: Span | None = None
        self._is_root_span: bool = False
        self.otel_context: OtelContext | None = None
        self.pipe_output: PipeOutput | None = None  # Set before exiting

    def __enter__(self) -> Self:
        if self._parent_otel_context is None:
            return self

        # Move _start_pipe_span logic here
        self._span, self._is_root_span = self._start_pipe_span(
            self._parent_otel_context, pipeline_run_id=self._pipeline_run_id, working_memory=self._working_memory
        )
        if self._span:
            span_context = self._span.get_span_context()
            self.otel_context = OtelContext(
                trace_id=self._parent_otel_context.trace_id,
                trace_name=self._parent_otel_context.trace_name,
                trace_name_redacted=self._parent_otel_context.trace_name_redacted,
                span_id=span_context.span_id,
            )
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: TracebackType | None):
        if self._span is None:
            return False

        if exc_val is not None:
            self._end_pipe_span_error(self._span, error=exc_val, is_root_span=self._is_root_span)
        elif self.pipe_output is not None:
            self._end_pipe_span_success(span=self._span, pipe_output=self.pipe_output, is_root_span=self._is_root_span)

        return False  # Don't suppress exceptions

    def _start_pipe_span(
        self,
        parent_otel_context: OtelContext,
        pipeline_run_id: str,
        working_memory: WorkingMemory,
    ) -> tuple[Span | None, bool]:
        """Start an OTel span for this pipe execution.

        Always includes full (non-redacted) pipe codes and content in span attributes.
        Redaction is handled by individual exporters based on their TelemetryRedactionConfig.

        Args:
            parent_otel_context: The parent's OTel context.
            pipeline_run_id: The pipeline run ID for span attributes.
            working_memory: The working memory containing input stuffs for telemetry capture.

        Returns:
            A tuple of (span, is_root_span) where span is the started span or None if tracer
            is unavailable, and is_root_span indicates if this is the trace root span.
        """
        tracer = TelemetryManagerAbstract.get_instance_tracer()
        if tracer is None:
            log.verbose(f"[OTel] No tracer available for pipe '{self._pipe_code}'")
            return None, False

        # Always use full pipe code - redaction is handled by exporters
        span_name = f"{self._pipe_type}: {self._pipe_code}"

        # For root spans: parent_otel_context.span_id is OTEL_VIRTUAL_ROOT_PARENT_SPAN_ID (1)
        # This ensures OTel uses our trace_id (INVALID_SPAN_ID=0 makes context invalid).
        # The exporter filters out this virtual parent when setting $ai_parent_id.
        # For child spans: parent_otel_context.span_id is the actual parent's span_id
        parent_span_id = parent_otel_context.span_id
        is_root_span = parent_span_id == OTelConstants.OTEL_VIRTUAL_ROOT_PARENT_SPAN_ID

        # Build all span attributes upfront with FULL (non-redacted) values
        # PostHog exporters will apply redaction based on their TelemetryRedactionConfig
        # Langfuse gets full data - users who configure Langfuse control their own data exposure
        span_attributes: dict[str, str] = {
            # Pipelex-specific attributes (always full values, exporters redact as needed)
            PipelexSpanAttr.TRACE_NAME: parent_otel_context.trace_name,
            PipelexSpanAttr.TRACE_NAME_REDACTED: parent_otel_context.trace_name_redacted,
            PipelexSpanAttr.SPAN_CATEGORY: SpanCategory.PIPE,
            PipelexSpanAttr.PIPELINE_RUN_ID: pipeline_run_id,
            PipelexSpanAttr.PIPE_CATEGORY: self._pipe_category,
            PipelexSpanAttr.PIPE_TYPE: self._pipe_type,
            PipelexSpanAttr.PIPE_CODE: self._pipe_code,  # Full pipe code, exporter handles redaction
        }

        # Langfuse-specific attributes: always send full data
        if TelemetryManagerAbstract.get_langfuse_enabled():
            span_attributes.update(
                {
                    LangfuseSpanAttr.TRACE_NAME: parent_otel_context.trace_name,
                    LangfuseSpanAttr.RELEASE: get_package_version(),
                    LangfuseSpanAttr.OBSERVATION_TYPE: SpanCategory.PIPE,
                    LangfuseSpanAttr.OBSERVATION_PIPE_CATEGORY: self._pipe_category,
                    LangfuseSpanAttr.OBSERVATION_PIPE_TYPE: self._pipe_type,
                    LangfuseSpanAttr.OBSERVATION_PIPE_CODE: self._pipe_code,
                    LangfuseSpanAttr.OBSERVATION_PIPELINE_RUN_ID: pipeline_run_id,
                }
            )
            if self._description:
                span_attributes[LangfuseSpanAttr.OBSERVATION_DESCRIPTION] = self._description

            # Capture full input content for Langfuse
            needed_input_names = set(self._needed_inputs.required_names)
            inputs_json = OtelFactory.make_inputs_json(
                working_memory=working_memory,
                needed_input_names=needed_input_names,
                max_length=None,  # No truncation for Langfuse
            )
            span_attributes[LangfuseSpanAttr.OBSERVATION_INPUT] = inputs_json

            # For root span, also set trace-level input and metadata
            if is_root_span:
                span_attributes[LangfuseSpanAttr.TRACE_INPUT] = inputs_json
                # Set trace-level metadata (filterable in Langfuse UI)
                span_attributes[LangfuseSpanAttr.TRACE_PIPE_CODE] = self._pipe_code
                span_attributes[LangfuseSpanAttr.TRACE_PIPE_TYPE] = self._pipe_type
                span_attributes[LangfuseSpanAttr.TRACE_PIPE_CATEGORY] = self._pipe_category
                span_attributes[LangfuseSpanAttr.TRACE_PIPELINE_RUN_ID] = pipeline_run_id
                if self._description:
                    span_attributes[LangfuseSpanAttr.TRACE_DESCRIPTION] = self._description

        parent_span_context = SpanContext(
            trace_id=parent_otel_context.trace_id,
            span_id=parent_span_id,
            is_remote=True,
            trace_flags=TraceFlags(TraceFlags.SAMPLED),
        )
        parent_ctx = trace.set_span_in_context(NonRecordingSpan(parent_span_context))

        # Start span with attributes - OTel generates the span_id, we capture it after
        span = tracer.start_span(
            name=span_name,
            kind=SpanKind.INTERNAL,
            context=parent_ctx,
            attributes=span_attributes,
        )

        # Debug logging
        span_ctx = span.get_span_context()
        log.verbose(
            f"[OTel] PIPE SPAN STARTED:\n"
            f"  pipe_code='{self._pipe_code}'\n"
            f"  pipeline_run_id='{pipeline_run_id}'\n"
            f"  trace_id={span_ctx.trace_id:032x}\n"
            f"  span_id={span_ctx.span_id:016x}\n"
            f"  parent_span_id={parent_span_id:016x}\n"
            f"  is_root_span={is_root_span}"
        )

        return span, is_root_span

    def _end_pipe_span_success(self, span: Span | None, pipe_output: PipeOutput, is_root_span: bool) -> None:
        """End the pipe's OTel span with success status. Safe to call if span is None.

        Args:
            span: The OTel span to end, or None if telemetry is disabled.
            pipe_output: The pipe output containing the result for telemetry capture.
            is_root_span: Whether this is the root span of the trace.
        """
        if span is None:
            return

        span_ctx = span.get_span_context()
        log.verbose(
            f"[OTel] PIPE SPAN ENDING:\n  pipe_code='{self._pipe_code}'\n  trace_id={span_ctx.trace_id:032x}\n  span_id={span_ctx.span_id:016x}"
        )

        # Always capture full output content for Langfuse
        if TelemetryManagerAbstract.get_langfuse_enabled():
            output_json = OtelFactory.make_output_json(
                pipe_output=pipe_output,
                max_length=None,  # No truncation for Langfuse
            )
            span.set_attribute(LangfuseSpanAttr.OBSERVATION_OUTPUT, output_json)

            # For root span, also set trace-level output
            if is_root_span:
                span.set_attribute(LangfuseSpanAttr.TRACE_OUTPUT, output_json)

        span.set_attribute(PipelexSpanAttr.OUTCOME, SpanOutcome.SUCCESS)
        span.set_status(Status(StatusCode.OK))
        if TelemetryManagerAbstract.get_langfuse_enabled():
            span.set_attribute(LangfuseSpanAttr.OBSERVATION_OUTCOME, SpanOutcome.SUCCESS)
            if is_root_span:
                span.set_attribute(LangfuseSpanAttr.TRACE_OUTCOME, SpanOutcome.SUCCESS)
        span.end()

    def _end_pipe_span_error(self, span: Span | None, error: BaseException, is_root_span: bool = False) -> None:
        """End the pipe's OTel span with error status. Safe to call if span is None.

        Args:
            span: The OTel span to end, or None if telemetry is disabled.
            error: The exception that caused the error.
            is_root_span: Whether this is the root span of the trace.
        """
        if span is None:
            return

        span_ctx = span.get_span_context()
        msg = (
            f"[OTel] PIPE SPAN ENDING WITH ERROR:\n  "
            f"pipe_code='{self._pipe_code}'\n  trace_id={span_ctx.trace_id:032x}\n  span_id={span_ctx.span_id:016x}"
        )
        log.verbose(msg)

        span.set_attribute(PipelexSpanAttr.OUTCOME, SpanOutcome.FAILURE)
        span.record_exception(error)
        span.set_status(Status(StatusCode.ERROR, str(error)))
        if TelemetryManagerAbstract.get_langfuse_enabled():
            span.set_attribute(LangfuseSpanAttr.OBSERVATION_OUTCOME, SpanOutcome.FAILURE)
            if is_root_span:
                span.set_attribute(LangfuseSpanAttr.TRACE_OUTCOME, SpanOutcome.FAILURE)
        span.end()
