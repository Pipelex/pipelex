import pytest
from pytest import Parser

from pipelex.deep_flow.deep_flow_hub import deep_flow_hub
from pipelex.deep_flow.deep_flow_manager import DeepFlowManager
from pipelex.deep_flow.tasks import Tasks
from pipelex.deep_flow.temporal_manager import TemporalWorkerEnvironment


def pytest_addoption(parser: Parser):
    parser.addoption(
        "--worker",
        default=TemporalWorkerEnvironment.INTERNAL,
        help="Which temporal worker environment to use ('internal', 'external')",
    )


@pytest.fixture(scope="module", autouse=True)
def boot_deep_flow():
    """Boot the deep_flow layer for temporal tests.

    Runs after the root conftest's reset_pipelex_config_fixture (also module-scoped)
    has initialized Pipelex. Creates a DeepFlowManager, populates the task catalog,
    and registers it on the deep_flow_hub so that get_task_manager() works.
    """
    manager = DeepFlowManager()
    deep_flow_hub.set_task_manager(manager)
    manager.complement_catalog(
        extra_catalog=Tasks.TASK_PACKS,
        extra_workflows=[],
        extra_activities=[],
    )
    manager.setup()
    yield
    manager.teardown()
    deep_flow_hub.reset()
