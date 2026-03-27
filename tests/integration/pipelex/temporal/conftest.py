from typing import AsyncGenerator, cast

import pytest
import pytest_asyncio
from pytest import FixtureRequest, Parser
from temporalio.client import Client as TemporalClient
from temporalio.testing import WorkflowEnvironment

from pipelex.pipelex import Pipelex
from pipelex.system.runtime import IntegrationMode, runtime_manager
from pipelex.temporal.tasks import Tasks
from pipelex.temporal.temporal_connect import connect_to_temporal_selected_server
from pipelex.temporal.temporal_data_converter import data_converter
from pipelex.temporal.temporal_hub import temporal_hub
from pipelex.temporal.temporal_task_manager import TemporalTaskManager

TEMPORAL_SERVER_NONE = "none"
TEMPORAL_SERVER_TIME_SKIPPING = "time-skipping"


def pytest_addoption(parser: Parser) -> None:
    parser.addoption(
        "--temporal-server",
        default=TEMPORAL_SERVER_NONE,
        help="Which temporal server to use ('none' for in-process, 'time-skipping', or a profile name from temporal_server_configs)",
    )


def _session_owns_pipelex(request: FixtureRequest) -> bool:
    """True when using a real Temporal server, meaning the session-scoped `env`
    fixture initialized Pipelex and owns its lifecycle.
    """
    server_option: str = cast("str", request.config.getoption("--temporal-server"))
    return server_option not in {TEMPORAL_SERVER_NONE, TEMPORAL_SERVER_TIME_SKIPPING}


@pytest.fixture(scope="module", autouse=True)
def reset_pipelex_config_fixture(request: FixtureRequest):
    """Override root conftest's fixture for Temporal tests.

    When using a real Temporal server (--temporal-server <profile>), the session-scoped
    `env` fixture owns the Pipelex lifecycle because it needs config to connect.
    Skip module-level init/teardown to avoid conflicting with it.
    """
    if _session_owns_pipelex(request):
        yield
        return
    Pipelex.make(
        integration_mode=IntegrationMode.CI if runtime_manager.is_ci_testing else IntegrationMode.PYTEST,
    )
    yield
    Pipelex.teardown_if_needed()


@pytest.fixture(scope="module", autouse=True)
def boot_temporal():
    """Boot the temporal layer for temporal tests.

    Runs after reset_pipelex_config_fixture (also module-scoped)
    has ensured Pipelex is initialized. Creates a TemporalTaskManager, populates
    the task catalog, and registers it on the temporal_hub so that
    get_task_manager() works.
    """
    manager = TemporalTaskManager()
    temporal_hub.set_task_manager(manager)
    manager.complement_catalog(
        extra_catalog=Tasks.TASK_PACKS,
        extra_workflows=[],
        extra_activities=[],
    )
    manager.setup()

    # Install Temporal-aware pipe routers and content generator so that:
    # 1. Sub-pipes dispatch as child workflows (not inline in the sandbox)
    # 2. Inference calls (LLM, img_gen, etc.) dispatch as activities (not inline)
    # This mirrors what a full Temporal-enabled Pipelex.make() would set up.
    from pipelex.cogt.content_generation.generated_content_factory import GeneratedContentFactory  # noqa: PLC0415
    from pipelex.hub import get_pipelex_hub, get_storage_provider  # noqa: PLC0415
    from pipelex.temporal.tprl_content_generation.content_generator_child_factory import ContentGeneratorChildFactory  # noqa: PLC0415
    from pipelex.temporal.tprl_pipe.pipe_router_child import make_tprl_pipe_router_child  # noqa: PLC0415
    from pipelex.temporal.tprl_pipe.pipe_router_top import make_tprl_pipe_router_top  # noqa: PLC0415

    pipelex_hub = get_pipelex_hub()
    pipelex_hub.set_pipe_router_top(make_tprl_pipe_router_top())
    pipelex_hub.set_pipe_router(make_tprl_pipe_router_child())

    generated_content_factory = GeneratedContentFactory(storage_provider=get_storage_provider())
    content_generator_child = ContentGeneratorChildFactory.make_content_generator_child(
        generated_content_factory=generated_content_factory,
    )
    pipelex_hub.set_content_generator(content_generator_child)

    yield
    manager.teardown()
    temporal_hub.reset()

    # Clear cached inference workers and SDK instances between modules.
    # When session owns Pipelex (--temporal-server <profile>), the InferenceManager
    # persists across modules. Each module's test class uses its own event loop
    # (loop_scope="class"), so cached workers hold httpx connections bound to the
    # previous module's (now-closed) event loop. Clearing forces fresh workers/clients
    # on the next module's event loop.
    from pipelex.hub import get_inference_manager, get_plugin_manager  # noqa: PLC0415

    get_inference_manager().teardown()
    get_plugin_manager().plugin_sdk_registry.teardown()


@pytest_asyncio.fixture(scope="session")  # pyright: ignore[reportUntypedFunctionDecorator, reportUnknownMemberType]
async def env(request: FixtureRequest) -> AsyncGenerator[WorkflowEnvironment, None]:
    """Temporal test environment, shared across all temporal tests.

    Uses an in-process server by default (--temporal-server none).
    Pass a profile name from temporal_server_configs to connect to a real server.
    """
    server_option: str = cast("str", request.config.getoption("--temporal-server"))
    workflow_env: WorkflowEnvironment
    needs_early_init = server_option not in {TEMPORAL_SERVER_NONE, TEMPORAL_SERVER_TIME_SKIPPING}
    if needs_early_init:
        # Connecting to a real server needs config (for host, namespace, API key).
        # Pipelex is normally initialized by the module-scoped reset_pipelex_config_fixture,
        # but this session-scoped fixture runs first, so we bootstrap here.
        integration_mode = IntegrationMode.CI if runtime_manager.is_ci_testing else IntegrationMode.PYTEST
        Pipelex.make(integration_mode=integration_mode)
    if server_option == TEMPORAL_SERVER_NONE:
        workflow_env = await WorkflowEnvironment.start_local(data_converter=data_converter)  # pyright: ignore[reportUnknownMemberType]
    elif server_option == TEMPORAL_SERVER_TIME_SKIPPING:
        workflow_env = await WorkflowEnvironment.start_time_skipping(data_converter=data_converter)
    else:
        temporal_client = await connect_to_temporal_selected_server(selected_server_config=server_option)
        workflow_env = WorkflowEnvironment.from_client(temporal_client)
    yield workflow_env
    await workflow_env.shutdown()
    if needs_early_init:
        Pipelex.teardown_if_needed()


@pytest_asyncio.fixture  # pyright: ignore[reportUntypedFunctionDecorator, reportUnknownMemberType]
async def temporal_client(env: WorkflowEnvironment) -> TemporalClient:  # noqa: RUF029
    """Temporal client connected to the test server."""
    return env.client
