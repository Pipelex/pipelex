"""PostHog span exporter for OpenTelemetry.

This module provides a SpanExporter that sends OTel spans to PostHog
as $ai_generation or $ai_span events.
"""

from typing import Any, Mapping, Sequence, cast

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.util.types import AttributeValue
from posthog import Posthog
from typing_extensions import override

from pipelex import log
from pipelex.system.telemetry.otel_constants import (
    GenAISpanAttr,
    OTelConstants,
    PipelexSpanAttr,
    PostHogAttr,
    PostHogEvent,
    SpanCategory,
)
from pipelex.system.telemetry.telemetry_config import TelemetryRedactionConfig


class PostHogSpanExporter(SpanExporter):
    """Exports OTel spans to PostHog as $ai_generation or $ai_span events.

    Applies redaction rules from TelemetryRedactionConfig before sending events.
    """

    def __init__(
        self,
        posthog_client: Posthog,
        distinct_id: str | None,
        redaction_config: TelemetryRedactionConfig,
    ):
        self.posthog_client = posthog_client
        self.distinct_id = distinct_id
        self.redaction_config = redaction_config

    def _capture_event(self, event: PostHogEvent, properties: dict[str, Any]) -> None:
        """Capture an event to PostHog, handling anonymous vs identified users.

        PostHog requires a valid distinct_id - passing None will cause the event to be rejected.
        For anonymous tracking, we omit distinct_id and set $process_person_profile=False.
        """
        if self.distinct_id:
            # Identified user: pass distinct_id
            self.posthog_client.capture(
                distinct_id=self.distinct_id,
                event=event,
                properties=properties,
            )
        else:
            # Anonymous user: don't pass distinct_id, mark as anonymous
            properties[PostHogAttr.PROCESS_PERSON_PROFILE] = False
            self.posthog_client.capture(
                event=event,
                properties=properties,
            )

    def _truncate_content(self, content: str) -> str:
        """Truncate content if it exceeds max length.

        Args:
            content: The content string to potentially truncate.

        Returns:
            The original content if no limit is set or within limit,
            otherwise truncated content with suffix.
        """
        max_length = self.redaction_config.content_max_length
        if max_length is None or len(content) <= max_length:
            return content
        truncate_at = max(0, max_length - len(OTelConstants.TRUNCATION_SUFFIX))
        return content[:truncate_at] + OTelConstants.TRUNCATION_SUFFIX

    def _apply_content_redaction(self, properties: dict[str, Any]) -> None:
        """Apply content redaction to properties in place.

        Removes or truncates content fields based on redaction config.

        Args:
            properties: The properties dict to modify in place.
        """
        if self.redaction_config.redact_content:
            # Remove content fields entirely
            properties.pop(PostHogAttr.INPUT, None)
            properties.pop(PostHogAttr.OUTPUT_CHOICES, None)
        else:
            # Apply truncation if content exists
            if properties.get(PostHogAttr.INPUT):
                properties[PostHogAttr.INPUT] = self._truncate_content(str(properties[PostHogAttr.INPUT]))
            if properties.get(PostHogAttr.OUTPUT_CHOICES):
                properties[PostHogAttr.OUTPUT_CHOICES] = self._truncate_content(str(properties[PostHogAttr.OUTPUT_CHOICES]))

    def _build_redacted_pipe_span_name(
        self,
        original_span_name: str,
        pipe_type: str | None,
    ) -> str:
        """Build a redacted span name for pipe spans.

        Pipe span names follow the format: "{pipe_type}: {pipe_code}"
        This method rebuilds the name with redacted pipe code if needed.

        Args:
            original_span_name: The original span name from OTel.
            pipe_type: The pipe type from attributes.

        Returns:
            The span name with redacted pipe code if redaction is enabled,
            otherwise the original span name.
        """
        if not self.redaction_config.redact_pipe_codes:
            return original_span_name

        # Rebuild with redacted pipe code
        if pipe_type:
            return pipe_type
        else:
            return OTelConstants.PIPE_CODE_REDACTED

    def _build_redacted_generation_span_name(
        self,
        original_span_name: str,
        pipe_code: str | None,
        unit_job_id: str | None,
        model_name: str | None,
        output_class_name: str | None,
    ) -> str:
        """Build a redacted span name for generation spans.

        Generation span names follow the format:
        "{pipe_code}: {unit_job_id} ({model_name}) -> {output_desc}"
        where output_desc is either "text" or the output class name.

        Args:
            original_span_name: The original span name from OTel.
            pipe_code: The original pipe code from attributes.
            unit_job_id: The unit job ID (e.g., "LLM_GEN_TEXT").
            model_name: The model name.
            output_class_name: The output class name (for object generation).

        Returns:
            The span name with redacted parts based on redaction config.
        """
        redact_pipe_codes = self.redaction_config.redact_pipe_codes
        redact_class_names = self.redaction_config.redact_output_class_names

        if not redact_pipe_codes and not redact_class_names:
            return original_span_name

        # Build output description
        if output_class_name:
            display_output = OTelConstants.OUTPUT_CLASS_REDACTED if redact_class_names else output_class_name
        else:
            display_output = "text"

        # Build redacted pipe code
        if redact_pipe_codes:
            return f"{unit_job_id or 'unknown'} ({model_name or 'unknown'}) -> {display_output}"
        elif pipe_code:
            return f"{pipe_code}: {unit_job_id or 'unknown'} ({model_name or 'unknown'}) -> {display_output}"
        else:
            return f"{unit_job_id or 'unknown'} ({model_name or 'unknown'}) -> {display_output}"

    def _get_redacted_pipe_code(self, pipe_code: str | None) -> str | None:
        """Get the pipe code, redacted if config requires it.

        Args:
            pipe_code: The original pipe code.

        Returns:
            The original pipe code or redacted value based on config.
        """
        if not self.redaction_config.redact_pipe_codes:
            return pipe_code
        return OTelConstants.PIPE_CODE_REDACTED if pipe_code else None

    def _get_redacted_output_class_name(self, output_class_name: str | None) -> str | None:
        """Get the output class name, redacted if config requires it.

        Args:
            output_class_name: The original output class name.

        Returns:
            The original output class name or redacted value based on config.
        """
        if not self.redaction_config.redact_output_class_names:
            return output_class_name
        return OTelConstants.PIPE_CODE_REDACTED if output_class_name else None

    def _get_base_properties(self, span: ReadableSpan, attributes: Mapping[str, AttributeValue]) -> dict[str, Any]:
        """Get common properties for all span types."""
        properties: dict[str, Any] = {}
        if span.end_time and span.start_time:
            properties[PostHogAttr.LATENCY] = (span.end_time - span.start_time) / 1e9

        # Add trace/span IDs for PostHog trace grouping
        span_context = span.get_span_context()
        if span_context and span_context.is_valid:
            properties[PostHogAttr.TRACE_ID] = f"{span_context.trace_id:032x}"
            properties[PostHogAttr.SPAN_ID] = f"{span_context.span_id:016x}"
            # Use redacted or full trace name based on redaction config
            if self.redaction_config.redact_pipe_codes:
                properties[PostHogAttr.TRACE_NAME] = attributes.get(PipelexSpanAttr.TRACE_NAME_REDACTED)
            else:
                properties[PostHogAttr.TRACE_NAME] = attributes.get(PipelexSpanAttr.TRACE_NAME)

        # Add parent span ID for trace hierarchy
        # Filter out virtual root parent (used to set trace_id for root spans)
        if span.parent and span.parent.span_id != OTelConstants.OTEL_VIRTUAL_ROOT_PARENT_SPAN_ID:
            properties[PostHogAttr.PARENT_ID] = f"{span.parent.span_id:016x}"

        return properties

    def _export_generation_span(self, span: ReadableSpan, attributes: Mapping[str, AttributeValue]) -> None:
        """Export a GenAI generation span."""
        properties = self._get_base_properties(span=span, attributes=attributes)
        provider_operation_combo = f"{attributes.get(GenAISpanAttr.PROVIDER_NAME)}:{attributes.get(GenAISpanAttr.OPERATION_NAME)}"

        # Get raw attribute values for redaction
        pipe_code = cast("str | None", attributes.get(PipelexSpanAttr.PIPE_CODE))
        output_class_name = cast("str | None", attributes.get(PipelexSpanAttr.OUTPUT_CLASS_NAME))
        unit_job_id = cast("str | None", attributes.get(GenAISpanAttr.OPERATION_NAME))
        model_name = cast("str | None", attributes.get(GenAISpanAttr.REQUEST_MODEL))

        properties.update(
            {
                PostHogAttr.MODEL: model_name,
                PostHogAttr.MODEL_ID: attributes.get(GenAISpanAttr.RESPONSE_MODEL),
                PostHogAttr.PROVIDER: provider_operation_combo,
                PostHogAttr.TEMPERATURE: attributes.get(GenAISpanAttr.REQUEST_TEMPERATURE),
                PostHogAttr.MAX_TOKENS: attributes.get(GenAISpanAttr.REQUEST_MAX_TOKENS),
                PostHogAttr.SEED: attributes.get(GenAISpanAttr.REQUEST_SEED),
                PostHogAttr.OUTPUT_TYPE: attributes.get(GenAISpanAttr.OUTPUT_TYPE),
                PostHogAttr.INPUT_TOKENS: attributes.get(GenAISpanAttr.USAGE_INPUT_TOKENS),
                PostHogAttr.OUTPUT_TOKENS: attributes.get(GenAISpanAttr.USAGE_OUTPUT_TOKENS),
            }
        )

        # Add content if available
        if prompt := attributes.get(GenAISpanAttr.PROMPT_CONTENT):
            properties[PostHogAttr.INPUT] = prompt
        if completion := attributes.get(GenAISpanAttr.COMPLETION_CONTENT):
            properties[PostHogAttr.OUTPUT_CHOICES] = completion

        # Apply content redaction (removes or truncates content)
        self._apply_content_redaction(properties)

        # Build redacted span name for display
        redacted_span_name = self._build_redacted_generation_span_name(
            original_span_name=span.name,
            pipe_code=pipe_code,
            unit_job_id=unit_job_id,
            model_name=model_name,
            output_class_name=output_class_name,
        )
        properties[PostHogAttr.SPAN_NAME] = redacted_span_name

        # Apply pipe code and output class name redaction to properties (only add if not None)
        if redacted_pipe_code := self._get_redacted_pipe_code(pipe_code):
            properties["pipe_code"] = redacted_pipe_code
        if redacted_output_class_name := self._get_redacted_output_class_name(output_class_name):
            properties["output_class_name"] = redacted_output_class_name

        # Add pipeline_run_id (never redacted - useful for debugging and correlation)
        pipeline_run_id = attributes.get(PipelexSpanAttr.PIPELINE_RUN_ID)
        properties["pipeline_run_id"] = pipeline_run_id

        log.verbose(
            f"[OTel->PostHog] EXPORT $ai_generation:\n"
            f"  pipe_code='{properties.get('pipe_code')}'\n"
            f"  pipeline_run_id='{pipeline_run_id}'\n"
            f"  trace_id={properties.get(PostHogAttr.TRACE_ID)}\n"
            f"  span_id={properties.get(PostHogAttr.SPAN_ID)}\n"
            f"  parent_id={properties.get(PostHogAttr.PARENT_ID)}\n"
            f"  model={properties.get(PostHogAttr.MODEL)}"
        )

        self._capture_event(event=PostHogEvent.GENERATION, properties=properties)

    def _export_pipe_span(self, span: ReadableSpan, attributes: Mapping[str, AttributeValue]) -> None:
        """Export a pipe execution span."""
        properties = self._get_base_properties(span=span, attributes=attributes)

        # Get raw attribute values for redaction
        pipe_code = cast("str | None", attributes.get(PipelexSpanAttr.PIPE_CODE))
        pipe_type = cast("str | None", attributes.get(PipelexSpanAttr.PIPE_TYPE))

        # Build redacted span name
        # The trace name is established by a "trace start" event emitted at pipeline setup,
        # which ensures PostHog receives the correct trace name before any pipe spans arrive.
        redacted_span_name = self._build_redacted_pipe_span_name(
            original_span_name=span.name,
            pipe_type=pipe_type,
        )

        # Add pipeline_run_id (never redacted - useful for debugging and correlation)
        pipeline_run_id = attributes.get(PipelexSpanAttr.PIPELINE_RUN_ID)

        properties[PostHogAttr.SPAN_NAME] = redacted_span_name
        properties["pipe_type"] = pipe_type
        properties["pipe_category"] = attributes.get(PipelexSpanAttr.PIPE_CATEGORY)
        properties["outcome"] = attributes.get(PipelexSpanAttr.OUTCOME)
        properties["pipeline_run_id"] = pipeline_run_id

        # Apply pipe code redaction (only add if not None, for consistency)
        if redacted_pipe_code := self._get_redacted_pipe_code(pipe_code):
            properties["pipe_code"] = redacted_pipe_code
        log.verbose(
            f"[OTel->PostHog] EXPORT $ai_span:\n"
            f"  pipe_code='{properties.get('pipe_code')}'\n"
            f"  pipeline_run_id='{pipeline_run_id}'\n"
            f"  $ai_span_name='{redacted_span_name}'\n"
            f"  trace_id={properties.get(PostHogAttr.TRACE_ID)}\n"
            f"  span_id={properties.get(PostHogAttr.SPAN_ID)}\n"
            f"  parent_id={properties.get(PostHogAttr.PARENT_ID)}"
        )

        self._capture_event(event=PostHogEvent.SPAN, properties=properties)

    @override
    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        log.verbose(f"[OTel->PostHog] export() called with {len(spans)} span(s)")

        for span in spans:
            try:
                attributes = span.attributes or {}
                span_category_str = cast("str", attributes.get(PipelexSpanAttr.SPAN_CATEGORY))
                span_category = SpanCategory(span_category_str)

                span_ctx = span.get_span_context()
                parent_id = f"{span.parent.span_id:016x}" if span.parent else "None"
                trace_id_str = f"{span_ctx.trace_id:032x}" if span_ctx else "unknown"
                span_id_str = f"{span_ctx.span_id:016x}" if span_ctx else "unknown"
                pipe_code = attributes.get(PipelexSpanAttr.PIPE_CODE)
                pipeline_run_id = attributes.get(PipelexSpanAttr.PIPELINE_RUN_ID)
                trace_name = attributes.get(PipelexSpanAttr.TRACE_NAME)
                log.verbose(
                    f"[OTel->PostHog] Processing span:\n"
                    f"  trace_name='{trace_name}'\n"
                    f"  trace_id={trace_id_str}\n"
                    f"  span_id={span_id_str}\n"
                    f"  span_category={span_category}\n"
                    f"  pipeline_run_id='{pipeline_run_id}'\n"
                    f"  pipe_code='{pipe_code}'\n"
                    f"  parent_id={parent_id}"
                )

                match span_category:
                    case SpanCategory.INFERENCE:
                        self._export_generation_span(span=span, attributes=attributes)
                    case SpanCategory.PIPE:
                        self._export_pipe_span(span=span, attributes=attributes)

            except Exception as exc:
                # Fail silently to avoid breaking app
                log.debug(f"Failed to export span to PostHog: {exc}")

        return SpanExportResult.SUCCESS

    @override
    def shutdown(self) -> None:
        pass
