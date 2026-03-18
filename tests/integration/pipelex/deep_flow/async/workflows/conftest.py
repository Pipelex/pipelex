import uuid
from typing import AsyncGenerator, Generator, cast

import pytest
import pytest_asyncio
from pytest import FixtureRequest, Parser
from temporalio.client import Client
from temporalio.testing import WorkflowEnvironment

from pipelex.hub import get_report_delegate
from pipelex.temporal.temporal_data_converter import data_converter


def pytest_addoption(parser: Parser):
    parser.addoption(
        "--workflow-environment",
        default="local",
        help="Which workflow environment to use ('local', 'time-skipping', or target to existing server)",
    )


@pytest_asyncio.fixture(scope="session")  # pyright: ignore[reportUntypedFunctionDecorator, reportUnknownMemberType]
async def env(request: FixtureRequest) -> AsyncGenerator[WorkflowEnvironment, None]:
    env_type: str = cast("str", request.config.getoption("--workflow-environment"))
    workflow_env: WorkflowEnvironment
    if env_type == "local":
        workflow_env = await WorkflowEnvironment.start_local(data_converter=data_converter)  # pyright: ignore[reportUnknownMemberType]
    elif env_type == "time-skipping":
        workflow_env = await WorkflowEnvironment.start_time_skipping(data_converter=data_converter)
    else:
        workflow_env = WorkflowEnvironment.from_client(
            await Client.connect(
                env_type,
                data_converter=data_converter,
            )
        )
    yield workflow_env
    await workflow_env.shutdown()


@pytest_asyncio.fixture  # pyright: ignore[reportUntypedFunctionDecorator, reportUnknownMemberType]
async def temporal_client(env: WorkflowEnvironment) -> Client:  # noqa: RUF029
    return env.client


@pytest.fixture
def workflow_run_id() -> Generator[str, None, None]:
    """Provide a workflow run ID with an open reporting registry.

    Opens a registry for the run ID before the test and closes it after,
    mirroring the job_metadata fixture pattern.
    """
    run_id = str(uuid.uuid4())
    get_report_delegate().open_registry(pipeline_run_id=run_id)
    yield run_id
    get_report_delegate().close_registry(pipeline_run_id=run_id)
