from __future__ import annotations

from enum import StrEnum

from pipelex.graph.graphspec import GraphSpecMode


class PipeRunMode(StrEnum):
    LIVE = "live"
    DRY = "dry"

    @property
    def is_dry(self) -> bool:
        match self:
            case PipeRunMode.DRY:
                return True
            case PipeRunMode.LIVE:
                return False

    @property
    def is_live(self) -> bool:
        match self:
            case PipeRunMode.LIVE:
                return True
            case PipeRunMode.DRY:
                return False

    @property
    def graphspec_mode(self) -> GraphSpecMode:
        match self:
            case PipeRunMode.DRY:
                return GraphSpecMode.DRY
            case PipeRunMode.LIVE:
                return GraphSpecMode.LIVE
