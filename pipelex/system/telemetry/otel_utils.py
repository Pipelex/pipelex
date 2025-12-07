"""OpenTelemetry utilities for GenAI-compliant tracing.

This module provides helpers for instrumenting LLM operations with OpenTelemetry.
"""

import hashlib


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
