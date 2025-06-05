from abc import ABC, abstractmethod
from typing import Optional

from pipelex.reporting.reporting_protocol import ReportingProtocol


class InferenceWorkerAbstract(ABC):
    def __init__(
        self,
        report_delegate: Optional[ReportingProtocol] = None,
    ):
        self.report_delegate = report_delegate

    @property
    @abstractmethod
    def desc(self) -> str:
        pass
