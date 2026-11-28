from typing import Any, cast

from pydantic import BaseModel, ConfigDict, SerializerFunctionWrapHandler, field_validator, model_serializer, model_validator

from pipelex.core.concepts.concept_structure_blueprint import (
    RESERVED_FIELD_NAMES,
    ConceptStructureBlueprint,
    FieldNameRefusal,
    structure_field_name_refusal,
)
from pipelex.core.concepts.exceptions import ContractFactInvalidError
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.concepts.validation import is_concept_ref_or_code_valid
from pipelex.core.qualified_ref import QualifiedRef
from pipelex.language.contract_facts import ContractFactKey, ContractFactReason, malformed_fact_message

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
    unit: str | None = None
    """What a number-valued concept counts (spec: mthds-format.md, Units): allowed only on a concept whose refinement chain
    reaches `native.Number`, and inherited by its refiners, the nearer declaration winning. A refinement of another concept
    of this library is judged once the library's concepts are known (`pipelex.libraries.contract_fact_sites`)."""

    @field_validator("unit", mode="before")
    @classmethod
    def refuse_malformed_unit(cls, unit: Any) -> Any:
        if unit is None:
            return unit
        message = malformed_fact_message(key=ContractFactKey.UNIT, value=unit)
        if message is not None:
            raise ContractFactInvalidError(message, fact=ContractFactKey.UNIT, reason=ContractFactReason.MALFORMED)
        return unit

    @model_validator(mode="after")
    def refuse_unit_on_a_concept_not_number_valued(self) -> "ConceptBlueprint":
        """Refuse a `unit` on a concept that is known here not to be number-valued: a structured or description-only
        concept, or one refining a native other than `Number`. A concept refining another declared concept is judged once
        the library's concepts are known.
        """
        if self.unit is None or self.refines_number_or_unknown:
            return self
        msg = "'unit' is allowed only on a concept whose refinement chain reaches native.Number, and this concept is not number-valued"
        raise ContractFactInvalidError(msg, fact=ContractFactKey.UNIT, reason=ContractFactReason.INAPPLICABLE)

    @property
    def refines_number_or_unknown(self) -> bool:
        """Whether the concept refines `native.Number`, is backed by the native Number structure class (`NumberContent`), or
        refines a declared concept whose class this blueprint cannot know. A class name maps by identity to its native, as
        `pipelex.libraries.concept_value_kinds` judges it.
        """
        native_code: NativeConceptCode
        if isinstance(self.structure, str):
            class_native = next((code for code in NativeConceptCode if code.structure_class_name == self.structure), None)
            if class_native is None:
                return False
            native_code = class_native
        elif self.structure is not None or not self.refines:
            return False
        elif not NativeConceptCode.is_native_concept_ref_or_code(concept_ref_or_code=self.refines):
            return True
        else:
            native_code = NativeConceptCode(QualifiedRef.parse(self.refines).local_code)
        match native_code:
            case NativeConceptCode.NUMBER:
                return True
            case (
                NativeConceptCode.DYNAMIC
                | NativeConceptCode.TEXT
                | NativeConceptCode.IMAGE
                | NativeConceptCode.DOCUMENT
                | NativeConceptCode.HTML
                | NativeConceptCode.TEXT_AND_IMAGES
                | NativeConceptCode.YES_NO
                | NativeConceptCode.CHOICE
                | NativeConceptCode.RATING
                | NativeConceptCode.DATE
                | NativeConceptCode.TIME
                | NativeConceptCode.PAGE
                | NativeConceptCode.JSON
                | NativeConceptCode.MARKDOWN
                | NativeConceptCode.SEARCH_RESULT
                | NativeConceptCode.COMPOSITE
                | NativeConceptCode.ANYTHING
            ):
                return False

    @field_validator("hints", mode="after")
    @classmethod
    def normalize_empty_hints(cls, hints: dict[str, str] | None) -> dict[str, str] | None:
        # Sorted here so every serialization is canonical (spec: hints entries emitted sorted by
        # key); hint key order is not semantic, unlike structure-field order.
        return dict(sorted(hints.items())) if hints else None

    @model_serializer(mode="wrap")
    def serialize_without_absent_hints(self, handler: SerializerFunctionWrapHandler):
        """Absent hints are an absent member — never `null` (spec rule; keeps hint-free crate
        fingerprints byte-identical to before hints existed). Deliberately NOT a blanket
        `exclude_none`: the crate spec's general absent-members canonicalization is a separate
        forward contract whose adoption would migrate every existing fingerprint.

        The return is deliberately unannotated, and stays that way. Pydantic turns a serializer's
        return annotation into the model's serialization JSON Schema and prefers it over the schema
        it would generate, so a `-> dict[str, Any]` here publishes this model as an opaque
        `{"type": "object", "additionalProperties": true}` — no properties, no `required`, no
        closed shape — for every consumer that generates response schemas (FastAPI always does).
        """
        dumped: dict[str, Any] = handler(self)
        if dumped.get("hints") is None:
            dumped.pop("hints", None)
        # An absent unit is an absent member too, so a library that authors none keeps its fingerprint.
        if dumped.get("unit") is None:
            dumped.pop("unit", None)
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
            # One rule for a field name, shared with every name that stands for a field: each name is refused by
            # the first rule it breaks, and each rule keeps its own message.
            refusals = {field_name: structure_field_name_refusal(field_name=field_name) for field_name in structure}
            invalid_identifier_fields = [field_name for field_name, refusal in refusals.items() if refusal is FieldNameRefusal.NOT_AN_IDENTIFIER]
            if invalid_identifier_fields:
                invalid_list = ", ".join(f"'{name}'" for name in sorted(invalid_identifier_fields))
                msg = (
                    "Concept structure field names must be valid Python identifiers and cannot be Python keywords. "
                    f"Problematic fields: {invalid_list}."
                )
                raise ValueError(msg)

            # Check for reserved field names
            reserved_fields_used = [field_name for field_name, refusal in refusals.items() if refusal is FieldNameRefusal.RESERVED]
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
            underscore_fields = [field_name for field_name, refusal in refusals.items() if refusal is FieldNameRefusal.UNDERSCORE]
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
