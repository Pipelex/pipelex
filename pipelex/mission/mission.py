from pydantic import BaseModel, PrivateAttr

from pipelex.cogt.config_cogt import CogtReportConfig
from pipelex.cogt.inference.inference_report_delegate import InferenceReportDelegate
from pipelex.cogt.inference.inference_report_manager import InferenceReportManager


class Mission(BaseModel):
    mission_id: str
    _inference_report_manager: InferenceReportManager = PrivateAttr()

    def __init__(self, mission_id: str, report_config: CogtReportConfig):
        super().__init__(mission_id=mission_id)
        self._inference_report_manager = InferenceReportManager(
            report_config=report_config,
            mission_id=mission_id,
        )

    def get_report_delegate(self) -> InferenceReportDelegate:
        return self._inference_report_manager
