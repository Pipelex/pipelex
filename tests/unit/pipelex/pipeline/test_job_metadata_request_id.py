"""Unit tests for ``JobMetadata.request_id`` — the API-inbound ``X-Request-ID``
that rides the workflow input across the Temporal serialization boundary.
"""

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
