"""Unit tests for OTel utility functions."""

import json

import pytest

from pipelex.core.memory.absence import AbsenceKind, AbsenceRecord
from pipelex.core.memory.exceptions import WorkingMemoryStuffNotFoundError
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.system.telemetry.otel_factory import OtelFactory


class TestOtelFactory:
    """Test OTel factory utilities."""

    # --- make_output_json tests ---

    def test_make_output_json_absent_main_output(self) -> None:
        """An absent main output serializes to an explicit absence payload — the span ends
        successfully, never raises (a completed run always resolves its declared output).
        """
        memory = WorkingMemory()
        memory.record_new_main_absence(
            AbsenceRecord(
                variable_name="summary",
                kind=AbsenceKind.SKIPPED,
                reason="skipped because input 'analysis' is absent",
                producing_pipe="summarize",
            )
        )
        pipe_output = PipeOutput(working_memory=memory, pipeline_run_id="run-absent")

        output_json = OtelFactory.make_output_json(pipe_output=pipe_output, max_length=None)

        payload = json.loads(output_json)
        assert payload["absent"] is True
        assert payload["variable_name"] == "summary"
        assert payload["kind"] == "skipped"
        assert payload["reason"] == "skipped because input 'analysis' is absent"

    # --- make_inputs_json tests ---

    def test_make_inputs_json_captures_recorded_absence(self) -> None:
        """An input slot resolved as a recorded absence captures as the explicit absence
        payload — a legitimately omitted optional never breaks span input capture.
        """
        memory = WorkingMemoryFactory.make_from_single_stuff(StuffFactory.make_from_str("penalties", name="topic"))
        memory.record_absence(
            AbsenceRecord(
                variable_name="clause",
                kind=AbsenceKind.NOT_PROVIDED,
                reason="optional input 'clause' was not provided by the caller",
            )
        )

        inputs_json = OtelFactory.make_inputs_json(memory, needed_input_names={"topic", "clause"}, max_length=None)

        payload = json.loads(inputs_json)
        assert payload["topic"]["content"] == {"text": "penalties"}
        assert payload["clause"]["absent"] is True
        assert payload["clause"]["kind"] == "not_provided"

    def test_make_inputs_json_neither_value_nor_record_raises(self) -> None:
        """A slot with neither a value nor a recorded absence is the bug case — the capture
        raises loudly instead of silently omitting the input.
        """
        memory = WorkingMemory()

        with pytest.raises(WorkingMemoryStuffNotFoundError):
            OtelFactory.make_inputs_json(memory, needed_input_names={"ghost"}, max_length=None)

    # --- make_truncated_content tests ---

    def test_make_truncated_content_no_truncation_when_within_limit(self) -> None:
        """Test that content within limit is returned unchanged."""
        content = "short content"
        result = OtelFactory.make_truncated_content(content, max_length=100)
        assert result == content

    def test_make_truncated_content_truncates_when_exceeds_limit(self) -> None:
        """Test that content exceeding limit is truncated with suffix."""
        content = "a" * 50
        result = OtelFactory.make_truncated_content(content, max_length=20)
        assert result.endswith("... [truncated]")
        assert len(result) <= 20

    def test_make_truncated_content_no_limit_when_max_length_is_none(self) -> None:
        """Test that None max_length means no truncation."""
        content = "a" * 10000
        result = OtelFactory.make_truncated_content(content, max_length=None)
        assert result == content

    # --- make_trace_id tests ---

    def test_pipeline_run_id_to_trace_id_is_deterministic(self) -> None:
        """Test that pipeline_run_id_to_trace_id produces consistent trace IDs."""
        pipeline_run_id = "my_pipe_abc123xyz"

        trace_id_1 = OtelFactory.make_trace_id(pipeline_run_id)
        trace_id_2 = OtelFactory.make_trace_id(pipeline_run_id)

        assert trace_id_1 == trace_id_2

    def test_pipeline_run_id_to_trace_id_produces_128_bit_int(self) -> None:
        """Test that pipeline_run_id_to_trace_id produces a valid 128-bit integer."""
        pipeline_run_id = "test_pipeline_run_id"

        trace_id = OtelFactory.make_trace_id(pipeline_run_id)

        # Should be a positive integer that fits in 128 bits
        assert isinstance(trace_id, int)
        assert trace_id > 0
        assert trace_id.bit_length() <= 128

    def test_pipeline_run_id_to_trace_id_different_inputs_produce_different_outputs(self) -> None:
        """Test that different pipeline_run_ids produce different trace IDs."""
        trace_id_1 = OtelFactory.make_trace_id("pipeline_a")
        trace_id_2 = OtelFactory.make_trace_id("pipeline_b")

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
        trace_id = OtelFactory.make_trace_id(pipeline_run_id)

        assert isinstance(trace_id, int)
        assert trace_id > 0
        assert trace_id.bit_length() <= 128

    # --- make_trace_names tests ---

    def test_make_trace_names_returns_full_and_redacted(self) -> None:
        """Test that make_trace_names returns both full and redacted trace names."""
        trace_name, trace_name_redacted = OtelFactory.make_trace_names("run_123", pipe_code="my_pipe")

        # Full trace name should include pipe code
        assert trace_name.startswith("my_pipe_")
        assert len(trace_name) == len("my_pipe_") + 8  # pipe_code + underscore + 8-char hash

        # Redacted trace name should just be the hash
        assert "my_pipe" not in trace_name_redacted
        assert len(trace_name_redacted) == 8  # just the 8-char hash

        # Both should share the same hash suffix
        assert trace_name.endswith(trace_name_redacted)
