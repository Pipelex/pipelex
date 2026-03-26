from typing import AsyncGenerator, cast

import pytest
import pytest_asyncio
from pytest import FixtureRequest, Parser
from temporalio.client import Client as TemporalClient
from temporalio.testing import WorkflowEnvironment

from pipelex.temporal.tasks import Tasks
from pipelex.temporal.temporal_data_converter import data_converter
from pipelex.temporal.temporal_hub import temporal_hub
from pipelex.temporal.temporal_manager import TemporalWorkerEnvironment
from pipelex.temporal.temporal_task_manager import TemporalTaskManager


def pytest_addoption(parser: Parser):
    parser.addoption(
        "--worker",
        default=TemporalWorkerEnvironment.INTERNAL,
        help="Which temporal worker environment to use ('internal', 'external')",
    )
    parser.addoption(
        "--workflow-environment",
        default="local",
        help="Which workflow environment to use ('local', 'time-skipping', or target to existing server)",
    )


@pytest.fixture(scope="module", autouse=True)
def boot_temporal():
    """Boot the temporal layer for temporal tests.

    Runs after the root conftest's reset_pipelex_config_fixture (also module-scoped)
    has initialized Pipelex. Creates a TemporalTaskManager, populates the task catalog,
    and registers it on the temporal_hub so that get_task_manager() works.
    """
    manager = TemporalTaskManager()
    temporal_hub.set_task_manager(manager)
    manager.complement_catalog(
        extra_catalog=Tasks.TASK_PACKS,
        extra_workflows=[],
        extra_activities=[],
    )
    manager.setup()
    yield
    manager.teardown()
    temporal_hub.reset()


@pytest_asyncio.fixture(scope="session")  # pyright: ignore[reportUntypedFunctionDecorator, reportUnknownMemberType]
async def env(request: FixtureRequest) -> AsyncGenerator[WorkflowEnvironment, None]:
    """In-process Temporal test server, shared across all temporal tests."""
    env_type: str = cast("str", request.config.getoption("--workflow-environment"))
    workflow_env: WorkflowEnvironment
    if env_type == "local":
        workflow_env = await WorkflowEnvironment.start_local(data_converter=data_converter)  # pyright: ignore[reportUnknownMemberType]
    elif env_type == "time-skipping":
        workflow_env = await WorkflowEnvironment.start_time_skipping(data_converter=data_converter)
    else:
        from temporalio.client import Client  # noqa: PLC0415

        workflow_env = WorkflowEnvironment.from_client(
            await Client.connect(
                env_type,
                data_converter=data_converter,
            )
        )
    yield workflow_env
    await workflow_env.shutdown()


@pytest_asyncio.fixture  # pyright: ignore[reportUntypedFunctionDecorator, reportUnknownMemberType]
async def temporal_client(env: WorkflowEnvironment) -> TemporalClient:  # noqa: RUF029
    """Temporal client connected to the test server."""
    return env.client
