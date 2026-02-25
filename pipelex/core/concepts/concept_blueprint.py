from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from pipelex.core.concepts.concept_structure_blueprint import RESERVED_FIELD_NAMES, ConceptStructureBlueprint
from pipelex.core.concepts.validation import is_concept_ref_or_code_valid

ConceptStructureBlueprintType = str | ConceptStructureBlueprint


class ConceptBlueprint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str | None = None
    description: str
    # TODO (non-blockiing): define a type for Union[str, ConceptStructureBlueprint] (ConceptChoice to be consistent with LLMChoice)
    structure: str | dict[str, ConceptStructureBlueprintType] | None = None
    # TODO: restore possibility of multiple refiles
    refines: str | None = None

    @field_validator("refines", mode="before")
    @classmethod
    def validate_refines(cls, refines: str | None = None) -> str | None:
        """Validate the refines field.

        Refines can be either:
        - A native concept ref (e.g., "native.Text", "Text")
        - A non-native concept ref (e.g., "myapp.BaseEntity") for concept-to-concept inheritance

        Non-native concept refs are allowed since dependencies are loaded in topological order,
        ensuring the refined concept exists before the refining concept is constructed.
        """
        if refines is None:
            return None

        # Check if it's a valid concept ref or code (domain.ConceptCode or ConceptCode in PascalCase)
        if is_concept_ref_or_code_valid(concept_ref_or_code=refines):
            return refines

        # Invalid refines value
        msg = f"Refines '{refines}' must be a valid concept ref (domain.ConceptCode) or concept code (PascalCase)"
        raise ValueError(msg)

    @field_validator("structure", mode="before")
    @classmethod
    def validate_structure_field_names(
        cls, structure: str | dict[str, ConceptStructureBlueprintType] | None
    ) -> str | dict[str, ConceptStructureBlueprintType] | None:
        if isinstance(structure, dict):
            # Check for reserved field names
            reserved_fields_used = [field_name for field_name in structure if field_name in RESERVED_FIELD_NAMES]
            if reserved_fields_used:
                fields_word = "field" if len(reserved_fields_used) == 1 else "fields"
                reserved_fields_used_list = ", ".join(f"'{name}'" for name in sorted(reserved_fields_used))
                reserved_names = ", ".join(f"'{name}'" for name in sorted(RESERVED_FIELD_NAMES))
                msg = (
                    f"Cannot use reserved fields in concept structure. "
                    f"Problematic fields: '{reserved_fields_used_list}'. "
                    f"All reserved field names are: {reserved_names}"
                )
                raise ValueError(msg)

            # Check for field names starting with underscore (reserved for internal use)
            underscore_fields = [field_name for field_name in structure if field_name.startswith("_")]
            if underscore_fields:
                fields_word = "field" if len(underscore_fields) == 1 else "fields"
                underscore_list = ", ".join(f"'{name}'" for name in sorted(underscore_fields))
                msg = (
                    f"Cannot use '{fields_word}' starting with underscore in concept structure. "
                    f"Problematic fields: '{underscore_list}'. "
                    "Field names starting with '_' are reserved for internal use by Pipelex."
                )
                raise ValueError(msg)
        return structure

    @model_validator(mode="before")
    @classmethod
    def validate_mutually_exclusive_fields(cls, values: dict[str, Any] | str) -> dict[str, Any] | str:
        """Validate that refines and structure are not both set."""
        if isinstance(values, dict) and values.get("refines") and values.get("structure"):
            msg = (
                f"A concept cannot have both 'refines' and 'structure'. "
                f"Got refines='{values.get('refines')}' and structure='{values.get('structure')}'. "
                f"Concept description: '{values.get('description')}'"
            )
            raise ValueError(msg)
        return values
