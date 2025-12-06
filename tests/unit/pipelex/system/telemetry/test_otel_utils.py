"""Unit tests for OTel utility functions."""

import pytest

from pipelex.system.telemetry.otel_utils import (
    generate_span_id,
    pipeline_run_id_to_trace_id,
)


class TestOtelUtils:
    """Test OTel ID generation utilities."""

    def test_generate_span_id_produces_16_char_hex(self) -> None:
        """Test that generate_span_id produces a valid 16-character hex string."""
        span_id = generate_span_id()

        assert len(span_id) == 16
        # Verify it's valid hex by converting to int
        int(span_id, 16)

    def test_generate_span_id_is_random(self) -> None:
        """Test that generate_span_id produces unique values."""
        span_ids = [generate_span_id() for _ in range(100)]

        # All should be unique
        assert len(set(span_ids)) == 100

    def test_generate_span_id_can_be_converted_to_int(self) -> None:
        """Test that generated span IDs can be converted to int and back."""
        span_id = generate_span_id()

        span_id_int = int(span_id, 16)
        # Convert back to hex (with leading zeros)
        span_id_back = f"{span_id_int:016x}"

        assert span_id_back == span_id

    def test_pipeline_run_id_to_trace_id_is_deterministic(self) -> None:
        """Test that pipeline_run_id_to_trace_id produces consistent trace IDs."""
        pipeline_run_id = "my_pipe_abc123xyz"

        trace_id_1 = pipeline_run_id_to_trace_id(pipeline_run_id)
        trace_id_2 = pipeline_run_id_to_trace_id(pipeline_run_id)

        assert trace_id_1 == trace_id_2

    def test_pipeline_run_id_to_trace_id_produces_128_bit_int(self) -> None:
        """Test that pipeline_run_id_to_trace_id produces a valid 128-bit integer."""
        pipeline_run_id = "test_pipeline_run_id"

        trace_id = pipeline_run_id_to_trace_id(pipeline_run_id)

        # Should be a positive integer that fits in 128 bits
        assert isinstance(trace_id, int)
        assert trace_id > 0
        assert trace_id.bit_length() <= 128

    def test_pipeline_run_id_to_trace_id_different_inputs_produce_different_outputs(self) -> None:
        """Test that different pipeline_run_ids produce different trace IDs."""
        trace_id_1 = pipeline_run_id_to_trace_id("pipeline_a")
        trace_id_2 = pipeline_run_id_to_trace_id("pipeline_b")

        assert trace_id_1 != trace_id_2

    @pytest.mark.parametrize(
        "pipeline_run_id",
        [
            "simple_id",
            "pipe_with_numbers_123",
            "UPPERCASE_ID",
            "mixed_Case_Id",
            "id-with-dashes",
            "id.with.dots",
            "a",  # Very short
            "a" * 1000,  # Very long
        ],
    )
    def test_pipeline_run_id_to_trace_id_handles_various_formats(self, pipeline_run_id: str) -> None:
        """Test that pipeline_run_id_to_trace_id handles various input formats."""
        trace_id = pipeline_run_id_to_trace_id(pipeline_run_id)

        assert isinstance(trace_id, int)
        assert trace_id > 0
        assert trace_id.bit_length() <= 128
