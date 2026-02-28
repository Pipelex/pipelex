from enum import StrEnum

from pytest import Parser

from pipelex.deep_flow.temporal_manager import TemporalWorkerEnvironment


class DeepFlowPytestOption(StrEnum):
    WORKER_ENVIRONMENT = "--worker"


def pytest_addoption(parser: Parser):
    parser.addoption(
        DeepFlowPytestOption.WORKER_ENVIRONMENT,
        default=TemporalWorkerEnvironment.INTERNAL,
        help="Which temporal worker environment to use ('internal', 'external')",
    )
