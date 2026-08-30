"""Materialize native concepts into explicit concept-object form for the normalized crate.

Native concepts (`native.Text`, `native.Image`, ...) are the standard's built-in vocabulary. To
make a crate self-contained (a consumer needs no hardcoded native table), every referenced native
is materialized into a `ConceptBlueprint`. Materialization is a **lookup, not a computation**: the
standard pins every native's normative blueprint form per MTHDS version
(`mthds/docs/spec/native-concepts.md`), and `pipelex/core/concepts/native/pinned_blueprints.py` is
the runtime copy of that pinned set. Deriving the definitions from the runtime content classes by
reflection would make this implementation's quirks the de-facto standard and break cross-
implementation fingerprint byte-agreement — so the reflection below is retained **only as the
consistency probe**: the unit test compares each runtime content class's reflected shape against
its pinned blueprint, proving the two can never drift silently.

Reflection is faithful-or-absent: a native's structure is reflected only when *every* field of its
content class maps unambiguously to a blueprint field — primitive, dict, list, a reference to
another native, or a nested non-native model (whose wire form is a JSON object, so it maps honestly
to a `dict` blueprint with unspecified value types — declared imprecision). A field whose
annotation has no honest blueprint form at all (e.g. a non-Optional union) makes the whole
reflected structure absent.
"""

from typing import Any, cast, get_origin

from pydantic import BaseModel

from pipelex.core.concepts.annotation_shapes import (
    is_number_union,
    is_union,
    list_item_annotation,
    native_code_for_content_class,
    scalar_field_type,
    strip_optional,
)
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint, ConceptStructureBlueprintType
from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint, ConceptStructureBlueprintFieldType
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.concepts.native.pinned_blueprints import make_pinned_native_blueprint


class _UnmappableAnnotationError(Exception):
    """Internal signal that a native field's annotation has no clean blueprint representation."""


def materialize_native_concept(native_code: NativeConceptCode) -> ConceptBlueprint:
    """Return the pinned normative `ConceptBlueprint` for a native concept (a lookup, never reflection)."""
    return make_pinned_native_blueprint(native_code)


def collect_native_refs_from_structure(structure: dict[str, ConceptStructureBlueprint]) -> set[str]:
    """Return the `native.<Code>` refs a materialized native structure itself references (for transitive expansion)."""
    refs: set[str] = set()
    for field_blueprint in structure.values():
        for ref in (field_blueprint.concept_ref, field_blueprint.item_concept_ref):
            if ref and NativeConceptCode.is_native_concept_ref_or_code(concept_ref_or_code=ref):
                refs.add(NativeConceptCode.get_validated_native_concept_ref(concept_ref_or_code=ref))
    return refs


def reflect_native_structure(native_code: NativeConceptCode) -> dict[str, ConceptStructureBlueprintType] | None:
    """Reflect a native's runtime content class into blueprint form — the consistency probe, not the authority."""
    structure_class = native_code.structure_class
    if structure_class is None:
        return None
    return _reflect_structure_class(structure_class=cast("type[BaseModel]", structure_class))


def _reflect_structure_class(*, structure_class: type[BaseModel]) -> dict[str, ConceptStructureBlueprintType] | None:
    """Reflect a content class into blueprint form, faithful-or-absent.

    Every field must map unambiguously to a blueprint field, or the whole reflected structure is
    absent (`None`) — never a guessed shape, and never a partial one. That severity is what makes
    this a probe worth trusting: the pinned blueprint it is compared against is the normative form,
    so a structure reflected from a class that drifted must not look plausible. The input-form
    deriver reflects a class-backed concept for a different purpose and answers differently — see
    `InputFormDeriver._reflected_class_fields`.
    """
    model_fields = structure_class.model_fields
    if not model_fields:
        return None
    try:
        structure: dict[str, ConceptStructureBlueprintType] = {
            field_name: _annotation_to_blueprint(field_info.annotation, description=field_info.description or field_name)
            for field_name, field_info in model_fields.items()
        }
    except _UnmappableAnnotationError:
        return None
    return structure


def _annotation_to_blueprint(annotation: Any, *, description: str) -> ConceptStructureBlueprint:
    inner, required = strip_optional(annotation=annotation)

    if is_number_union(annotation=inner):
        return ConceptStructureBlueprint(description=description, type=ConceptStructureBlueprintFieldType.NUMBER, required=required)
    if is_union(annotation=inner):
        # A union that is not simply Optional[X] nor a number union has no single blueprint shape.
        raise _UnmappableAnnotationError

    origin = get_origin(inner)
    if origin is dict:
        return ConceptStructureBlueprint(
            description=description, type=ConceptStructureBlueprintFieldType.DICT, key_type="text", value_type="Any", required=required
        )
    if origin is list:
        return _list_blueprint(inner, description=description, required=required)

    scalar_type = scalar_field_type(annotation=inner)
    if scalar_type is not None:
        return ConceptStructureBlueprint(description=description, type=scalar_type, required=required)

    native_code = native_code_for_content_class(annotation=inner)
    if native_code is not None:
        return ConceptStructureBlueprint(
            description=description, type=ConceptStructureBlueprintFieldType.CONCEPT, concept_ref=native_code.concept_ref, required=required
        )

    if _is_nested_model(inner):
        # A nested non-native model serializes as a JSON object; its honest blueprint form is a dict
        # with unspecified value types — declared imprecision, not a guess. (No pinned native uses
        # this today — a hit here means a runtime class drifted from its pinned blueprint.)
        return ConceptStructureBlueprint(
            description=description, type=ConceptStructureBlueprintFieldType.DICT, key_type="text", value_type="Any", required=required
        )

    raise _UnmappableAnnotationError


def _list_blueprint(list_annotation: Any, *, description: str, required: bool) -> ConceptStructureBlueprint:
    item_inner = list_item_annotation(annotation=list_annotation)
    if item_inner is None:
        raise _UnmappableAnnotationError

    native_code = native_code_for_content_class(annotation=item_inner)
    if native_code is not None:
        return ConceptStructureBlueprint(
            description=description,
            type=ConceptStructureBlueprintFieldType.LIST,
            item_type="concept",
            item_concept_ref=native_code.concept_ref,
            required=required,
        )
    scalar_type = scalar_field_type(annotation=item_inner)
    if scalar_type is not None:
        return ConceptStructureBlueprint(
            description=description, type=ConceptStructureBlueprintFieldType.LIST, item_type=scalar_type, required=required
        )
    raise _UnmappableAnnotationError


def _is_nested_model(annotation: Any) -> bool:
    """A pydantic model that is not itself a native content class — an object on the wire."""
    return isinstance(annotation, type) and issubclass(annotation, BaseModel)
