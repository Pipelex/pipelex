from pathlib import Path

import pytest
from rich.traceback import Traceback

from pipelex import log
from pipelex.config.config import PipelexConfig, get_config
from pipelex.hub import get_console, get_library_manager, get_report_delegate, set_current_library_id
from pipelex.libraries.library_ids import SpecialLibraryId
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
    # Code to run before each test
    # The routing_profile_setup dependency ensures any routing overrides happen first
    console = get_console()
    console.print("[magenta]pipelex setup[/magenta]")
    try:
        pipelex_instance = Pipelex.make(integration_mode=IntegrationMode.PYTEST)
        library_manager = get_library_manager()
        library_manager.setup()
        set_current_library_id(library_id=SpecialLibraryId.TEST)
        library_manager.open_library(library_id=SpecialLibraryId.TEST)
        # TODO: EACH TEST should load the required libraries for the test... The conf tests should load
        library_manager.load_libraries(library_id=SpecialLibraryId.TEST, library_dirs=[Path("tests/")])
        config = get_config()
        log.verbose(config, title="Test config")
        assert isinstance(config, PipelexConfig)
    except Exception as exc:
        console.print(Traceback())
        pytest.exit(f"Critical Pipelex setup error: {exc}")
    yield
    # Code to run after each test
    get_report_delegate().generate_report()
    console.print("[dim magenta]pipelex teardown[/dim magenta]")
    pipelex_instance.teardown()
