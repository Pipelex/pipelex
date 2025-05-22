# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

import shortuuid

from pipelex.mission.mission import Mission


class MissionFactory:
    @classmethod
    def make_mission(cls) -> Mission:
        return Mission(
            mission_id=shortuuid.uuid(),
        )
