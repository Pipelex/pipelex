from typing import AsyncGenerator, cast

import pytest_asyncio
from pytest import FixtureRequest, Parser
from temporalio.client import Client as TemporalClient
from temporalio.testing import WorkflowEnvironment

from pipelex.temporal.temporal_data_converter import data_converter


def pytest_addoption(parser: Parser):
    parser.addoption(
        "--workflow-environment",
        default="local",
        help="Which workflow environment to use ('local', 'time-skipping', or target to existing server)",
    )


@pytest_asyncio.fixture(scope="session")  # pyright: ignore[reportUntypedFunctionDecorator, reportUnknownMemberType]
async def env(request: FixtureRequest) -> AsyncGenerator[WorkflowEnvironment, None]:
    """In-process Temporal test server, shared across all async temporal tests."""
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
