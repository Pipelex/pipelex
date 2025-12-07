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
from pipelex.system.telemetry.otel_constants import OTEL_VIRTUAL_ROOT_PARENT_SPAN_ID, GenAISpanAttr, PostHogAttr, PostHogEvent
from pipelex.system.telemetry.telemetry_constants import PipelexSpanAttr, SpanCategory


class PostHogSpanExporter(SpanExporter):
    """Exports OTel spans to PostHog as $ai_generation or $ai_span events."""

    def __init__(self, posthog_client: Posthog, user_id: str):
        self.client = posthog_client
        self.user_id = user_id

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
            properties[PostHogAttr.TRACE_NAME] = attributes.get(PipelexSpanAttr.PIPELINE_RUN_ID)

        # Add parent span ID for trace hierarchy
        # Filter out virtual root parent (used to set trace_id for root spans)
        if span.parent and span.parent.span_id != OTEL_VIRTUAL_ROOT_PARENT_SPAN_ID:
            properties[PostHogAttr.PARENT_ID] = f"{span.parent.span_id:016x}"

        return properties

    def _export_generation_span(self, span: ReadableSpan, attributes: Mapping[str, AttributeValue]) -> None:
        """Export a GenAI generation span."""
        properties = self._get_base_properties(span=span, attributes=attributes)
        provider_operation_combo = f"{attributes.get(GenAISpanAttr.PROVIDER_NAME)}:{attributes.get(GenAISpanAttr.OPERATION_NAME)}"
        properties.update(
            {
                PostHogAttr.MODEL: attributes.get(GenAISpanAttr.REQUEST_MODEL),
                PostHogAttr.PROVIDER: provider_operation_combo,
                PostHogAttr.INPUT_TOKENS: attributes.get(GenAISpanAttr.USAGE_INPUT_TOKENS),
                PostHogAttr.OUTPUT_TOKENS: attributes.get(GenAISpanAttr.USAGE_OUTPUT_TOKENS),
                PostHogAttr.HTTP_STATUS: 200,
            }
        )

        # Add content if available
        if prompt := attributes.get(GenAISpanAttr.PROMPT_CONTENT):
            properties[PostHogAttr.INPUT] = prompt
        if completion := attributes.get(GenAISpanAttr.COMPLETION_CONTENT):
            properties[PostHogAttr.OUTPUT_CHOICES] = [{"content": completion}]

        pipe_code = attributes.get(PipelexSpanAttr.PIPE_CODE)
        pipeline_run_id = attributes.get(PipelexSpanAttr.PIPELINE_RUN_ID)
        log.dev(
            f"[OTel->PostHog] EXPORT $ai_generation:\n"
            f"  pipe_code='{pipe_code}'\n"
            f"  pipeline_run_id='{pipeline_run_id}'\n"
            f"  trace_id={properties.get(PostHogAttr.TRACE_ID)}\n"
            f"  span_id={properties.get(PostHogAttr.SPAN_ID)}\n"
            f"  parent_id={properties.get(PostHogAttr.PARENT_ID)}\n"
            f"  model={properties.get(PostHogAttr.MODEL)}"
        )

        self.client.capture(
            distinct_id=self.user_id,
            event=PostHogEvent.GENERATION,
            properties=properties,
        )

    def _export_pipe_span(self, span: ReadableSpan, attributes: Mapping[str, AttributeValue]) -> None:
        """Export a pipe execution span."""
        properties = self._get_base_properties(span, attributes)

        # Use the original span.name for $ai_span_name
        # The trace name is established by a "trace start" event emitted at pipeline setup,
        # which ensures PostHog receives the correct trace name before any pipe spans arrive.
        properties.update(
            {
                PostHogAttr.SPAN_NAME: span.name,
                "pipe_code": attributes.get(PipelexSpanAttr.PIPE_CODE),
                "pipe_type": attributes.get(PipelexSpanAttr.PIPE_TYPE),
                "pipe_category": attributes.get(PipelexSpanAttr.PIPE_CATEGORY),
                "outcome": attributes.get(PipelexSpanAttr.OUTCOME),
            }
        )

        pipe_code = attributes.get(PipelexSpanAttr.PIPE_CODE)
        pipeline_run_id = attributes.get(PipelexSpanAttr.PIPELINE_RUN_ID)
        log.dev(
            f"[OTel->PostHog] EXPORT $ai_span:\n"
            f"  pipe_code='{pipe_code}'\n"
            f"  pipeline_run_id='{pipeline_run_id}'\n"
            f"  $ai_span_name='{span.name}'\n"
            f"  trace_id={properties.get(PostHogAttr.TRACE_ID)}\n"
            f"  span_id={properties.get(PostHogAttr.SPAN_ID)}\n"
            f"  parent_id={properties.get(PostHogAttr.PARENT_ID)}"
        )

        self.client.capture(
            distinct_id=self.user_id,
            event=PostHogEvent.SPAN,
            properties=properties,
        )

    @override
    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        log.dev(f"[OTel->PostHog] export() called with {len(spans)} span(s)")

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
                log.dev(
                    f"[OTel->PostHog] Processing span:\n"
                    f"  pipe_code='{pipe_code}'\n"
                    f"  pipeline_run_id='{pipeline_run_id}'\n"
                    f"  span_category={span_category}\n"
                    f"  trace_id={trace_id_str}\n"
                    f"  span_id={span_id_str}\n"
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
