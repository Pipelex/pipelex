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
from pipelex.runtime_bridge.exceptions import PipelexBridgeDispatchError
from pipelex.runtime_bridge.execution_mode import PipelexExecutionMode


class TestBridgeValidationAndDecoding:
    def test_validate_input_passes_for_direct_without_delivery(self):
        payload = PipelexPipeRunInput(pipe_code="any", execution_mode=PipelexExecutionMode.DIRECT)
        _validate_input(payload)  # must not raise

    def test_validate_input_passes_for_temporal_blocking_without_delivery(self):
        payload = PipelexPipeRunInput(pipe_code="any", execution_mode=PipelexExecutionMode.TEMPORAL_BLOCKING)
        _validate_input(payload)  # must not raise

    def test_validate_input_rejects_fire_and_forget_without_delivery(self):
        payload = PipelexPipeRunInput(
            pipe_code="any",
            execution_mode=PipelexExecutionMode.TEMPORAL_FIRE_AND_FORGET,
        )
        with pytest.raises(PipelexBridgeDispatchError, match="TEMPORAL_FIRE_AND_FORGET"):
            _validate_input(payload)

    def test_validate_input_rejects_fire_and_forget_with_empty_delivery(self):
        # A DeliveryAssignment with no storage and no webhooks is a no-op: completion would
        # be silently dropped, so it must be rejected just like a missing dump.
        payload = PipelexPipeRunInput(
            pipe_code="any",
            execution_mode=PipelexExecutionMode.TEMPORAL_FIRE_AND_FORGET,
            delivery_assignment_dump={"webhooks": [], "storage": None},
        )
        with pytest.raises(PipelexBridgeDispatchError, match="delivery target"):
            _validate_input(payload)

    def test_validate_input_accepts_fire_and_forget_with_storage_target(self):
        payload = PipelexPipeRunInput(
            pipe_code="any",
            execution_mode=PipelexExecutionMode.TEMPORAL_FIRE_AND_FORGET,
            delivery_assignment_dump={"webhooks": [], "storage": {"key_prefix": "runs/abc"}},
        )
        _validate_input(payload)  # must not raise

    def test_validate_input_accepts_fire_and_forget_with_webhook_target(self):
        payload = PipelexPipeRunInput(
            pipe_code="any",
            execution_mode=PipelexExecutionMode.TEMPORAL_FIRE_AND_FORGET,
            delivery_assignment_dump={"webhooks": [{"url": "https://example.test/hook"}], "storage": None},
        )
        _validate_input(payload)  # must not raise

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
    async def test_run_pipe_via_bridge_rejects_fire_and_forget_without_delivery(self):
        payload = PipelexPipeRunInput(
            pipe_code="any",
            execution_mode=PipelexExecutionMode.TEMPORAL_FIRE_AND_FORGET,
        )
        with pytest.raises(PipelexBridgeDispatchError, match="TEMPORAL_FIRE_AND_FORGET"):
            await run_pipe_via_bridge(payload)
