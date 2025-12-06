"""OpenTelemetry utilities for GenAI-compliant tracing.

This module provides constants and helpers for instrumenting LLM operations
with OpenTelemetry, following the GenAI semantic conventions for PostHog compatibility.
"""

import hashlib
import secrets
from typing import TYPE_CHECKING, Any, Mapping, Sequence

from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter, SpanExportResult
from opentelemetry.semconv._incubating.attributes import gen_ai_attributes  # noqa: PLC2701
from opentelemetry.trace import Tracer
from opentelemetry.util.types import AttributeValue
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

# Pipelex-specific span attributes for workflow tracing
PIPELEX_PIPE_CODE = "pipelex.pipe.code"
PIPELEX_PIPE_TYPE = "pipelex.pipe.type"
PIPELEX_PIPE_CATEGORY = "pipelex.pipe.category"
PIPELEX_PIPELINE_RUN_ID = "pipelex.pipeline.run_id"
PIPELEX_SPAN_KIND = "pipelex.span.kind"  # "pipe" or "inference"


#########################################################
# OTel ID Generation Utilities
#########################################################

# Virtual parent span ID for root spans.
# INVALID_SPAN_ID (0) makes SpanContext invalid, causing OTel to ignore our trace_id.
# Using 1 as virtual parent ensures OTel uses our deterministic trace_id while
# still treating the span as a root (we filter this out in the exporter).
VIRTUAL_ROOT_PARENT_SPAN_ID = 1


def generate_span_id() -> str:
    """Generate a 64-bit span ID as a 16-char hex string.

    Returns:
        A cryptographically random 16-character hexadecimal string
        suitable for use as an OTel span ID.
    """
    return secrets.token_hex(8)


def pipeline_run_id_to_trace_id(pipeline_run_id: str) -> int:
    """Convert pipeline_run_id to a 128-bit OTel trace ID (deterministic).

    Uses MD5 hash to generate a consistent trace ID from the pipeline_run_id.
    This ensures all spans within the same pipeline run share the same trace ID.

    Args:
        pipeline_run_id: The pipeline run identifier string.

    Returns:
        A 128-bit integer suitable for use as an OTel trace ID.
    """
    return int(hashlib.md5(pipeline_run_id.encode("utf-8")).hexdigest(), 16)  # noqa: S324


#########################################################
# Global Tracer Accessor (avoids circular imports)
#########################################################

# Module-level tracer reference, set by TelemetryManager during initialization
_global_tracer: Tracer | None = None


def set_global_tracer(tracer: Tracer | None) -> None:
    """Set the global tracer. Called by TelemetryManager during setup."""
    global _global_tracer  # noqa: PLW0603
    _global_tracer = tracer


def get_global_tracer() -> Tracer | None:
    """Get the global tracer for OTel instrumentation.

    This avoids circular imports by not depending on the hub module.
    """
    return _global_tracer


