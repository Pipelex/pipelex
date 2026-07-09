"""Materialize native concepts into explicit concept-object form for the normalized crate.

Native concepts (`native.Text`, `native.Image`, ...) are the standard's built-in vocabulary. In the
runtime they are hand-written pydantic content classes, not authored blueprints — so to make a crate
self-contained (a consumer needs no hardcoded native table), every referenced native is materialized
here into a `ConceptBlueprint`: its canonical description plus, where the content class's shape maps
cleanly onto the authoring structure language, its structure.

Materialization is faithful-or-absent: a native's structure is emitted only when *every* field of its
content class maps unambiguously to a blueprint field (primitive, dict, list, or a reference to
another native). A field whose annotation has no clean blueprint form (e.g. `ImageSize`,
`datetime.time`) makes the whole native structureless — the sufficiency contract surfaces that as
declared imprecision rather than a guessed shape. The `mthds_version` the crate is stamped with pins
which version these materialized definitions correspond to.
"""

import datetime
from types import UnionType
from typing import Any, Union, cast, get_args, get_origin

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint, ConceptStructureBlueprintType
from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint, ConceptStructureBlueprintFieldType
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.stuffs.stuff_content import StuffContent

_NATIVE_CLASS_NAME_TO_CODE: dict[str, NativeConceptCode] = {native_code.structure_class_name: native_code for native_code in NativeConceptCode}


class _UnmappableAnnotationError(Exception):
    """Internal signal that a native field's annotation has no clean blueprint representation."""


def materialize_native_concept(native_code: NativeConceptCode) -> ConceptBlueprint:
    """Build the explicit `ConceptBlueprint` for a native concept (description + structure-if-clean)."""
    # Local import: the concept factory pulls in the class registry lazily; keeping the import here
    # avoids an import cycle when this module is loaded during codegen bootstrapping.
    from pipelex.core.concepts.concept_factory import ConceptFactory  # noqa: PLC0415

    description = ConceptFactory.make_native_concept(native_concept_code=native_code).description
    return ConceptBlueprint(source=None, description=description, structure=_native_structure(native_code))


def collect_native_refs_from_structure(structure: dict[str, ConceptStructureBlueprint]) -> set[str]:
    """Return the `native.<Code>` refs a materialized native structure itself references (for transitive expansion)."""
    refs: set[str] = set()
    for field_blueprint in structure.values():
        for ref in (field_blueprint.concept_ref, field_blueprint.item_concept_ref):
            if ref and NativeConceptCode.is_native_concept_ref_or_code(concept_ref_or_code=ref):
                refs.add(NativeConceptCode.get_validated_native_concept_ref(concept_ref_or_code=ref))
    return refs


def _native_structure(native_code: NativeConceptCode) -> dict[str, ConceptStructureBlueprintType] | None:
    structure_class = native_code.structure_class
    if structure_class is None:
        return None
    model_fields = cast("type[StuffContent]", structure_class).model_fields
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
            description=description, type=ConceptStructureBlueprintFieldType.DICT, key_type="str", value_type="Any", required=required
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
    return None


def _native_code_for_content_class(annotation: Any) -> NativeConceptCode | None:
    if not isinstance(annotation, type) or not issubclass(annotation, StuffContent):
        return None
    return _NATIVE_CLASS_NAME_TO_CODE.get(annotation.__name__)
