"""OpenTelemetry utilities for GenAI-compliant tracing.

This module provides helpers for instrumenting LLM operations with OpenTelemetry.
"""

import hashlib

from pipelex.system.telemetry.otel_constants import TRUNCATION_SUFFIX


def truncate_content_for_telemetry(content: str, max_length: int | None) -> str:
    """Truncate content for telemetry capture if it exceeds max length.

    Args:
        content: The content to potentially truncate.
        max_length: Maximum allowed length, or None for no limit.

    Returns:
        The original content if within limit, or truncated content with suffix.
    """
    if max_length is None or len(content) <= max_length:
        return content
    truncate_at = max(0, max_length - len(TRUNCATION_SUFFIX))
    return content[:truncate_at] + TRUNCATION_SUFFIX


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
