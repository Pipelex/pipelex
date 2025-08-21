import pytest
from pytest import FixtureRequest, Parser

from pipelex.core.pipes.pipe_run_params import PipeRunMode
from pipelex.tools.runtime_manager import RunMode, runtime_manager


@pytest.fixture(scope="session", autouse=True)
def set_run_mode():
    runtime_manager.set_run_mode(run_mode=RunMode.UNIT_TEST)


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
