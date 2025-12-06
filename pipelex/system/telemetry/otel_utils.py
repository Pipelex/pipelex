"""OpenTelemetry utilities for GenAI-compliant tracing.

This module provides constants and helpers for instrumenting LLM operations
with OpenTelemetry, following the GenAI semantic conventions for PostHog compatibility.
"""

from typing import TYPE_CHECKING, Any, Sequence

from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter, SpanExportResult
from opentelemetry.semconv._incubating.attributes import gen_ai_attributes  # noqa: PLC2701
from opentelemetry.trace import Tracer
from typing_extensions import override

from pipelex import log
from pipelex.tools.misc.package_utils import get_package_version

if TYPE_CHECKING:
    from posthog import Posthog


# Attribute keys from OpenTelemetry GenAI semantic conventions
GEN_AI_SYSTEM = gen_ai_attributes.GEN_AI_SYSTEM
GEN_AI_REQUEST_MODEL = gen_ai_attributes.GEN_AI_REQUEST_MODEL
GEN_AI_OPERATION_NAME = gen_ai_attributes.GEN_AI_OPERATION_NAME
GEN_AI_USAGE_INPUT_TOKENS = gen_ai_attributes.GEN_AI_USAGE_INPUT_TOKENS
GEN_AI_USAGE_OUTPUT_TOKENS = gen_ai_attributes.GEN_AI_USAGE_OUTPUT_TOKENS

# Content attributes for PostHog compatibility (not in standard semconv)
# PostHog UI expects these as span attributes, not events
GEN_AI_PROMPT_CONTENT = "gen_ai.prompt.0.content"
GEN_AI_COMPLETION_CONTENT = "gen_ai.completion.0.content"


class PostHogSpanExporter(SpanExporter):
    """Exports OTel spans to PostHog as $ai_generation events."""

    def __init__(self, posthog_client: "Posthog"):
        self.client = posthog_client

    @override
    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        for span in spans:
            try:
                # Only process spans that are GenAI operations
                attributes = span.attributes or {}
                if not attributes.get(GEN_AI_OPERATION_NAME):
                    continue

                properties: dict[str, Any] = {
                    "$ai_model": attributes.get(GEN_AI_REQUEST_MODEL),
                    "$ai_provider": attributes.get(GEN_AI_SYSTEM),
                    "$ai_input_tokens": attributes.get(GEN_AI_USAGE_INPUT_TOKENS),
                    "$ai_output_tokens": attributes.get(GEN_AI_USAGE_OUTPUT_TOKENS),
                    "$ai_latency": (span.end_time - span.start_time) / 1e9 if span.end_time and span.start_time else None,
                    "$ai_http_status": 200,  # Default to 200 OK for successful spans
                }

                # Add content if available
                if prompt := attributes.get(GEN_AI_PROMPT_CONTENT):
                    properties["$ai_input"] = prompt
                if completion := attributes.get(GEN_AI_COMPLETION_CONTENT):
                    properties["$ai_output_choices"] = [{"content": completion}]

                # Add trace/span IDs for PostHog trace grouping
                span_context = span.get_span_context()
                if span_context and span_context.is_valid:
                    properties["$ai_trace_id"] = f"{span_context.trace_id:032x}"
                    properties["$ai_span_id"] = f"{span_context.span_id:016x}"
                    properties["$ai_trace_name"] = attributes.get("pipelex.pipeline.run_id")

                # For parent, ReadableSpan typically has a 'parent' attribute which is a SpanContext
                if span.parent:
                    parent_id = f"{span.parent.span_id:016x}"
                    # Ignore virtual parent ID 1 (used for trace grouping)
                    if parent_id != "0000000000000001":
                        properties["$ai_parent_id"] = parent_id

                self.client.capture(
                    distinct_id="pipelex-user",  # TODO: get actual user ID
                    event="$ai_generation",
                    properties=properties,
                )
            except Exception as e:
                # Fail silently to avoid breaking app
                log.debug(f"Failed to export span to PostHog: {e}")

        return SpanExportResult.SUCCESS

    @override
    def shutdown(self) -> None:
        pass


def create_ai_tracer(
    posthog_client: "Posthog | None" = None,
    otlp_endpoint: str | None = None,
    otlp_headers: dict[str, str] | None = None,
) -> Tracer:
    """Create an isolated OpenTelemetry Tracer for GenAI instrumentation.

    This creates a dedicated TracerProvider that does NOT register itself as the
    global tracer to avoid polluting other traces in the host application.

    It can configure two types of exporters:
    1. PostHog Exporter: Converts spans to PostHog $ai_generation events
    2. OTLP Exporter: Sends standard OTLP traces to a collector

    Args:
        posthog_client: Optional PostHog client for sending events
        otlp_endpoint: Optional OTLP endpoint URL
        otlp_headers: Optional headers for OTLP export

    Returns:
        A configured Tracer instance for GenAI spans
    """
    # 1. Define Resource (Identity)
    resource = Resource.create(
        {
            "service.name": "pipelex-ai",
            "service.version": get_package_version(),
            "service.namespace": "ai.orchestration",
        }
    )

    # 2. Create Provider
    provider = TracerProvider(resource=resource)

    # 3. Add PostHog Exporter if client provided
    if posthog_client:
        ph_exporter = PostHogSpanExporter(posthog_client)
        provider.add_span_processor(BatchSpanProcessor(ph_exporter))

    # 4. Add Generic OTLP Exporter if endpoint provided
    if otlp_endpoint:
        otlp_exporter = OTLPSpanExporter(
            endpoint=otlp_endpoint,
            headers=otlp_headers or {},
        )
        provider.add_span_processor(BatchSpanProcessor(otlp_exporter))

    # 5. Get the Tracer
    return provider.get_tracer("pipelex", get_package_version())
