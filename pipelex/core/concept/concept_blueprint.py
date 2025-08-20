from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing_extensions import Self

from pipelex.exceptions import ConceptFactoryError


class ConceptStructureBlueprintError(ConceptFactoryError):
    pass


class ConceptStructureBlueprint(BaseModel):
    definition: str
    type: Literal["text", "list", "dict", "integer", "boolean", "number", "date", None] = None
    item_type: Optional[str] = None
    key_type: Optional[str] = None
    value_type: Optional[str] = None
    choices: Optional[List[str]] = Field(default_factory=list)
    required: Optional[bool] = Field(default=True)

    @model_validator(mode="after")
    def validate_structure_blueprint(self) -> Self:
        """Validate the structure blueprint according to type rules."""
        # If type is None (array), choices must not be None
        if self.type is None and not self.choices:
            raise ValueError("When type is None (array), choices must not be empty")

        # If type is "dict", key_type and value_type must not be empty
        if self.type == "dict":
            if not self.key_type:
                raise ValueError("When type is 'dict', key_type must not be empty")
            if not self.value_type:
                raise ValueError("When type is 'dict', value_type must not be empty")

        return self


ConceptStructureBlueprintType = Union[str, ConceptStructureBlueprint]


class ConceptBlueprint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    definition: str
    structure: Optional[Union[str, Dict[str, ConceptStructureBlueprintType]]] = None
    refines: Optional[Union[str, List[str]]] = Field(default_factory=list)

    @model_validator(mode="after")
    def model_validate_blueprint(self) -> Self:
        return self

    def structure_to_field_def(self) -> Dict[str, Any]:
        if isinstance(self.structure, str):
            raise ValueError("structure_to_field_def can only be called when structure is a dict in the blueprint")

        if self.structure is None:
            return {}

        # Process the dict structure
        result: Dict[str, Any] = {}
        for key, value in self.structure.items():
            if isinstance(value, ConceptStructureBlueprint):
                # Use model_dump for ConceptStructureBlueprint instances
                result[key] = value.model_dump()
            else:
                # This shouldn't happen based on the type hints, but handle it gracefully
                result[key] = {"type": "text", "definition": value}

        return result
