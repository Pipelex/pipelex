# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from typing import Dict, Optional

from pydantic import Field, RootModel
from typing_extensions import override

from pipelex.exceptions import MissionManagerNotFoundError
from pipelex.mission.mission import Mission
from pipelex.mission.mission_factory import MissionFactory
from pipelex.mission.mission_manager_abstract import MissionManagerAbstract

MissionManagerRoot = Dict[str, Mission]


class MissionManager(MissionManagerAbstract, RootModel[MissionManagerRoot]):
    root: MissionManagerRoot = Field(default_factory=dict)

    @override
    def setup(self):
        pass

    @override
    def teardown(self):
        self.root.clear()

    @override
    def get_optional_mission(self, mission_id: str) -> Optional[Mission]:
        return self.root.get(mission_id)

    @override
    def get_mission(self, mission_id: str) -> Mission:
        mission = self.get_optional_mission(mission_id=mission_id)
        if mission is None:
            raise MissionManagerNotFoundError(f"Mission {mission_id} not found")
        return mission

    def _set_mission(self, mission_id: str, mission: Mission) -> Mission:
        self.root[mission_id] = mission
        return mission

    @override
    def add_new_mission(self) -> Mission:
        mission = MissionFactory.make_mission()
        self._set_mission(mission_id=mission.mission_id, mission=mission)
        return mission
