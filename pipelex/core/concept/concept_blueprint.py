from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


class ConceptBlueprint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    definition: str
    structure: Optional[Union[str, Dict[str, Any]]] = None
    refines: Union[str, List[str]] = Field(default_factory=list)
    domain: Optional[str] = None
