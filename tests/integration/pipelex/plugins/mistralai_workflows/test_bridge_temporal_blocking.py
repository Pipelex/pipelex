"""Layer-3 integration test: ``run_pipe_via_bridge`` end-to-end in TEMPORAL_BLOCKING mode.

The bridge dispatches a Pipelex ``WfPipeRun`` workflow through the same
``make_temporal_pipe_run`` helper that the activity wrapper uses, and waits
for completion. This validates the full bridge → Pipelex Temporal wiring.

The Mistral ``@activity`` wrapping over ``run_pipe_via_bridge`` is a
single-line decoration already validated end-to-end in DIRECT mode by
``test_activities_direct.py``; the same wrapping flows through this code path
unchanged.

Skipped when ``temporalio`` (or ``mistralai-workflows``) is not installed.
"""

from collections.abc import AsyncGenerator, Generator

import pytest
import pytest_asyncio

pytest.importorskip("temporalio")
pytest.importorskip("mistralai.workflows")

from temporalio.testing import WorkflowEnvironment

from pipelex.cogt.content_generation.generated_content_factory import GeneratedContentFactory
from pipelex.config import get_config
from pipelex.hub import get_pipelex_hub, get_storage_provider
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
TEST_TASK_QUEUE = "pipelex-bridge-temporal-blocking-test"


@pytest.fixture(scope="module", autouse=True)
def _enable_pipelex_temporal_for_bridge() -> Generator[None, None, None]:  # pyright: ignore[reportUnusedFunction]
    """Enable Pipelex Temporal and pin the worker task_queue to our test queue.

    The bridge calls ``make_temporal_pipe_run()`` with no arguments, which
    reads the task_queue from ``get_config().temporal.worker_config.task_queue``.
    """
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
    """Set up the Pipelex Temporal task manager + temporal-aware routers.

    Mirrors the production boot path: registers WfPipeRun / WfPipeRouter and
    swaps the pipe_router and content_generator on the hub for their
    Temporal-aware variants. Without this, dispatching ``WfPipeRun`` would
    fail because the worker would have no workflows to register.
    """
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

    TemporalManager.setup(session_id="bridge-temporal-blocking-test")

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
    """Local Temporal env wired with Pipelex's data converter.

    Pre-connects ``TemporalManager`` to ``env.client`` so that
    ``make_temporal_pipe_run()`` (called by the bridge with default
    ``should_auto_connect_temporal=True``) reuses the same client instead of
    auto-connecting to a non-existent production server.
    """
    env = await WorkflowEnvironment.start_local(data_converter=data_converter)  # pyright: ignore[reportUnknownMemberType]
    try:
        await get_temporal_manager().connect_temporal(temporal_client=env.client)
        yield env
    finally:
        await env.shutdown()


@pytest.mark.temporal
@pytest.mark.asyncio(loop_scope="class")
class TestBridgeTemporalBlocking:
    async def test_temporal_blocking_mode_end_to_end(
        self,
        workflow_env: WorkflowEnvironment,
        bridge_test_library: str,  # noqa: ARG002
    ) -> None:
        """Bridge dispatches WfPipeRun on the test Temporal server and blocks until completion."""
        async with get_task_manager().make_worker(
            temporal_client=workflow_env.client,
            task_queue=TEST_TASK_QUEUE,
            is_not_sandboxed=True,
        ):
            result = await run_pipe_via_bridge(
                PipelexPipeRunInput(
                    pipe_code=PIPE_REF,
                    inputs={"input_text": "hello via temporal blocking"},
                    execution_mode=PipelexExecutionMode.TEMPORAL_BLOCKING,
                )
            )

        assert result.is_completed is True
        assert result.workflow_id is not None
        assert result.main_stuff_name is not None
        main_stuff_dump = result.output_dict["root"][result.main_stuff_name]
        assert main_stuff_dump["content"]["text"] == "hello via temporal blocking"
