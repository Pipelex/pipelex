import pytest
from pytest import Parser

from pipelex.temporal.tasks import Tasks
from pipelex.temporal.temporal_hub import temporal_hub
from pipelex.temporal.temporal_manager import TemporalWorkerEnvironment
from pipelex.temporal.temporal_task_manager import TemporalTaskManager


def pytest_addoption(parser: Parser):
    parser.addoption(
        "--worker",
        default=TemporalWorkerEnvironment.INTERNAL,
        help="Which temporal worker environment to use ('internal', 'external')",
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
