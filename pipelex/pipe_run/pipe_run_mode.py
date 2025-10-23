from __future__ import annotations

from pipelex.types import StrEnum


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
