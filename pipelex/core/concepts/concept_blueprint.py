from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from pipelex.core.concepts.concept_native import NativeConceptCode
from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint
from pipelex.core.concepts.exceptions import ConceptBlueprintValueError


class ConceptBlueprint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str | None = None
    description: str
    # TODO (non-blockiing): define a type for Union[str, ConceptStructureBlueprint] (ConceptChoice to be consistent with LLMChoice)
    structure: str | dict[str, str | ConceptStructureBlueprint] | None = None
    # TODO: restore possibility of multiple refiles
    refines: str | None = None

    @field_validator("refines", mode="before")
    @classmethod
    def validate_refines(cls, refines: str | None = None) -> str | None:
        if refines is not None:
            if not NativeConceptCode.get_validated_native_concept_string(concept_string_or_code=refines):
                msg = f"Refine '{refines}' is not a native concept and we currently can only refine native concepts"
                raise ConceptBlueprintValueError(msg)
        return refines

    @model_validator(mode="before")
    @classmethod
    def validate_blueprint(cls, values: dict[str, Any] | str) -> dict[str, Any] | str:
        if isinstance(values, dict) and values.get("refines") and values.get("structure"):
            msg = (
                f"Forbidden to have refines and structure at the same time: `{values.get('refines')}` "
                f"and `{values.get('structure')}` for concept that has the definition `{values.get('description')}`"
            )
            raise ConceptBlueprintValueError(msg)
        return values
