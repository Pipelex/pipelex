"""OpenTelemetry constants for GenAI-compliant tracing.

This module defines attribute keys used for instrumenting LLM operations
with OpenTelemetry, following the GenAI semantic conventions.
"""

from opentelemetry.semconv._incubating.attributes import gen_ai_attributes  # noqa: PLC2701

from pipelex.types import StrEnum


class GenAISpanAttr(StrEnum):
    """OpenTelemetry GenAI semantic convention attribute keys."""

    SYSTEM = gen_ai_attributes.GEN_AI_SYSTEM
    REQUEST_MODEL = gen_ai_attributes.GEN_AI_REQUEST_MODEL
    OPERATION_NAME = gen_ai_attributes.GEN_AI_OPERATION_NAME
    USAGE_INPUT_TOKENS = gen_ai_attributes.GEN_AI_USAGE_INPUT_TOKENS
    USAGE_OUTPUT_TOKENS = gen_ai_attributes.GEN_AI_USAGE_OUTPUT_TOKENS

    # Content attributes for PostHog compatibility (not in standard semconv)
    # PostHog UI expects these as span attributes, not events
    PROMPT_CONTENT = "gen_ai.prompt.0.content"
    COMPLETION_CONTENT = "gen_ai.completion.0.content"


# Virtual parent span ID for root spans.
# INVALID_SPAN_ID (0) makes SpanContext invalid, causing OTel to ignore our trace_id.
# Using 1 as virtual parent ensures OTel uses our deterministic trace_id while
# still treating the span as a root (we filter this out in the exporter).
VIRTUAL_ROOT_PARENT_SPAN_ID = 1
