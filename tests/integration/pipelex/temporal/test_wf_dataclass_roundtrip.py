"""Integration test: a pydantic dataclass round-trips through Temporal (workflow -> activity -> return).

Phase 0 widened ``BaseModelPayloadConverter`` to route pydantic dataclasses through kajson with
type preservation. This exercises that path end-to-end through the in-process test server: the
dataclass is encoded by the client, decoded by the worker for the activity, re-encoded on return,
and decoded again by the client — every hop driven by the widened converter.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import TYPE_CHECKING

import pytest
from pydantic import BaseModel
from pydantic.dataclasses import dataclass as pydantic_dataclass
from pydantic.dataclasses import is_pydantic_dataclass
from temporalio import activity, workflow
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import UnsandboxedWorkflowRunner, Worker

from pipelex.pipelex import Pipelex
from pipelex.system.runtime import IntegrationMode, runtime_manager
from pipelex.temporal.temporal_data_converter import make_data_converter

if TYPE_CHECKING:
    from collections.abc import Generator

    from temporalio.client import Client as TemporalClient


# ---------------------------------------------------------------------------
# Override autouse fixtures from parent conftest — this test manages its own
# Worker and client, and only needs Pipelex initialized for logging/config.
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
# Test model, dataclass, activity, and workflow
# ---------------------------------------------------------------------------


class DataclassInner(BaseModel):
    """Nested BaseModel field, to prove type preservation survives inside a dataclass."""

    label: str
    count: int


@pydantic_dataclass
class DataclassPayload:
    """Pydantic dataclass crossing the Temporal wire — the type Phase 0 made wire-legal."""

    name: str
    delay: timedelta
    inner: DataclassInner
    note: str | None = None


@activity.defn(name="act_echo_dataclass_payload")
async def act_echo_dataclass_payload(payload: DataclassPayload) -> DataclassPayload:  # noqa: RUF029
    """Return the dataclass unchanged — exercises decode (arg) then encode (return)."""
    return payload


@workflow.defn(name="wf_echo_dataclass_payload")
class WfEchoDataclassPayload:
    """Forward a pydantic dataclass through an activity and return it."""

    @workflow.run
    async def run(self, payload: DataclassPayload) -> DataclassPayload:
        return await workflow.execute_activity(
            act_echo_dataclass_payload,
            payload,
            start_to_close_timeout=timedelta(seconds=30),
        )


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="class")
class TestPydanticDataclassTemporalRoundTrip:
    async def test_pydantic_dataclass_survives_temporal_roundtrip(self) -> None:
        """A pydantic dataclass round-trips through workflow -> activity -> return with type preserved."""
        original = DataclassPayload(
            name="widget",
            delay=timedelta(seconds=45),
            inner=DataclassInner(label="L", count=3),
            note="hello",
        )

        task_queue = str(uuid.uuid4())
        converter = make_data_converter()

        async with await WorkflowEnvironment.start_local(data_converter=converter) as env:  # pyright: ignore[reportUnknownMemberType]
            temporal_client: TemporalClient = env.client
            async with Worker(
                temporal_client,
                task_queue=task_queue,
                workflows=[WfEchoDataclassPayload],
                activities=[act_echo_dataclass_payload],
                workflow_runner=UnsandboxedWorkflowRunner(),
            ):
                result: DataclassPayload = await temporal_client.execute_workflow(  # pyright: ignore[reportUnknownMemberType]
                    WfEchoDataclassPayload.run,
                    original,
                    id=f"wf-dataclass-roundtrip-{uuid.uuid4().hex[:8]}",
                    task_queue=task_queue,
                )

        assert is_pydantic_dataclass(type(result))
        assert isinstance(result.inner, DataclassInner)
        assert result.inner.label == "L"
        assert result.inner.count == 3
        assert result.delay == timedelta(seconds=45)
        assert result.note == "hello"
        assert result == original
