"""Unit tests for ``RunMetadata.request_id`` — the API-inbound ``X-Request-ID``
that rides the workflow input across the Temporal serialization boundary,
reached from a ``JobMetadata`` through its ``run_metadata``.
"""

import pytest
from pydantic import ValidationError

from pipelex.system.job_metadata import JobMetadata, RunMetadata


class TestJobMetadataRequestId:
    def test_request_id_defaults_to_none(self) -> None:
        """A ``RunMetadata`` constructed without ``request_id`` carries ``None``."""
        meta = JobMetadata(run_metadata=RunMetadata(storage_scope="test/scope", read_scope=None, user_id="u", pipeline_run_id="r"))
        assert meta.run_metadata.request_id is None

    def test_request_id_round_trips_through_json(self) -> None:
        """``request_id`` survives ``model_dump_json`` / ``model_validate_json`` round-trip.

        Temporal's data converter serializes activity args as JSON; this pins
        the contract that ``request_id`` reaches the worker intact.
        """
        meta = JobMetadata(
            run_metadata=RunMetadata(storage_scope="test/scope", read_scope=None, user_id="u", pipeline_run_id="r", request_id="r-abc-123")
        )
        recovered = JobMetadata.model_validate_json(meta.model_dump_json())
        assert recovered.run_metadata.request_id == "r-abc-123"
        assert recovered == meta

    def test_copy_with_update_preserves_request_id(self) -> None:
        """``copy_with_update`` inherits ``request_id`` from the parent metadata."""
        parent = JobMetadata(
            run_metadata=RunMetadata(storage_scope="test/scope", read_scope=None, user_id="u", pipeline_run_id="r", request_id="r-1")
        )
        child = parent.copy_with_update(otel_context=None)
        assert child.run_metadata.request_id == "r-1"

    @pytest.mark.parametrize(
        "bad_request_id",
        [
            "abc\ndef",  # newline (CRLF log injection)
            "abc\n",  # trailing newline (a `$` anchor under `re.match` would admit it)
            "",  # empty
            "abc\rdef",  # carriage return
            "abc\x1b[31mfake",  # ANSI escape (log forgery)
            "abc\x00def",  # NUL byte
            "abc\tdef",  # tab (outside printable ASCII range)
            "café",  # non-ASCII (latin-1 supplement)
            "x" * 129,  # exceeds max_length=128
            " ",  # a space alone, which a header trims to nothing
            "abc def",  # a space, which splits a key=value log line
            "abc error.code=forged",  # a forged field of a key=value log line
            'abc"def',  # a quote, which closes a quoted value
            "abc;q=1",  # a header parameter
            "req_abc.123",  # a dot: outside the one rule the API server's middleware applies too
        ],
    )
    def test_request_id_rejects_unsanitized_input(self, bad_request_id: str) -> None:
        """``request_id`` holds ASCII letters, digits, ``_`` and ``-`` alone (max 128 chars).

        Defense-in-depth: an upstream consumer of pipelex that forwards the
        ``X-Request-ID`` header without sanitization cannot inject a line, a
        field or a header parameter into the log lines, the headers and the
        problem documents that carry it.
        """
        with pytest.raises(ValidationError):
            JobMetadata(
                run_metadata=RunMetadata(storage_scope="test/scope", read_scope=None, user_id="u", pipeline_run_id="r", request_id=bad_request_id)
            )

    @pytest.mark.parametrize(
        "good_request_id",
        [
            "abc-123",
            "11111111-2222-3333-4444-555555555555",  # uuid
            "01JA2B3C4D5E6F7G8H9J0K1M2N",  # ulid
            "req_abc_123",
            "x" * 128,  # at the limit
        ],
    )
    def test_request_id_accepts_well_formed_input(self, good_request_id: str) -> None:
        """Common ``X-Request-ID`` shapes (UUID, ULID, hyphenated, underscored) round-trip cleanly."""
        meta = JobMetadata(
            run_metadata=RunMetadata(storage_scope="test/scope", read_scope=None, user_id="u", pipeline_run_id="r", request_id=good_request_id)
        )
        assert meta.run_metadata.request_id == good_request_id
