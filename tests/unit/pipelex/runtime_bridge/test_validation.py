import pytest

from pipelex.libraries.library_crate import LibraryCrate
from pipelex.pipe_run.delivery_assignment import DeliveryAssignment
from pipelex.runtime_bridge.bridge import (
    PipelexPipeRunInput,
    _decode_delivery_assignment,  # noqa: PLC2701  # pyright: ignore[reportPrivateUsage]
    _decode_library_crate,  # noqa: PLC2701  # pyright: ignore[reportPrivateUsage]
    _validate_input,  # noqa: PLC2701  # pyright: ignore[reportPrivateUsage]
    run_pipe_via_bridge,
)
from pipelex.runtime_bridge.delivery_mode import DeliveryMode
from pipelex.runtime_bridge.direct_orchestrator import DirectOrchestrator
from pipelex.runtime_bridge.exceptions import PipelexBridgeDispatchError
from pipelex.runtime_bridge.payloads import PipelexPipeRunOutput


class _AsyncCapableOrchestrator:
    """Async-capable stand-in: _validate_input reads only supports_fire_and_forget (run is never called)."""

    supports_fire_and_forget = True

    async def run(self, *, pipe_job: object, delivery_assignment: object, delivery: DeliveryMode) -> PipelexPipeRunOutput:  # noqa: ARG002
        # _validate_input never dispatches; this body exists only to satisfy OrchestratorProtocol.
        return PipelexPipeRunOutput(
            output_dict={},
            main_stuff_name=None,
            pipeline_run_id="fake-run",
            workflow_id="fake-wf",
            is_completed=False,
            graph_spec_dump=None,
        )


