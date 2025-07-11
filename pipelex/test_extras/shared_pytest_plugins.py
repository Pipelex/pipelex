import pytest
from pytest import FixtureRequest, Parser

from pipelex.core.pipe_run_params import PipeRunMode
from pipelex.libraries.library_config import LibraryConfig
from pipelex.tools.runtime_manager import RunMode, runtime_manager


@pytest.fixture(scope="session", autouse=True)
def set_run_mode():
    runtime_manager.set_run_mode(run_mode=RunMode.UNIT_TEST)


@pytest.fixture(scope="session")
def manage_pipelex_libraries():
    LibraryConfig(config_folder_path="./pipelex_libraries").export_libraries(overwrite=False)
    yield
    # TODO: make it safe to erase/replace standard libraries in client projects without touching custom stuff
    # LibraryConfig.remove_libraries()


@pytest.fixture(scope="session")
def manage_pipelex_libraries_with_overwrite():
    LibraryConfig(config_folder_path="./pipelex_libraries").export_libraries(overwrite=True)
    yield
    # TODO: make it safe to erase/replace standard libraries in client projects without touching custom stuff
    # LibraryConfig.remove_libraries()


def pytest_addoption(parser: Parser):
    parser.addoption(
        "--pipe-run-mode",
        action="store",
        default="dry",
        help="Pipe run mode: 'live' or 'dry'",
        choices=("live", "dry"),
    )


@pytest.fixture
def pipe_run_mode(request: FixtureRequest) -> PipeRunMode:
    mode_str = request.config.getoption("--pipe-run-mode")
    return PipeRunMode(mode_str)
