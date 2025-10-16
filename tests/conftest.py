import pytest
from rich.console import Console
from rich.traceback import Traceback

import pipelex.config
import pipelex.pipelex
from pipelex import log
from pipelex.config import get_config
from pipelex.hub import get_report_delegate

pytest_plugins = [
    "pipelex.test_extras.shared_pytest_plugins",
]

TEST_OUTPUTS_DIR = "temp/test_outputs"


@pytest.fixture(scope="module", autouse=True)
def reset_pipelex_config_fixture():
    # Code to run before each test
    Console().print("[magenta]pipelex setup[/magenta]")
    try:
        pipelex_instance = pipelex.pipelex.Pipelex.make()
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
