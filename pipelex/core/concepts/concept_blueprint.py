import keyword
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, SerializerFunctionWrapHandler, field_validator, model_serializer, model_validator

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
    hints: dict[str, str] | None = None
    """MTHDS intent hints (spec: intent-hints.md) — non-normative presentation intent. Shape is
    strict (flat string->string table), content is lenient (unknown entries preserved, advisory
    lint warns). An empty table is equivalent to no hints and normalizes to absence."""

    @field_validator("hints", mode="after")
    @classmethod
    def normalize_empty_hints(cls, hints: dict[str, str] | None) -> dict[str, str] | None:
        return hints or None

    @model_serializer(mode="wrap")
    def serialize_without_absent_hints(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        """Absent hints are an absent member — never `null` (spec rule; keeps hint-free crate
        fingerprints byte-identical to before hints existed). Deliberately NOT a blanket
        `exclude_none`: the crate spec's general absent-members canonicalization is a separate
        forward contract whose adoption would migrate every existing fingerprint.
        """
        dumped: dict[str, Any] = handler(self)
        if dumped.get("hints") is None:
            dumped.pop("hints", None)
        return dumped

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
            invalid_identifier_fields = [field_name for field_name in structure if not field_name.isidentifier() or keyword.iskeyword(field_name)]
            if invalid_identifier_fields:
                invalid_list = ", ".join(f"'{name}'" for name in sorted(invalid_identifier_fields))
                msg = (
                    "Concept structure field names must be valid Python identifiers and cannot be Python keywords. "
                    f"Problematic fields: {invalid_list}."
                )
                raise ValueError(msg)

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
    def validate_mutually_exclusive_fields(cls, values: Any) -> Any:
        """Validate that refines and structure are not both set."""
        # mode="before" receives raw, unvalidated input — a non-dict (e.g. a plain string in a
        # `ConceptBlueprint | str` union) must fall through untouched rather than crash on dict access
        if not isinstance(values, dict):
            return values
        fields = cast("dict[str, Any]", values)
        if fields.get("refines") and fields.get("structure"):
            msg = (
                f"A concept cannot have both 'refines' and 'structure'. "
                f"Got refines='{fields.get('refines')}' and structure='{fields.get('structure')}'. "
                f"Concept description: '{fields.get('description')}'"
            )
            raise ValueError(msg)
        return fields
