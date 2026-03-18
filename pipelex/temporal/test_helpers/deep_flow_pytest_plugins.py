from pytest import Parser

from pipelex.temporal.temporal_manager import TemporalWorkerEnvironment
from pipelex.types import StrEnum


class DeepFlowPytestOption(StrEnum):
    WORKER_ENVIRONMENT = "--worker"


def pytest_addoption(parser: Parser):
    parser.addoption(
        DeepFlowPytestOption.WORKER_ENVIRONMENT,
        type=TemporalWorkerEnvironment,
        default=TemporalWorkerEnvironment.INTERNAL,
        help="Which temporal worker environment to use ('internal', 'external')",
    )
