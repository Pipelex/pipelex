from pathlib import Path

import pytest
from rich.console import Console
from rich.traceback import Traceback

import pipelex.config
import pipelex.pipelex
from pipelex import log
from pipelex.config import get_config
from pipelex.hub import get_library_manager, get_report_delegate, set_current_library_id
from pipelex.libraries.library_ids import SpecialLibraryId
from pipelex.system.runtime import IntegrationMode

pytest_plugins = [
    "pipelex.test_extras.shared_pytest_plugins",
]

TEST_OUTPUTS_DIR = "temp/test_outputs"


@pytest.fixture(scope="module", autouse=True)
def reset_pipelex_config_fixture():
    # Code to run before each test
    Console().print("[magenta]pipelex setup[/magenta]")
    try:
        pipelex_instance = pipelex.pipelex.Pipelex.make(integration_mode=IntegrationMode.PYTEST)
        library_manager = get_library_manager()
        library_manager.setup()
        set_current_library_id(library_id=SpecialLibraryId.TEST)
        library_manager.open_library(library_id=SpecialLibraryId.TEST)
        library_manager.load_libraries(library_id=SpecialLibraryId.TEST, library_dirs=[Path("tests/test_pipelines/")])
        config = get_config()
        log.verbose(config, title="Test config")
        assert isinstance(config, pipelex.config.PipelexConfig)
    except Exception as exc:
        Console().print(Traceback())
        pytest.exit(f"Critical Pipelex setup error: {exc}")
    yield
    # Code to run after each test
    get_report_delegate().generate_report()
    Console().print("[magenta]pipelex teardown[/magenta]")
    pipelex_instance.teardown()
