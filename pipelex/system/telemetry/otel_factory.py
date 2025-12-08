"""OpenTelemetry utilities for GenAI-compliant tracing.

This module provides helpers for instrumenting LLM operations with OpenTelemetry.
"""

import hashlib

from pipelex.system.telemetry.otel_constants import TRUNCATION_SUFFIX
from pipelex.system.telemetry.telemetry_manager_abstract import TelemetryManagerAbstract


class OtelFactory:
    @classmethod
    def make_truncated_content(cls, content: str, max_length: int | None) -> str:
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

    @classmethod
    def make_trace_id(cls, pipeline_run_id: str) -> int:
        """Convert pipeline_run_id to a 128-bit OTel trace ID (deterministic).

        Uses MD5 hash to generate a consistent trace ID from the pipeline_run_id.
        This ensures all spans within the same pipeline run share the same trace ID.

        Args:
            pipeline_run_id: The pipeline run identifier string.

        Returns:
            A 128-bit integer suitable for use as an OTel trace ID.
        """
        return int(hashlib.md5(pipeline_run_id.encode("utf-8")).hexdigest(), 16)  # noqa: S324

    @classmethod
    def make_trace_name(cls, pipeline_run_id: str, pipe_code: str) -> str:
        """Create a trace name from pipeline run ID and optional pipe code.

        Args:
            pipeline_run_id: The pipeline run identifier string.
            pipe_code: pipe code to include in the trace name or not.

        Returns:
            A trace name combining the pipe code (if enabled) with a short deterministic
            hash of the pipeline run ID.
        """
        hashed_id = hashlib.md5(pipeline_run_id.encode("utf-8")).hexdigest()[:8]  # noqa: S324
        if TelemetryManagerAbstract.is_capture_pipe_codes_enabled():
            return f"{pipe_code}_{hashed_id}"
        else:
            return hashed_id
