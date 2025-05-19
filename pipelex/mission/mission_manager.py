# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from enum import StrEnum
from typing import Any, Dict, Optional

from pydantic import Field, RootModel

from pipelex.mission.mission import Mission

MissionManagerRoot = Dict[str, Mission]


class MissionManager(RootModel[MissionManagerRoot]):
    root: MissionManagerRoot = Field(default_factory=dict)

    def reset(self):
        self.root.clear()

    def get_mission(self, mission_id: str) -> Optional[Mission]:
        return self.root.get(mission_id)

    def set_mission(self, mission_id: str, mission: Mission) -> Mission:
        self.root[mission_id] = mission
        return mission
