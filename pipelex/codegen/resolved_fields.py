"""Neutral, language-agnostic resolved-field layer.

Every codegen emitter (Python structures, plain pydantic, TS/Zod, ...) consumes the same
resolved shape rather than re-deriving the semantic mapping from `ConceptStructureBlueprint`.
This module owns that mapping — the one place that turns an authored structure field into a
resolved type tree:

- inline `choices` -> a literal type,
- primitive field types -> their neutral kind,
- `concept` / list-of-`concept` -> a concept reference (native-flagged, bare refs promoted to the
  local domain), leaving the language-specific class spelling to each emitter,
- `list` / `dict` -> recursive item / value types.

Where the source is imprecise — a `list` with no `item_type`, a `dict` with no resolvable value
type — the resolved type is `ANY` carrying an explicit imprecision marker, so an emitter surfaces
the imprecision (a TODO / caveat) instead of guessing a shape. The layer never emits a language;
it produces neutral fields an emitter walks.
"""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict

from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint, ConceptStructureBlueprintFieldType
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.qualified_ref import QualifiedRef


class ResolvedTypeKind(StrEnum):
    """The neutral type kinds an emitter maps to its own language."""

    TEXT = "text"
    NUMBER = "number"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    DATE = "date"
    DATETIME = "datetime"
    LITERAL = "literal"
    CONCEPT = "concept"
    LIST = "list"
    DICT = "dict"
    ANY = "any"


class ResolvedType(BaseModel):
    """A resolved, language-neutral type tree node.

    Only the members relevant to `kind` are populated: `choices` for LITERAL, `concept_ref` /
    `is_native` for CONCEPT, `item` for LIST, `key` / `value` for DICT. `imprecise` (with an
    optional reason) is set on ANY nodes that stand in for a source the author left unspecified.
    """

    model_config = ConfigDict(frozen=True)

    kind: ResolvedTypeKind
    choices: list[str] | None = None
    concept_ref: str | None = None
    is_native: bool = False
    item: "ResolvedType | None" = None
    key: "ResolvedType | None" = None
    value: "ResolvedType | None" = None
    imprecise: bool = False
    imprecision_reason: str | None = None


class ResolvedField(BaseModel):
    """One resolved structure field: its name, docs, presence, default, and neutral type."""

    model_config = ConfigDict(frozen=True)

    name: str
    description: str
    required: bool
    default_value: Any | None = None
    resolved_type: ResolvedType


def resolve_structure_fields(
    structure_blueprint: dict[str, ConceptStructureBlueprint],
    *,
    local_domain: str | None = None,
) -> list[ResolvedField]:
    """Resolve every field of a structure blueprint into the neutral form, preserving field order."""
    return [
        resolve_field(field_name, blueprint=field_blueprint, local_domain=local_domain) for field_name, field_blueprint in structure_blueprint.items()
    ]


def iter_imprecision_reasons(resolved_type: ResolvedType) -> list[str]:
    """Collect every declared-imprecision reason in a resolved-type tree, depth-first.

    Imprecision markers are set (never guessed) wherever the source under-specifies a shape — a
    `list` with no `item_type`, a `concept` field with no ref, an unrecognized nested type name.
    They are write-only until an emitter surfaces them: this walker is how an emitter turns the
    markers on a field's whole type tree into caveats (a `# imprecise:` comment / JSDoc note)
    instead of emitting a silent `Any` / `z.any()`.
    """
    reasons: list[str] = []
    if resolved_type.imprecise and resolved_type.imprecision_reason:
        reasons.append(resolved_type.imprecision_reason)
    for child in (resolved_type.item, resolved_type.key, resolved_type.value):
        if child is not None:
            reasons.extend(iter_imprecision_reasons(child))
    return reasons


def resolve_field(
    field_name: str,
    *,
    blueprint: ConceptStructureBlueprint,
    local_domain: str | None = None,
) -> ResolvedField:
    """Resolve a single structure-blueprint field into a neutral `ResolvedField`."""
    return ResolvedField(
        name=field_name,
        description=blueprint.description,
        required=blueprint.required,
        default_value=blueprint.default_value,
        resolved_type=_resolve_type(blueprint, local_domain=local_domain),
    )