class TestBridgeValidationAndDecoding:
    def test_validate_input_passes_for_blocking_without_delivery(self):
        # Delivery, not orchestration mode, gates the delivery-target requirement: a BLOCKING
        # call needs no target regardless of which orchestrator runs it (even a blocking-only one).
        payload = PipelexPipeRunInput(pipe_code="any", orchestration_mode="direct", delivery=DeliveryMode.BLOCKING)
        _validate_input(
            payload, orchestrator=DirectOrchestrator(), delivery_assignment=_decode_delivery_assignment(payload.delivery_assignment_dump)
        )  # must not raise

    def test_validate_input_passes_for_temporal_blocking_without_delivery(self):
        payload = PipelexPipeRunInput(pipe_code="any", orchestration_mode="temporal", delivery=DeliveryMode.BLOCKING)
        _validate_input(
            payload, orchestrator=_AsyncCapableOrchestrator(), delivery_assignment=_decode_delivery_assignment(payload.delivery_assignment_dump)
        )  # must not raise

    def test_validate_input_rejects_fire_and_forget_on_blocking_only_orchestrator(self):
        # The capability gate fires before the delivery-target gate: a blocking-only orchestrator
        # (direct) cannot honor fire-and-forget at all — a valid target does NOT rescue it.
        payload = PipelexPipeRunInput(
            pipe_code="any",
            orchestration_mode="direct",
            delivery=DeliveryMode.FIRE_AND_FORGET,
            delivery_assignment_dump={"webhooks": [], "storage": {"key_prefix": "runs/abc"}},
        )
        with pytest.raises(PipelexBridgeDispatchError, match="cannot honor fire-and-forget"):
            _validate_input(
                payload, orchestrator=DirectOrchestrator(), delivery_assignment=_decode_delivery_assignment(payload.delivery_assignment_dump)
            )

    def test_validate_input_rejects_fire_and_forget_without_delivery(self):
        payload = PipelexPipeRunInput(
            pipe_code="any",
            orchestration_mode="temporal",
            delivery=DeliveryMode.FIRE_AND_FORGET,
        )
        with pytest.raises(PipelexBridgeDispatchError, match="Fire-and-forget"):
            _validate_input(
                payload, orchestrator=_AsyncCapableOrchestrator(), delivery_assignment=_decode_delivery_assignment(payload.delivery_assignment_dump)
            )

    def test_validate_input_rejects_fire_and_forget_with_empty_delivery(self):
        # A DeliveryAssignment with no storage and no webhooks is a no-op: completion would
        # be silently dropped, so it must be rejected just like a missing dump.
        payload = PipelexPipeRunInput(
            pipe_code="any",
            orchestration_mode="temporal",
            delivery=DeliveryMode.FIRE_AND_FORGET,
            delivery_assignment_dump={"webhooks": [], "storage": None},
        )
        with pytest.raises(PipelexBridgeDispatchError, match="delivery target"):
            _validate_input(
                payload, orchestrator=_AsyncCapableOrchestrator(), delivery_assignment=_decode_delivery_assignment(payload.delivery_assignment_dump)
            )

    def test_validate_input_accepts_fire_and_forget_with_storage_target(self):
        payload = PipelexPipeRunInput(
            pipe_code="any",
            orchestration_mode="temporal",
            delivery=DeliveryMode.FIRE_AND_FORGET,
            delivery_assignment_dump={"webhooks": [], "storage": {"key_prefix": "runs/abc"}},
        )
        _validate_input(
            payload, orchestrator=_AsyncCapableOrchestrator(), delivery_assignment=_decode_delivery_assignment(payload.delivery_assignment_dump)
        )  # must not raise

    def test_validate_input_accepts_fire_and_forget_with_webhook_target(self):
        payload = PipelexPipeRunInput(
            pipe_code="any",
            orchestration_mode="temporal",
            delivery=DeliveryMode.FIRE_AND_FORGET,
            delivery_assignment_dump={"webhooks": [{"url": "https://example.test/hook"}], "storage": None},
        )
        _validate_input(
            payload, orchestrator=_AsyncCapableOrchestrator(), delivery_assignment=_decode_delivery_assignment(payload.delivery_assignment_dump)
        )  # must not raise

    def test_decode_library_crate_returns_none_for_none(self):
        assert _decode_library_crate(None) is None

    def test_decode_library_crate_round_trips_empty(self):
        empty = LibraryCrate()
        decoded = _decode_library_crate(empty.model_dump(mode="json"))
        assert decoded is not None
        assert decoded.concepts == empty.concepts
        assert decoded.pipes == empty.pipes

    def test_decode_delivery_assignment_returns_none_for_none(self):
        assert _decode_delivery_assignment(None) is None

    def test_decode_delivery_assignment_round_trips(self):
        assignment = DeliveryAssignment.model_validate(
            {
                "storage": {"key_prefix": "runs/abc"},
                "webhooks": [{"url": "https://example.test/hook"}],
            }
        )
        decoded = _decode_delivery_assignment(assignment.model_dump(mode="json"))
        assert decoded is not None
        assert decoded.storage is not None
        assert decoded.storage.key_prefix == "runs/abc/"  # storage validator appends trailing /
        assert len(decoded.webhooks) == 1
        assert decoded.webhooks[0].url == "https://example.test/hook"

    @pytest.mark.asyncio
    async def test_run_pipe_via_bridge_rejects_fire_and_forget_on_direct(self):
        # Real path: the bridge resolves the always-registered "direct" orchestrator (blocking-only)
        # and rejects the fire-and-forget request honestly — even with a valid delivery target —
        # instead of running blocking and falsely acking completion. Rejection happens before any
        # pipe lookup, so a nonexistent pipe_code is fine.
        payload = PipelexPipeRunInput(
            pipe_code="any",
            orchestration_mode="direct",
            delivery=DeliveryMode.FIRE_AND_FORGET,
            delivery_assignment_dump={"webhooks": [], "storage": {"key_prefix": "runs/abc"}},
        )
        with pytest.raises(PipelexBridgeDispatchError, match="cannot honor fire-and-forget"):
            await run_pipe_via_bridge(payload)
