# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

# pyright: reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportMissingTypeArgument=false
from enum import StrEnum
from typing import Any, Dict, List, Optional, Protocol, Tuple

from pipelex import log
from pipelex.core.stuff import Stuff
from pipelex.pipe_controllers.pipe_condition_details import PipeConditionDetails


class MissionTrackerProtocol(Protocol):
    # def reset(self): ...
    def add_pipe_step(
        self,
        from_stuff: Optional[Stuff],
        to_stuff: Stuff,
        pipe_code: str,
        comment: str,
        pipe_layer: List[str],
        as_item_index: Optional[int] = None,
        is_with_edge: bool = True,
    ): ...

    def add_batch_step(
        self,
        from_stuff: Optional[Stuff],
        to_stuff: Stuff,
        to_branch_index: int,
        pipe_layer: List[str],
        comment: str,
    ): ...

    def add_aggregate_step(
        self,
        from_stuff: Stuff,
        to_stuff: Stuff,
        pipe_layer: List[str],
        comment: str,
    ): ...

    def add_condition_step(
        self,
        from_stuff: Stuff,
        to_condition: PipeConditionDetails,
        condition_expression: str,
        pipe_layer: List[str],
        comment: str,
    ): ...

    def add_choice_step(
        self,
        from_condition: PipeConditionDetails,
        to_stuff: Stuff,
        pipe_layer: List[str],
        comment: str,
    ): ...
