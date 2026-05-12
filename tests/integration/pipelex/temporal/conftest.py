from typing import AsyncGenerator, Generator, cast

import pytest
import pytest_asyncio
from pytest import FixtureRequest, Parser
from temporalio.client import Client as TemporalClient
from temporalio.testing import WorkflowEnvironment

from pipelex import log
from pipelex.pipelex import Pipelex
from pipelex.system.runtime import IntegrationMode, runtime_manager
from pipelex.temporal.config_temporal import BUILTIN_SEARCH_ATTRIBUTES
from pipelex.temporal.tasks import Tasks
from pipelex.temporal.temporal_connect import connect_to_temporal_selected_server
from pipelex.temporal.temporal_data_converter import data_converter
from pipelex.temporal.temporal_hub import temporal_hub
from pipelex.temporal.temporal_task_manager import TemporalTaskManager
from pipelex.temporal.tprl.namespace_check import RegistrationFailure, ensure_required_search_attributes_registered
from pipelex.test_extras.shared_pytest_plugins import ClassRegistryMode

TEMPORAL_SERVER_NONE = "none"
TEMPORAL_SERVER_TIME_SKIPPING = "time-skipping"


def pytest_addoption(parser: Parser) -> None:
    parser.addoption(
        "--temporal-server",
        default=TEMPORAL_SERVER_NONE,
        help="Which temporal server to use ('none' for in-process, 'time-skipping', or a profile name from temporal_server_configs)",
    )


@pytest.fixture(scope="module", autouse=True)
def reset_pipelex_config_fixture() -> Generator[None, None, None]:
    """Override root conftest's fixture for Temporal tests.

    Always initializes Pipelex per module so that logging and config are available
    for boot_temporal and other fixtures, regardless of --temporal-server mode.
    """
    Pipelex.make(
        integration_mode=IntegrationMode.CI if runtime_manager.is_ci_testing else IntegrationMode.PYTEST,
    )
    yield
    Pipelex.teardown_if_needed()


@pytest.fixture(scope="module", autouse=True)
def boot_temporal(reset_pipelex_config_fixture: None) -> Generator[None, None, None]:  # noqa: ARG001
    """Boot the temporal layer for temporal tests.

    Depends on reset_pipelex_config_fixture to ensure Pipelex is initialized
    before we access logging or config. Creates a TemporalTaskManager, populates
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
    from pipelex.temporal.tprl_content_generation.content_generator_in_workflow_factory import (  # noqa: PLC0415
        ContentGeneratorInWorkflowFactory,
    )
    from pipelex.temporal.tprl_pipe.temporal_pipe_router import make_temporal_pipe_router  # noqa: PLC0415

    pipelex_hub = get_pipelex_hub()
    pipelex_hub.set_pipe_router(make_temporal_pipe_router())

    generated_content_factory = GeneratedContentFactory(storage_provider=get_storage_provider())
    pipelex_hub.set_content_generator(
        ContentGeneratorInWorkflowFactory.make_content_generator_in_workflow(
            generated_content_factory=generated_content_factory,
        )
    )

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

    For real server modes, Pipelex is temporarily bootstrapped here to read
    connection config (session fixtures run before module-scoped ones), then
    torn down so reset_pipelex_config_fixture can re-initialize per module.
    The gRPC TemporalClient stays alive independently of the Pipelex lifecycle.
    """
    server_option: str = cast("str", request.config.getoption("--temporal-server"))
    workflow_env: WorkflowEnvironment
    if server_option == TEMPORAL_SERVER_NONE:
        workflow_env = await WorkflowEnvironment.start_local(data_converter=data_converter)  # pyright: ignore[reportUnknownMemberType]
    elif server_option == TEMPORAL_SERVER_TIME_SKIPPING:
        workflow_env = await WorkflowEnvironment.start_time_skipping(data_converter=data_converter)
    else:
        # Bootstrap Pipelex temporarily to read server connection config.
        # If a module-scoped fixture already initialized Pipelex (happens when
        # env is lazily triggered after reset_pipelex_config_fixture), skip init
        # and just read the config from the existing instance.

        # TODO: Pipelex.make() is heavy — it initializes inference, registries, etc.
        # We only need the config here. Design a lightweight boot path (e.g.
        # Pipelex.load_config_only()) that parses pipelex.toml without full init.
        needs_teardown = False
        if Pipelex.get_optional_instance() is None:
            Pipelex.make(
                integration_mode=IntegrationMode.CI if runtime_manager.is_ci_testing else IntegrationMode.PYTEST,
            )
            needs_teardown = True
        temporal_client = await connect_to_temporal_selected_server(selected_server_config=server_option)
        if needs_teardown:
            Pipelex.teardown_if_needed()
        workflow_env = WorkflowEnvironment.from_client(temporal_client)
    # Every Temporal namespace — in-process, time-skipping, or real-server profile —
    # starts with no custom search attributes registered, so the cluster's
    # StartWorkflowExecution RPC rejects every workflow that sets one. Register
    # them here so all temporal tests can start workflows without per-test
    # bootstrap. Idempotent: only adds attributes that are missing.
    # ``RegistrationFailure`` is returned (not raised) when the API key lacks
    # ``AddSearchAttributes`` permission (Temporal Cloud read-only key); surface
    # it as a warning so the operator runs ``pipelex setup-temporal-namespace``
    # with an admin key before rerunning the tests. For in-process and
    # time-skipping servers the caller is always admin, so this branch is
    # unreachable there — but handling it uniformly keeps the call site honest
    # against the function's full return type.
    registration_result = await ensure_required_search_attributes_registered(
        temporal_client=workflow_env.client,
        namespace=workflow_env.client.namespace,
        configured_attributes=BUILTIN_SEARCH_ATTRIBUTES,
    )
    if isinstance(registration_result, RegistrationFailure):
        msg = (
            f"Could not auto-register Temporal search attributes on namespace "
            f"'{registration_result.namespace}' (missing: {list(registration_result.missing)}). "
            f"Workflow starts will fail at dispatch. Run `pipelex setup-temporal-namespace` "
            f"with an admin API key, then rerun the tests. RPC error: "
            f"{registration_result.rpc_error_message}"
        )
        log.warning(msg)
    yield workflow_env
    await workflow_env.shutdown()


@pytest_asyncio.fixture  # pyright: ignore[reportUntypedFunctionDecorator, reportUnknownMemberType]
async def temporal_client(env: WorkflowEnvironment) -> TemporalClient:  # noqa: RUF029
    """Temporal client connected to the test server."""
    return env.client


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Auto-parametrize is_class_registry_isolated based on --class-registry.

    By default (``--class-registry both``), every test class that requests
    ``is_class_registry_isolated`` runs twice: once with classes in the global
    registry (shared) and once scoped to the library (isolated).  Pass
    ``--class-registry shared`` or ``--class-registry isolated`` to force a
    single mode (useful for debugging).
    """
    if "is_class_registry_isolated" not in metafunc.fixturenames:
        return
    mode = ClassRegistryMode(metafunc.config.getoption("--class-registry"))
    match mode:
        case ClassRegistryMode.BOTH:
            metafunc.parametrize("is_class_registry_isolated", [False, True], ids=["shared", "isolated"], scope="class")
        case ClassRegistryMode.ISOLATED:
            metafunc.parametrize("is_class_registry_isolated", [True], ids=["isolated"], scope="class")
        case ClassRegistryMode.SHARED:
            metafunc.parametrize("is_class_registry_isolated", [False], ids=["shared"], scope="class")