def _resolve_type(blueprint: ConceptStructureBlueprint, *, local_domain: str | None) -> ResolvedType:
    # Inline choices win over `type` (a typed-choices field is still a literal set).
    if blueprint.choices:
        return ResolvedType(kind=ResolvedTypeKind.LITERAL, choices=blueprint.choices)
    if blueprint.type is None:
        # Validation guarantees `type is None` only alongside choices (handled above); this is a
        # defensive fallback matching the historical "assume text" behavior.
        return ResolvedType(kind=ResolvedTypeKind.TEXT)

    match blueprint.type:
        case ConceptStructureBlueprintFieldType.TEXT:
            return ResolvedType(kind=ResolvedTypeKind.TEXT)
        case ConceptStructureBlueprintFieldType.NUMBER:
            return ResolvedType(kind=ResolvedTypeKind.NUMBER)
        case ConceptStructureBlueprintFieldType.INTEGER:
            return ResolvedType(kind=ResolvedTypeKind.INTEGER)
        case ConceptStructureBlueprintFieldType.BOOLEAN:
            return ResolvedType(kind=ResolvedTypeKind.BOOLEAN)
        case ConceptStructureBlueprintFieldType.DATE:
            return ResolvedType(kind=ResolvedTypeKind.DATE)
        case ConceptStructureBlueprintFieldType.DATETIME:
            return ResolvedType(kind=ResolvedTypeKind.DATETIME)
        case ConceptStructureBlueprintFieldType.CONCEPT:
            return _resolve_concept(blueprint.concept_ref, local_domain=local_domain)
        case ConceptStructureBlueprintFieldType.LIST:
            return ResolvedType(kind=ResolvedTypeKind.LIST, item=_resolve_list_item(blueprint, local_domain=local_domain))
        case ConceptStructureBlueprintFieldType.DICT:
            return ResolvedType(
                kind=ResolvedTypeKind.DICT,
                key=ResolvedType(kind=ResolvedTypeKind.TEXT),
                value=_resolve_scalar_type_name(blueprint.value_type, local_domain=local_domain, context="dict value"),
            )


def _resolve_concept(concept_ref: str | None, *, local_domain: str | None) -> ResolvedType:
    if not concept_ref:
        return ResolvedType(kind=ResolvedTypeKind.ANY, imprecise=True, imprecision_reason="concept field without concept_ref")
    if NativeConceptCode.is_native_concept_ref_or_code(concept_ref_or_code=concept_ref):
        return ResolvedType(kind=ResolvedTypeKind.CONCEPT, concept_ref=concept_ref, is_native=True)
    # A bare concept ref (no domain) is local to the current bundle's domain — promote it so the
    # resolved ref is unambiguous for every downstream emitter.
    parsed_ref = QualifiedRef.parse_stripping_cross_package(concept_ref)
    if not parsed_ref.domain_path and local_domain:
        concept_ref = f"{local_domain}.{concept_ref}"
    return ResolvedType(kind=ResolvedTypeKind.CONCEPT, concept_ref=concept_ref, is_native=False)


def _resolve_list_item(blueprint: ConceptStructureBlueprint, *, local_domain: str | None) -> ResolvedType:
    if blueprint.item_type == "concept" and blueprint.item_concept_ref:
        return _resolve_concept(blueprint.item_concept_ref, local_domain=local_domain)
    return _resolve_scalar_type_name(blueprint.item_type, local_domain=local_domain, context="list item")


def _resolve_scalar_type_name(type_name: str | None, *, local_domain: str | None, context: str) -> ResolvedType:
    """Resolve a nested type named by a string (a list `item_type` / dict `value_type`).

    These positions carry a `ConceptStructureBlueprintFieldType` value as a string, never a concept
    ref (concept nesting uses the dedicated `concept` / `item_concept_ref` path). An unset or
    unrecognized name is genuine source imprecision, surfaced as ANY rather than guessed.
    """
    if type_name is None:
        return ResolvedType(kind=ResolvedTypeKind.ANY, imprecise=True, imprecision_reason=f"{context} type unspecified")
    try:
        field_type = ConceptStructureBlueprintFieldType(type_name)
    except ValueError:
        return ResolvedType(
            kind=ResolvedTypeKind.ANY, imprecise=True, imprecision_reason=f"{context} type '{type_name}' is not a recognized field type"
        )

    match field_type:
        case (
            ConceptStructureBlueprintFieldType.TEXT
            | ConceptStructureBlueprintFieldType.NUMBER
            | ConceptStructureBlueprintFieldType.INTEGER
            | ConceptStructureBlueprintFieldType.BOOLEAN
            | ConceptStructureBlueprintFieldType.DATE
            | ConceptStructureBlueprintFieldType.DATETIME
        ):
            return _resolve_type(ConceptStructureBlueprint(description="", type=field_type), local_domain=local_domain)
        case ConceptStructureBlueprintFieldType.LIST:
            # Nested list without its own item type: the inner item is unspecified.
            return ResolvedType(
                kind=ResolvedTypeKind.LIST,
                item=ResolvedType(kind=ResolvedTypeKind.ANY, imprecise=True, imprecision_reason=f"nested {context} list item type unspecified"),
            )
        case ConceptStructureBlueprintFieldType.DICT:
            return ResolvedType(
                kind=ResolvedTypeKind.DICT,
                key=ResolvedType(kind=ResolvedTypeKind.TEXT),
                value=ResolvedType(kind=ResolvedTypeKind.ANY, imprecise=True, imprecision_reason=f"nested {context} dict value type unspecified"),
            )
        case ConceptStructureBlueprintFieldType.CONCEPT:
            # `concept` in a scalar-type-name position carries no ref (a concept nesting would use the
            # dedicated concept path), so its shape is unspecified.
            return ResolvedType(kind=ResolvedTypeKind.ANY, imprecise=True, imprecision_reason=f"{context} concept type carries no concept_ref")
