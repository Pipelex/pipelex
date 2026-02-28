from enum import StrEnum

from deep_flow.temporal_manager import TemporalWorkerEnvironment
from pytest import Parser


class DeepFlowPytestOption(StrEnum):
    WORKER_ENVIRONMENT = "--worker"


def pytest_addoption(parser: Parser):
    parser.addoption(
        DeepFlowPytestOption.WORKER_ENVIRONMENT,
        default=TemporalWorkerEnvironment.INTERNAL,
        help="Which temporal worker environment to use ('internal', 'external')",
    )
