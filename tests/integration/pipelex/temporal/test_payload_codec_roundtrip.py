"""Integration test for StoragePayloadCodec round-trip through Temporal.

Verifies that large payloads are transparently offloaded to external storage
and reconstructed on the other side of a workflow → activity → return chain.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import TYPE_CHECKING, ClassVar

import pytest
from pydantic import BaseModel
from temporalio import activity, workflow
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import UnsandboxedWorkflowRunner, Worker

from pipelex.base_exceptions import ErrorDomain, ErrorReport
from pipelex.cogt.inference.error_classification import ProviderErrorMetadata, UserAction, UserActionKind
from pipelex.cogt.inference.provider_name import ProviderName
from pipelex.pipelex import Pipelex
from pipelex.system.runtime import IntegrationMode, runtime_manager
from pipelex.temporal.codec.storage_payload_codec import StoragePayloadCodec
from pipelex.temporal.temporal_data_converter import make_data_converter
from pipelex.tools.storage.local_storage_provider import LocalStorageProvider

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

    from temporalio.client import Client as TemporalClient

# ---------------------------------------------------------------------------
# Override autouse fixtures from parent conftest — this test needs Pipelex
# initialized (for logging/config) but not the full TemporalTaskManager.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module", autouse=True)
def reset_pipelex_config_fixture() -> Generator[None, None, None]:
    """Initialize Pipelex for logging/config without TemporalTaskManager."""
    Pipelex.make(
        integration_mode=IntegrationMode.CI if runtime_manager.is_ci_testing else IntegrationMode.PYTEST,
    )
    yield
    Pipelex.teardown_if_needed()


@pytest.fixture(scope="module", autouse=True)
def boot_temporal(reset_pipelex_config_fixture: None) -> None:
    """No-op override: this test manages its own Worker and client."""


# ---------------------------------------------------------------------------
# Test model, activity, and workflow
# ---------------------------------------------------------------------------


class LargePayloadModel(BaseModel):
    """Simple model carrying a large string payload."""

    label: str
    data: str


@activity.defn(name="act_echo_large_payload")
async def act_echo_large_payload(payload: LargePayloadModel) -> LargePayloadModel:  # noqa: RUF029
    """Activity that returns its input unchanged — exercises decode then encode."""
    return payload


@workflow.defn(name="wf_echo_large_payload")
class WfEchoLargePayload:
    """Workflow that forwards a large payload through an activity and returns it."""

    @workflow.run
    async def run(self, payload: LargePayloadModel) -> LargePayloadModel:
        return await workflow.execute_activity(
            act_echo_large_payload,
            payload,
            start_to_close_timeout=timedelta(seconds=30),
        )


@activity.defn(name="act_echo_error_report")
async def act_echo_error_report(report: ErrorReport) -> ErrorReport:  # noqa: RUF029
    """Activity that returns its ErrorReport input unchanged — exercises the BaseModel round-trip."""
    return report


@workflow.defn(name="wf_echo_error_report")
class WfEchoErrorReport:
    """Workflow that forwards an ErrorReport through an activity and returns it."""

    @workflow.run
    async def run(self, report: ErrorReport) -> ErrorReport:
        return await workflow.execute_activity(
            act_echo_error_report,
            report,
            start_to_close_timeout=timedelta(seconds=30),
        )


# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------


class TestPayloadCodecRoundTripTestData:
    # 1 KB threshold — low enough that our test payload triggers offloading
    SIZE_THRESHOLD: ClassVar[int] = 1024
    STORAGE_PREFIX: ClassVar[str] = "test-payloads/"
    # Generate a payload well above the threshold
    LARGE_DATA: ClassVar[str] = "X" * 10_000
    LABEL: ClassVar[str] = "roundtrip-test"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="class")
class TestPayloadCodecRoundTrip:
    """End-to-end test: client encode → storage → worker decode → activity → worker encode → storage → client decode."""

    async def test_large_payload_survives_temporal_roundtrip(self, tmp_path: Path) -> None:
        """A payload larger than the codec threshold round-trips through Temporal identically."""
        # Arrange: build a codec-enabled environment
        storage_root = tmp_path / "payload-store"
        storage_root.mkdir()
        storage_provider = LocalStorageProvider(root_path=storage_root)
        codec = StoragePayloadCodec(
            storage_provider=storage_provider,
            size_threshold=TestPayloadCodecRoundTripTestData.SIZE_THRESHOLD,
            storage_prefix=TestPayloadCodecRoundTripTestData.STORAGE_PREFIX,
        )
        converter = make_data_converter(payload_codec=codec)

        input_payload = LargePayloadModel(
            label=TestPayloadCodecRoundTripTestData.LABEL,
            data=TestPayloadCodecRoundTripTestData.LARGE_DATA,
        )

        task_queue = str(uuid.uuid4())

        async with await WorkflowEnvironment.start_local(data_converter=converter) as env:  # pyright: ignore[reportUnknownMemberType]
            temporal_client: TemporalClient = env.client
            async with Worker(
                temporal_client,
                task_queue=task_queue,
                workflows=[WfEchoLargePayload],
                activities=[act_echo_large_payload],
                workflow_runner=UnsandboxedWorkflowRunner(),
            ):
                result: LargePayloadModel = await temporal_client.execute_workflow(  # pyright: ignore[reportUnknownMemberType]
                    WfEchoLargePayload.run,
                    input_payload,
                    id="wf-payload-codec-roundtrip",
                    task_queue=task_queue,
                )

        # Assert: output matches input exactly
        assert isinstance(result, LargePayloadModel)
        assert result.label == input_payload.label
        assert result.data == input_payload.data
        assert result == input_payload

        # Assert: storage was actually used (files were written)
        stored_files = list(storage_root.rglob("*"))
        stored_files = [file_path for file_path in stored_files if file_path.is_file()]
        assert len(stored_files) > 0, "Codec should have offloaded payloads to storage"

    async def test_error_report_round_trips_through_activity(self) -> None:
        """``ErrorReport`` round-trips through a workflow→activity hop, including nested ``UserAction`` / ``ProviderErrorMetadata``."""
        original = ErrorReport(
            error_type="LLMCompletionError",
            message="provider returned 429",
            title="AI inference failed",
            type_uri="https://pipelex.dev/errors/llm-completion-error",
            error_category="transient",
            error_domain=ErrorDomain.RUNTIME,
            retryable=True,
            user_action=UserAction(kind=UserActionKind.WAIT_AND_RETRY, detail="Wait a moment and retry"),
            model="gpt-4o-mini",
            provider="openai",
            provider_metadata=ProviderErrorMetadata(
                provider=ProviderName.OPENAI,
                sdk_exception_type="RateLimitError",
                message="429 Too Many Requests",
                status_code=429,
                request_id="req_round_trip_001",
                retry_after_seconds=2.5,
            ),
        )

        task_queue = str(uuid.uuid4())
        converter = make_data_converter()

        async with await WorkflowEnvironment.start_local(data_converter=converter) as env:  # pyright: ignore[reportUnknownMemberType]
            temporal_client: TemporalClient = env.client
            async with Worker(
                temporal_client,
                task_queue=task_queue,
                workflows=[WfEchoErrorReport],
                activities=[act_echo_error_report],
                workflow_runner=UnsandboxedWorkflowRunner(),
            ):
                result: ErrorReport = await temporal_client.execute_workflow(  # pyright: ignore[reportUnknownMemberType]
                    WfEchoErrorReport.run,
                    original,
                    id=f"wf-error-report-roundtrip-{uuid.uuid4().hex[:8]}",
                    task_queue=task_queue,
                )

        assert isinstance(result, ErrorReport)
        assert result == original
        assert result.user_action is not None
        assert result.user_action.kind == UserActionKind.WAIT_AND_RETRY
        assert result.provider_metadata is not None
        assert result.provider_metadata.status_code == 429
        assert result.provider_metadata.retry_after_seconds == 2.5
