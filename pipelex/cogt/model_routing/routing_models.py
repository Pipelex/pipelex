from pydantic import BaseModel

from pipelex.types import StrEnum


class BackendMatchingMethod(StrEnum):
    DEFAULT = "default"
    EXACT_MATCH = "exact_match"
    PATTERN_MATCH = "pattern_match"


class BackendMatchForModel(BaseModel):
    model_name: str
    backend_name: str
    routing_profile_name: str
    matching_method: BackendMatchingMethod
    matched_pattern: str | None
