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


class PostHogSpanExporter(SpanExporter):
    """Exports OTel spans to PostHog as $ai_generation or $ai_span events."""

    def __init__(self, posthog_client: Posthog, distinct_id: str | None):
        self.client = posthog_client
        self.distinct_id = distinct_id

    def _capture_event(self, event: PostHogEvent, properties: dict[str, Any]) -> None:
        """Capture an event to PostHog, handling anonymous vs identified users.

        PostHog requires a valid distinct_id - passing None will cause the event to be rejected.
        For anonymous tracking, we omit distinct_id and set $process_person_profile=False.
        """
        if self.distinct_id:
            # Identified user: pass distinct_id
            self.client.capture(
                distinct_id=self.distinct_id,
                event=event,
                properties=properties,
            )
        else:
            # Anonymous user: don't pass distinct_id, mark as anonymous
            properties[PostHogAttr.PROCESS_PERSON_PROFILE] = False
            self.client.capture(
                event=event,
                properties=properties,
            )

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
        properties.update(
            {
                PostHogAttr.MODEL: attributes.get(GenAISpanAttr.REQUEST_MODEL),
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

        pipe_code = attributes.get(PipelexSpanAttr.PIPE_CODE)
        pipeline_run_id = attributes.get(PipelexSpanAttr.PIPELINE_RUN_ID)
        log.verbose(
            f"[OTel->PostHog] EXPORT $ai_generation:\n"
            f"  pipe_code='{pipe_code}'\n"
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
        log.verbose(
            f"[OTel->PostHog] EXPORT $ai_span:\n"
            f"  pipe_code='{pipe_code}'\n"
            f"  pipeline_run_id='{pipeline_run_id}'\n"
            f"  $ai_span_name='{span.name}'\n"
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
