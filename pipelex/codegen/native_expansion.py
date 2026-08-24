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

import datetime
from types import UnionType
from typing import Any, Union, cast, get_args, get_origin

from pydantic import BaseModel

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint, ConceptStructureBlueprintType
from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint, ConceptStructureBlueprintFieldType
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.concepts.native.pinned_blueprints import make_pinned_native_blueprint
from pipelex.core.stuffs.stuff_content import StuffContent

_NATIVE_CLASS_NAME_TO_CODE: dict[str, NativeConceptCode] = {native_code.structure_class_name: native_code for native_code in NativeConceptCode}


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
    return reflect_structure_class(structure_class=cast("type[BaseModel]", structure_class))


def reflect_structure_class(*, structure_class: type[BaseModel]) -> dict[str, ConceptStructureBlueprintType] | None:
    """Reflect a registered structure class into blueprint form, faithful-or-absent.

    Same rules as native reflection: every field must map unambiguously to a blueprint field, or
    the whole reflected structure is absent (`None`) — never a guessed shape. The input-form
    deriver uses this for class-backed concepts (`structure = "ClassName"`), where the class is
    the only statement of the payload's fields.
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
    inner, required = _strip_optional(annotation)

    if _is_number_union(inner):
        return ConceptStructureBlueprint(description=description, type=ConceptStructureBlueprintFieldType.NUMBER, required=required)
    if get_origin(inner) in {Union, UnionType}:
        # A union that is not simply Optional[X] nor a number union has no single blueprint shape.
        raise _UnmappableAnnotationError

    origin = get_origin(inner)
    if origin is dict:
        return ConceptStructureBlueprint(
            description=description, type=ConceptStructureBlueprintFieldType.DICT, key_type="text", value_type="Any", required=required
        )
    if origin is list:
        return _list_blueprint(inner, description=description, required=required)

    scalar_type = _scalar_field_type(inner)
    if scalar_type is not None:
        return ConceptStructureBlueprint(description=description, type=scalar_type, required=required)

    native_code = _native_code_for_content_class(inner)
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
    args = get_args(list_annotation)
    if not args:
        raise _UnmappableAnnotationError
    item_inner, _ = _strip_optional(args[0])

    native_code = _native_code_for_content_class(item_inner)
    if native_code is not None:
        return ConceptStructureBlueprint(
            description=description,
            type=ConceptStructureBlueprintFieldType.LIST,
            item_type="concept",
            item_concept_ref=native_code.concept_ref,
            required=required,
        )
    scalar_type = _scalar_field_type(item_inner)
    if scalar_type is not None:
        return ConceptStructureBlueprint(
            description=description, type=ConceptStructureBlueprintFieldType.LIST, item_type=scalar_type, required=required
        )
    raise _UnmappableAnnotationError


def _strip_optional(annotation: Any) -> tuple[Any, bool]:
    """Return (inner, required): peel a single `X | None` into (X, False); otherwise (annotation, True)."""
    if get_origin(annotation) in {Union, UnionType}:
        args = get_args(annotation)
        non_none = [arg for arg in args if arg is not type(None)]
        if len(non_none) == 1 and len(non_none) != len(args):
            return non_none[0], False
    return annotation, True


def _is_number_union(annotation: Any) -> bool:
    if get_origin(annotation) not in {Union, UnionType}:
        return False
    return set(get_args(annotation)) == {int, float}


def _scalar_field_type(annotation: Any) -> ConceptStructureBlueprintFieldType | None:
    # Order matters: bool is an int subclass, datetime is a date subclass — check the narrower first.
    if annotation is bool:
        return ConceptStructureBlueprintFieldType.BOOLEAN
    if annotation is int:
        return ConceptStructureBlueprintFieldType.INTEGER
    if annotation is float:
        return ConceptStructureBlueprintFieldType.NUMBER
    if annotation is str:
        return ConceptStructureBlueprintFieldType.TEXT
    if annotation is datetime.datetime:
        return ConceptStructureBlueprintFieldType.DATETIME
    if annotation is datetime.date:
        return ConceptStructureBlueprintFieldType.DATE
    if annotation is datetime.time:
        return ConceptStructureBlueprintFieldType.TIME
    return None


def _native_code_for_content_class(annotation: Any) -> NativeConceptCode | None:
    if not isinstance(annotation, type) or not issubclass(annotation, StuffContent):
        return None
    return _NATIVE_CLASS_NAME_TO_CODE.get(annotation.__name__)


def _is_nested_model(annotation: Any) -> bool:
    """A pydantic model that is not itself a native content class — an object on the wire."""
    return isinstance(annotation, type) and issubclass(annotation, BaseModel)
