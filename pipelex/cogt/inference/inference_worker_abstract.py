from abc import ABC, abstractmethod
from typing import Optional

from pipelex.reporting.reporting_protocol import ReportingProtocol


class InferenceWorkerAbstract(ABC):
    def __init__(
        self,
        reporting_delegate: Optional[ReportingProtocol] = None,
    ):
        self.reporting_delegate = reporting_delegate

    def setup(self):
        pass

    def teardown(self):
        pass

    @property
    @abstractmethod
    def desc(self) -> str:
        pass
