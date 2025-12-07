"""OpenTelemetry constants for GenAI-compliant tracing.

This module defines attribute keys used for instrumenting LLM operations
with OpenTelemetry, following the GenAI semantic conventions.
"""

from opentelemetry.semconv._incubating.attributes import gen_ai_attributes as otel_gen_ai_attributes  # noqa: PLC2701

from pipelex.types import StrEnum


class GenAISpanAttr(StrEnum):
    """OpenTelemetry GenAI semantic convention attribute keys."""

    SYSTEM = otel_gen_ai_attributes.GEN_AI_SYSTEM
    REQUEST_MODEL = otel_gen_ai_attributes.GEN_AI_REQUEST_MODEL
    OPERATION_NAME = otel_gen_ai_attributes.GEN_AI_OPERATION_NAME
    USAGE_INPUT_TOKENS = otel_gen_ai_attributes.GEN_AI_USAGE_INPUT_TOKENS
    USAGE_OUTPUT_TOKENS = otel_gen_ai_attributes.GEN_AI_USAGE_OUTPUT_TOKENS

    # Content attributes for PostHog compatibility (not in standard semconv)
    # PostHog UI expects these as span attributes, not events
    PROMPT_CONTENT = "gen_ai.prompt.0.content"
    COMPLETION_CONTENT = "gen_ai.completion.0.content"


# Virtual parent span ID for root spans.
# INVALID_SPAN_ID (0) makes SpanContext invalid, causing OTel to ignore our trace_id.
# Using 1 as virtual parent ensures OTel uses our deterministic trace_id while
# still treating the span as a root (we filter this out in the exporter).
VIRTUAL_ROOT_PARENT_SPAN_ID = 1


class OTelConstants(StrEnum):
    """OpenTelemetry constants."""

    DEFAULT_USER_ID = "anonymous"
    SERVICE_NAME = "pipelex"
    SERVICE_NAMESPACE_KEY = "service.namespace"
    SERVICE_NAMESPACE = "ai.orchestration"
    INSTRUMENTATION_NAME = "pipelex"