class PostHogSpanExporter(SpanExporter):
    """Exports OTel spans to PostHog as $ai_generation or $ai_span events."""

    def __init__(self, posthog_client: "Posthog"):
        self.client = posthog_client

    def _get_base_properties(self, span: ReadableSpan, attributes: Mapping[str, AttributeValue]) -> dict[str, Any]:
        """Get common properties for all span types."""
        properties: dict[str, Any] = {
            "$ai_latency": (span.end_time - span.start_time) / 1e9 if span.end_time and span.start_time else None,
        }

        # Add trace/span IDs for PostHog trace grouping
        span_context = span.get_span_context()
        if span_context and span_context.is_valid:
            properties["$ai_trace_id"] = f"{span_context.trace_id:032x}"
            properties["$ai_span_id"] = f"{span_context.span_id:016x}"
            properties["$ai_trace_name"] = attributes.get(PIPELEX_PIPELINE_RUN_ID)

        # Add parent span ID for trace hierarchy
        # Filter out virtual root parent (used to set trace_id for root spans)
        if span.parent and span.parent.span_id != VIRTUAL_ROOT_PARENT_SPAN_ID:
            properties["$ai_parent_id"] = f"{span.parent.span_id:016x}"

        return properties

    def _export_generation_span(self, span: ReadableSpan, attributes: Mapping[str, AttributeValue]) -> None:
        """Export a GenAI generation span."""
        properties = self._get_base_properties(span, attributes)
        properties.update(
            {
                "$ai_model": attributes.get(GEN_AI_REQUEST_MODEL),
                "$ai_provider": attributes.get(GEN_AI_SYSTEM),
                "$ai_input_tokens": attributes.get(GEN_AI_USAGE_INPUT_TOKENS),
                "$ai_output_tokens": attributes.get(GEN_AI_USAGE_OUTPUT_TOKENS),
                "$ai_http_status": 200,
            }
        )

        # Add content if available
        if prompt := attributes.get(GEN_AI_PROMPT_CONTENT):
            properties["$ai_input"] = prompt
        if completion := attributes.get(GEN_AI_COMPLETION_CONTENT):
            properties["$ai_output_choices"] = [{"content": completion}]

        log.dev(
            f"[OTel->PostHog] EXPORT $ai_generation: "
            f"trace_id={properties.get('$ai_trace_id')} span_id={properties.get('$ai_span_id')} "
            f"parent_id={properties.get('$ai_parent_id')} model={properties.get('$ai_model')}"
        )

        self.client.capture(
            distinct_id="pipelex-user",  # TODO: get actual user ID
            event="$ai_generation",
            properties=properties,
        )

    def _export_pipe_span(self, span: ReadableSpan, attributes: Mapping[str, AttributeValue]) -> None:
        """Export a pipe execution span."""
        properties = self._get_base_properties(span, attributes)
        properties.update(
            {
                "$ai_span_name": span.name,
                "pipe_code": attributes.get(PIPELEX_PIPE_CODE),
                "pipe_type": attributes.get(PIPELEX_PIPE_TYPE),
                "pipe_category": attributes.get(PIPELEX_PIPE_CATEGORY),
            }
        )

        log.dev(
            f"[OTel->PostHog] EXPORT $ai_span: "
            f"trace_id={properties.get('$ai_trace_id')} span_id={properties.get('$ai_span_id')} "
            f"parent_id={properties.get('$ai_parent_id')} name={span.name}"
        )

        self.client.capture(
            distinct_id="pipelex-user",  # TODO: get actual user ID
            event="$ai_span",
            properties=properties,
        )

    @override
    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        log.dev(f"[OTel->PostHog] export() called with {len(spans)} span(s)")

        for span in spans:
            try:
                attributes = span.attributes or {}
                span_kind = attributes.get(PIPELEX_SPAN_KIND)

                span_ctx = span.get_span_context()
                parent_id = f"{span.parent.span_id:016x}" if span.parent else "None"
                trace_id_str = f"{span_ctx.trace_id:032x}" if span_ctx else "unknown"
                span_id_str = f"{span_ctx.span_id:016x}" if span_ctx else "unknown"
                log.dev(
                    f"[OTel->PostHog] Processing span: name='{span.name}' kind={span_kind} "
                    f"trace_id={trace_id_str} span_id={span_id_str} parent_id={parent_id}"
                )

                # Route to appropriate exporter based on span kind
                if attributes.get(GEN_AI_OPERATION_NAME):
                    # GenAI (LLM) span
                    self._export_generation_span(span, attributes)
                elif span_kind == "pipe":
                    # Pipe execution span
                    self._export_pipe_span(span, attributes)
                else:
                    log.dev(f"[OTel->PostHog] SKIPPING span (unknown kind): {span.name}")

            except Exception as exc:
                # Fail silently to avoid breaking app
                log.debug(f"Failed to export span to PostHog: {exc}")

        return SpanExportResult.SUCCESS

    @override
    def shutdown(self) -> None:
        pass


def create_ai_tracer(
    posthog_client: "Posthog | None" = None,
    otlp_endpoint: str | None = None,
    otlp_headers: dict[str, str] | None = None,
) -> tuple[Tracer, TracerProvider]:
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
        A tuple of (Tracer, TracerProvider). The caller should call
        provider.shutdown() during teardown to flush pending spans.
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

    # 5. Get the Tracer and return both tracer and provider
    tracer = provider.get_tracer("pipelex", get_package_version())
    return tracer, provider
