from collections.abc import Callable, Generator
from pathlib import Path

import pytest

from pipelex import log
from pipelex.hub import get_library_manager, set_current_library
from pipelex.pipelex import Pipelex
from pipelex.system.runtime import IntegrationMode, runtime_manager

pytest_plugins = [
    "pipelex.test_extras.shared_pytest_plugins",
]

TEST_OUTPUTS_DIR = "temp/test_outputs"


def _get_test_integration_mode() -> IntegrationMode:
    """Return the appropriate integration mode for tests.

    Uses CI mode in CI environments (no terms acceptance required),
    PYTEST mode for local development (terms acceptance required).
    """
    if runtime_manager.is_ci_testing:
        return IntegrationMode.CI
    else:
        return IntegrationMode.PYTEST


@pytest.fixture(scope="module")
def routing_profile_setup(request: pytest.FixtureRequest):  # noqa: ARG001  # pyright: ignore[reportUnusedFunction]
    """Hook for downstream conftest to inject routing profile setup before Pipelex init.

    This fixture can be overridden in integration/conftest.py to setup routing overrides.
    Note: Used by reset_pipelex_config_fixture via fixture dependency.
    """
    return


@pytest.fixture(scope="module", autouse=True)
def reset_pipelex_config_fixture(routing_profile_setup: str | None):  # noqa: ARG001
    Pipelex.make(integration_mode=_get_test_integration_mode())
    yield
    Pipelex.teardown_if_needed()


@pytest.fixture(scope="class")
def load_test_library() -> Generator[Callable[[list[Path]], None], None, None]:
    library_id = None

    def _load(library_dirs: list[Path]) -> None:
        nonlocal library_id
        library_manager = get_library_manager()
        library_id, _ = library_manager.open_library()
        set_current_library(library_id=library_id)

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
def load_empty_library() -> Generator[Callable[[], str], None, None]:
    library_id = None

    def _load() -> str:
        nonlocal library_id
        library_manager = get_library_manager()
        library_id, _ = library_manager.open_library()
        set_current_library(library_id=library_id)

        log.verbose(f"Opened empty library: {library_id}")
        return library_id

    yield _load

    if library_id is not None:
        library_manager = get_library_manager()
        library_manager.teardown(library_id=library_id)
        log.verbose(f"Torn down library: {library_id}")
