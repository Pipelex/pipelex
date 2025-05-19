from enum import StrEnum
from typing import Any, Dict, Optional

import shortuuid
from pydantic import BaseModel, Field


class Mission(BaseModel):
    mission_id: str = Field(default_factory=shortuuid.uuid)
