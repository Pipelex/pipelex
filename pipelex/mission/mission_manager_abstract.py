# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from abc import ABC, abstractmethod
from typing import Optional

from pipelex.mission.mission import Mission


class MissionManagerAbstract(ABC):
    @abstractmethod
    def setup(self) -> None:
        pass

    @abstractmethod
    def teardown(self) -> None:
        pass

    @abstractmethod
    def get_optional_mission(self, mission_id: str) -> Optional[Mission]:
        pass

    @abstractmethod
    def get_mission(self, mission_id: str) -> Mission:
        pass

    @abstractmethod
    def add_new_mission(self) -> Mission:
        pass
