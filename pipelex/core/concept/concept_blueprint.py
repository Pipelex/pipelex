from typing import Any, Dict, List, Optional, Union

from kajson.kajson_manager import KajsonManager
from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing_extensions import Self

from pipelex import log
from pipelex.core.stuff.stuff_content import StuffContent


class ConceptBlueprint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    definition: str
    structure: Optional[Union[str, Dict[str, Any]]] = None
    refines: Optional[Union[str, List[str]]] = Field(default_factory=list)

    @model_validator(mode="after")
    def model_validate_blueprint(self) -> Self:
        return self.validate_blueprint()

    def validate_blueprint(self) -> Self:
        # Validate structure if it's a string reference to a class name
        if isinstance(self.structure, str):
            if not self.is_valid_structure_class(structure_class_name=self.structure):
                raise ValueError(f"Structure class '{self.structure}' is not a registered subclass of StuffContent")
        return self

    @classmethod
    def is_valid_structure_class(cls, structure_class_name: str) -> bool:
        # We get_class_registry directly from KajsonManager instead of pipelex hub to avoid circular import
        if KajsonManager.get_class_registry().has_subclass(name=structure_class_name, base_class=StuffContent):
            return True
        else:
            # We get_class_registry directly from KajsonManager instead of pipelex hub to avoid circular import
            if KajsonManager.get_class_registry().has_class(name=structure_class_name):
                log.warning(f"Concept class '{structure_class_name}' is registered but it's not a subclass of StuffContent")
            return False
