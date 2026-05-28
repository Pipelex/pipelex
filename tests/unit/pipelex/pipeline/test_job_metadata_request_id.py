"""Unit tests for ``JobMetadata.request_id`` — the API-inbound ``X-Request-ID``
that rides the workflow input across the Temporal serialization boundary.
"""

import pytest
from pydantic import ValidationError

from pipelex.pipeline.job_metadata import JobMetadata


class TestJobMetadataRequestId:
    def test_request_id_defaults_to_none(self) -> None:
        """``JobMetadata`` constructed without ``request_id`` carries ``None``."""
        meta = JobMetadata(user_id="u", pipeline_run_id="r")
        assert meta.request_id is None

    def test_request_id_round_trips_through_json(self) -> None:
        """``request_id`` survives ``model_dump_json`` / ``model_validate_json`` round-trip.

        Temporal's data converter serializes activity args as JSON; this pins
        the contract that ``request_id`` reaches the worker intact.
        """
        meta = JobMetadata(user_id="u", pipeline_run_id="r", request_id="r-abc-123")
        recovered = JobMetadata.model_validate_json(meta.model_dump_json())
        assert recovered.request_id == "r-abc-123"
        assert recovered == meta

    def test_copy_with_update_preserves_request_id(self) -> None:
        """``copy_with_update`` inherits ``request_id`` from the parent metadata."""
        parent = JobMetadata(user_id="u", pipeline_run_id="r", request_id="r-1")
        child = parent.copy_with_update(otel_context=None)
        assert child.request_id == "r-1"

    @pytest.mark.parametrize(
        "bad_request_id",
        [
            "abc\ndef",  # newline (CRLF log injection)
            "abc\rdef",  # carriage return
            "abc\x1b[31mfake",  # ANSI escape (log forgery)
            "abc\x00def",  # NUL byte
            "abc\tdef",  # tab (outside printable ASCII range)
            "café",  # non-ASCII (latin-1 supplement)
            "x" * 129,  # exceeds max_length=128
        ],
    )
    def test_request_id_rejects_unsanitized_input(self, bad_request_id: str) -> None:
        """``request_id`` is constrained to printable ASCII (max 128 chars).

        Defense-in-depth: an upstream consumer of pipelex that forwards the
        ``X-Request-ID`` header without sanitization cannot inject newlines,
        ANSI escapes, or control characters into the log lines and
        ``ErrorReport`` envelopes that quote it.
        """
        with pytest.raises(ValidationError):
            JobMetadata(user_id="u", pipeline_run_id="r", request_id=bad_request_id)

    @pytest.mark.parametrize(
        "good_request_id",
        [
            "abc-123",
            "11111111-2222-3333-4444-555555555555",  # uuid
            "req_abc.123",
            "x" * 128,  # at the limit
        ],
    )
    def test_request_id_accepts_well_formed_input(self, good_request_id: str) -> None:
        """Common ``X-Request-ID`` shapes (UUID, hyphenated, dot-separated) round-trip cleanly."""
        meta = JobMetadata(user_id="u", pipeline_run_id="r", request_id=good_request_id)
        assert meta.request_id == good_request_id
