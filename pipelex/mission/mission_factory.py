import shortuuid

from pipelex.mission.mission import Mission


class MissionFactory:
    @classmethod
    def make_mission(cls) -> Mission:
        return Mission(
            mission_id=shortuuid.uuid(),
        )
