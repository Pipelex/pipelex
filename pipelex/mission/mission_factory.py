import shortuuid

from pipelex.config import get_config
from pipelex.mission.mission import Mission


class MissionFactory:
    @classmethod
    def make_mission(cls) -> Mission:
        return Mission(
            mission_id=shortuuid.uuid(),
            report_config=get_config().cogt.cogt_report_config,
        )
