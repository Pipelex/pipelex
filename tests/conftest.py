from pathlib import Path

import pytest

from pipelex import log
from pipelex.hub import get_library_manager, set_current_library_id
from pipelex.pipelex import Pipelex
from pipelex.system.runtime import IntegrationMode

pytest_plugins = [
    "pipelex.test_extras.shared_pytest_plugins",
]

TEST_OUTPUTS_DIR = "temp/test_outputs"


@pytest.fixture(scope="module")
def routing_profile_setup(request: pytest.FixtureRequest):  # noqa: ARG001  # pyright: ignore[reportUnusedFunction]
    """Hook for downstream conftest to inject routing profile setup before Pipelex init.

    This fixture can be overridden in integration/conftest.py to setup routing overrides.
    Note: Used by reset_pipelex_config_fixture via fixture dependency.
    """
    return


@pytest.fixture(scope="module", autouse=True)
def reset_pipelex_config_fixture(routing_profile_setup: str | None):  # noqa: ARG001
    pipelex_instance = Pipelex.make(integration_mode=IntegrationMode.PYTEST)

    yield
    pipelex_instance.teardown()


@pytest.fixture(scope="class")
def load_test_library():
    library_id = None

    def _load(library_dirs: list[Path]) -> None:
        nonlocal library_id
        library_manager = get_library_manager()
        library_id, _ = library_manager.open_library()
        set_current_library_id(library_id=library_id)

        library_manager.load_libraries(
            library_id=library_id,
            library_dirs=library_dirs,
        )

        log.verbose(f"Loaded libraries: {[str(p) for p in library_dirs]}")

    yield _load

    if library_id is not None:
        library_manager = get_library_manager()
        library_manager.teardown(library_id=library_id)
        log.verbose(f"Torn down library: {library_id}")


@pytest.fixture(scope="class")
def load_empty_library():
    library_id = None

    def _load() -> None:
        nonlocal library_id
        library_manager = get_library_manager()
        library_id, _ = library_manager.open_library()
        set_current_library_id(library_id=library_id)

        log.verbose(f"Opened empty library: {library_id}")

    yield _load

    if library_id is not None:
        library_manager = get_library_manager()
        library_manager.teardown(library_id=library_id)
        log.verbose(f"Torn down library: {library_id}")
