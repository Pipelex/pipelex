"""Layer-3 integration test: ``run_pipe_via_bridge`` in TEMPORAL_FIRE_AND_FORGET mode.

Validates that the bridge dispatches a Pipelex ``WfPipeRun`` workflow on the
test Temporal server and returns immediately without waiting for completion,
and that the workflow eventually completes asynchronously.

Skipped when ``temporalio`` (or ``mistralai-workflows``) is not installed.
"""

from collections.abc import AsyncGenerator, Generator

import pytest
import pytest_asyncio

pytest.importorskip("temporalio")
pytest.importorskip("mistralai.workflows")

from temporalio.client import WorkflowExecutionStatus
from temporalio.testing import WorkflowEnvironment

from pipelex.cogt.content_generation.generated_content_factory import GeneratedContentFactory
from pipelex.config import get_config
from pipelex.hub import get_pipelex_hub, get_storage_provider
from pipelex.pipe_run.delivery_assignment import DeliveryAssignment
from pipelex.plugins.mistralai_workflows.bridge import (
    PipelexPipeRunInput,
    run_pipe_via_bridge,
)
from pipelex.plugins.mistralai_workflows.execution_mode import PipelexExecutionMode
from pipelex.temporal.tasks import Tasks
from pipelex.temporal.temporal_data_converter import data_converter
from pipelex.temporal.temporal_hub import get_task_manager, temporal_hub
from pipelex.temporal.temporal_manager import TemporalManager, get_temporal_manager
from pipelex.temporal.temporal_task_manager import TemporalTaskManager
from pipelex.temporal.tprl_content_generation.content_generator_child_factory import ContentGeneratorChildFactory
from pipelex.temporal.tprl_pipe.temporal_pipe_router import make_temporal_pipe_router

PIPE_REF = "mistralai_workflows_bridge_test.bridge_compose_pipe"
TEST_TASK_QUEUE = "pipelex-bridge-temporal-fire-and-forget-test"


@pytest.fixture(scope="module", autouse=True)
def _enable_pipelex_temporal_for_bridge() -> Generator[None, None, None]:  # pyright: ignore[reportUnusedFunction]
    config = get_config()
    original_is_enabled = config.temporal.is_enabled
    original_task_queue = config.temporal.worker_config.task_queue
    config.temporal.is_enabled = True
    config.temporal.worker_config.task_queue = TEST_TASK_QUEUE
    try:
        yield
    finally:
        config.temporal.is_enabled = original_is_enabled
        config.temporal.worker_config.task_queue = original_task_queue


@pytest.fixture(scope="module", autouse=True)
def _boot_pipelex_temporal_layer(_enable_pipelex_temporal_for_bridge: None) -> Generator[None, None, None]:  # pyright: ignore[reportUnusedFunction]
    """Mirrors the production boot path for Pipelex's Temporal layer."""
    manager = TemporalTaskManager()
    temporal_hub.set_task_manager(manager)
    manager.complement_catalog(
        extra_catalog=Tasks.TASK_PACKS,
        extra_workflows=[],
        extra_activities=[],
    )
    manager.setup()

    pipelex_hub = get_pipelex_hub()
    original_pipe_router = pipelex_hub.get_required_pipe_router()
    original_content_generator = pipelex_hub.get_required_content_generator()

    pipelex_hub.set_pipe_router(make_temporal_pipe_router())
    generated_content_factory = GeneratedContentFactory(storage_provider=get_storage_provider())
    pipelex_hub.set_content_generator(
        ContentGeneratorChildFactory.make_content_generator_child(
            generated_content_factory=generated_content_factory,
        )
    )

    TemporalManager.setup(session_id="bridge-temporal-faf-test")

    try:
        yield
    finally:
        TemporalManager.teardown()
        pipelex_hub.set_pipe_router(original_pipe_router)
        pipelex_hub.set_content_generator(original_content_generator)
        manager.teardown()
        temporal_hub.reset()


@pytest_asyncio.fixture(scope="module")  # pyright: ignore[reportUntypedFunctionDecorator, reportUnknownMemberType]
async def workflow_env() -> AsyncGenerator[WorkflowEnvironment, None]:
    env = await WorkflowEnvironment.start_local(data_converter=data_converter)  # pyright: ignore[reportUnknownMemberType]
    try:
        await get_temporal_manager().connect_temporal(temporal_client=env.client)
        yield env
    finally:
        await env.shutdown()


@pytest.mark.temporal
@pytest.mark.asyncio(loop_scope="class")
class TestBridgeTemporalFireAndForget:
    async def test_fire_and_forget_returns_immediately_and_workflow_completes(
        self,
        workflow_env: WorkflowEnvironment,
        bridge_test_library: str,  # noqa: ARG002
    ) -> None:
        """Bridge starts WfPipeRun without waiting; the workflow completes asynchronously.

        Asserts in two phases:

        1. The bridge returns with ``is_completed=False`` and a non-None
           ``workflow_id`` — proving the dispatch did not block.
        2. The Pipelex Temporal workflow eventually completes with
           ``COMPLETED`` status when the worker is given time to run.
        """
        delivery_assignment_dump = DeliveryAssignment().model_dump(mode="json")

        async with get_task_manager().make_worker(
            temporal_client=workflow_env.client,
            task_queue=TEST_TASK_QUEUE,
            is_not_sandboxed=True,
        ):
            result = await run_pipe_via_bridge(
                PipelexPipeRunInput(
                    pipe_code=PIPE_REF,
                    inputs={"input_text": "hello via temporal fire and forget"},
                    execution_mode=PipelexExecutionMode.TEMPORAL_FIRE_AND_FORGET,
                    delivery_assignment_dump=delivery_assignment_dump,
                )
            )

            # Phase 1 — dispatch returned immediately without waiting.
            assert result.is_completed is False
            assert result.workflow_id is not None
            assert result.output_dict == {}
            assert result.main_stuff_name is None

            # Phase 2 — the Pipelex workflow eventually completes on the worker.
            handle = workflow_env.client.get_workflow_handle(workflow_id=result.workflow_id)
            await handle.result()
            description = await handle.describe()
            assert description.status == WorkflowExecutionStatus.COMPLETED
