"""The two ways the binding walk reads a concept: from a loaded library, or from a bundle's own blueprints.

Both answer the one question the walk asks, `resolve_walkable_concept`, with the same `WalkableConcept`:

- `LibraryConceptWalkResolver` reads the concepts of a loaded library, which is what a sequence validates and
  runs against. A concept declaring a structure is walked through the fields its blueprint declares, kept on
  the runtime concept as `declared_structure`; a refinement through the structure it inherits; a native
  through its pinned definition; a concept declared with a description alone not at all, however it was
  written. A concept whose structure exists only as a Python class is walked through the class's fields, a
  field typed by a content class mapping to the concept registered for that class when exactly one concept
  is, and to nothing otherwise, which the walk refuses. A dependency package's concepts are held only under
  their aliased keys (`alias->domain.Code`), so the walk reads a dependency's concept, and every concept its
  fields and its `refines` name, under that package's alias: a host concept of the same spelling never
  supplies its structure.
- `BlueprintConceptWalkResolver` reads the concept blueprints of one bundle, before any library is loaded,
  which is what the fix planner needs to decide whether deleting a redundant dotted input is safe. What the
  bundle does not declare, it does not know, and the walk refuses it. The planner asks whether a template's
  read holds, so it walks a single-field native through its pinned field, where a binding stops.
"""

import datetime
import types
from collections.abc import Mapping
from typing import Any, Literal, Union, get_args, get_origin

from pydantic.fields import FieldInfo
from typing_extensions import override

from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint, ConceptStructureBlueprintType
from pipelex.core.concepts.concept_provider_abstract import ConceptProviderAbstract
from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint, ConceptStructureBlueprintFieldType
from pipelex.core.concepts.exceptions import ConceptStructureClassNotFoundError
from pipelex.core.concepts.helpers import normalize_structure_blueprint
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.concepts.native.pinned_blueprints import make_pinned_native_blueprint
from pipelex.core.domains.domain import SpecialDomain
from pipelex.core.qualified_ref import QualifiedRef
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.libraries.concept.concept_library_abstract import ConceptLibraryAbstract
from pipelex.libraries.concept.exceptions import ConceptLibraryError
from pipelex.pipe_controllers.binding.binding_derivation import (
    BindingValueKind,
    ConceptShape,
    ConceptWalkResolver,
    WalkableConcept,
    WalkableField,
)

_SINGLE_FIELD_NATIVE_REASON = "holds its value in a single field"
_DESCRIBED_ONLY_REASON = "is declared with neither a structure nor refines"


def qualify_concept_ref(*, concept_ref: str, domain_code: str, package_alias: str | None = None) -> str:
    """A concept ref as a structure field or a `refines` writes it, made domain-qualified in the declaring domain.

    When the declaring concept belongs to a dependency package, `package_alias` is that package's alias, and a ref to
    one of its concepts is keyed under it (`alias->domain.Code`), the only key the library holds a dependency's concept
    under. A native ref, and a ref that already names its package, are left as they are.
    """
    if QualifiedRef.has_cross_package_prefix(concept_ref):
        return concept_ref
    if NativeConceptCode.is_native_concept_ref_or_code(concept_ref_or_code=concept_ref):
        return f"{SpecialDomain.NATIVE}.{concept_ref.rsplit('.', maxsplit=1)[-1]}"
    domain_qualified_ref = concept_ref if "." in concept_ref else f"{domain_code}.{concept_ref}"
    if package_alias is None:
        return domain_qualified_ref
    return f"{package_alias}->{domain_qualified_ref}"


def library_concept_key(*, concept_library: ConceptProviderAbstract, concept: Concept) -> str:
    """The key under which a library holds this very concept: its ref for a host or native concept, `alias->domain.Code` for a dependency's.

    A dependency package's concept reports the plain `domain.Code` its package declares, while the library holds it only
    under its aliased key, beside any host concept spelled the same. The walk must start from that key to read the
    package's own definitions. The concept is matched by identity, since pipes are built with the very concept objects
    the library holds, then by equality; failing both, a spelling held under one key alone is that key, and the
    concept's own ref is the answer otherwise.
    """
    candidate_keys = concept_library.list_concept_keys_for_ref(concept_ref=concept.concept_ref)
    candidate_concepts = {candidate_key: concept_library.get_required_concept(concept_ref=candidate_key) for candidate_key in candidate_keys}
    for candidate_key, candidate_concept in candidate_concepts.items():
        if candidate_concept is concept:
            return candidate_key
    equal_keys = [candidate_key for candidate_key, candidate_concept in candidate_concepts.items() if candidate_concept == concept]
    if len(equal_keys) == 1:
        return equal_keys[0]
    if len(candidate_keys) == 1:
        return candidate_keys[0]
    return concept.concept_ref


def _package_alias_of(*, concept_key: str) -> str | None:
    """The alias of the dependency package a library key holds a concept under, `None` for a host or native concept."""
    if not QualifiedRef.has_cross_package_prefix(concept_key):
        return None
    package_alias, _ = QualifiedRef.split_cross_package_ref(concept_key)
    return package_alias


def walkable_native_concept(*, native_code: NativeConceptCode, walks_single_field: bool = False) -> WalkableConcept:
    """A native concept as the walk sees it, read off its pinned definition, never off its content class.

    A native whose pinned definition is a single field holding the value itself (`Text`, `Number`, `Time`, `JSON`) is a
    leaf to a binding, which refuses to walk into it. A template reads that field all the same (`$note.text`), so a check
    asking whether a template's read holds passes `walks_single_field` to walk it through its pinned field.
    """
    pinned_blueprint = make_pinned_native_blueprint(native_code)
    if not isinstance(pinned_blueprint.structure, dict):
        return WalkableConcept(concept_ref=native_code.concept_ref, shape=ConceptShape.NO_STRUCTURE, shape_reason="is structureless by definition")
    if len(pinned_blueprint.structure) == 1 and not walks_single_field:
        return WalkableConcept(concept_ref=native_code.concept_ref, shape=ConceptShape.VALUE, shape_reason=_SINGLE_FIELD_NATIVE_REASON)
    return WalkableConcept(
        concept_ref=native_code.concept_ref,
        shape=ConceptShape.STRUCTURE,
        fields=walkable_fields_from_structure(structure=pinned_blueprint.structure, domain_code=SpecialDomain.NATIVE),
    )


def _scalar_value_kind(*, field_type: ConceptStructureBlueprintFieldType) -> BindingValueKind | None:
    """The value kind of a plain field type, or `None` for the types that are not plain values (`concept`, `list`)."""
    match field_type:
        case ConceptStructureBlueprintFieldType.TEXT:
            return BindingValueKind.TEXT
        case ConceptStructureBlueprintFieldType.NUMBER | ConceptStructureBlueprintFieldType.INTEGER:
            return BindingValueKind.NUMBER
        case ConceptStructureBlueprintFieldType.BOOLEAN:
            return BindingValueKind.YES_NO
        case ConceptStructureBlueprintFieldType.DATE:
            return BindingValueKind.DATE
        case ConceptStructureBlueprintFieldType.DATETIME:
            return BindingValueKind.DATETIME
        case ConceptStructureBlueprintFieldType.TIME:
            return BindingValueKind.TIME
        case ConceptStructureBlueprintFieldType.DICT:
            return BindingValueKind.JSON
        case ConceptStructureBlueprintFieldType.CONCEPT | ConceptStructureBlueprintFieldType.LIST:
            return None


def _walkable_field_from_blueprint(
    *, name: str, field_blueprint: ConceptStructureBlueprint, domain_code: str, package_alias: str | None
) -> WalkableField:
    # The standard's rule: a declared field may hold nothing when it is not `required` and has no `default_value`. A
    # `required` field is generated as a value that cannot be `None`.
    may_hold_nothing = not field_blueprint.required and field_blueprint.default_value is None
    if field_blueprint.type is None:
        # A field declared by its `choices` alone holds one of them, a text.
        return WalkableField(name=name, value_kind=BindingValueKind.TEXT, may_hold_nothing=may_hold_nothing)
    match field_blueprint.type:
        case ConceptStructureBlueprintFieldType.CONCEPT:
            concept_ref = (
                qualify_concept_ref(concept_ref=field_blueprint.concept_ref, domain_code=domain_code, package_alias=package_alias)
                if field_blueprint.concept_ref
                else None
            )
            return WalkableField(name=name, value_kind=BindingValueKind.CONCEPT, concept_ref=concept_ref, may_hold_nothing=may_hold_nothing)
        case ConceptStructureBlueprintFieldType.LIST:
            return _walkable_list_field(
                name=name, field_blueprint=field_blueprint, domain_code=domain_code, package_alias=package_alias, may_hold_nothing=may_hold_nothing
            )
        case (
            ConceptStructureBlueprintFieldType.TEXT
            | ConceptStructureBlueprintFieldType.NUMBER
            | ConceptStructureBlueprintFieldType.INTEGER
            | ConceptStructureBlueprintFieldType.BOOLEAN
            | ConceptStructureBlueprintFieldType.DATE
            | ConceptStructureBlueprintFieldType.DATETIME
            | ConceptStructureBlueprintFieldType.TIME
            | ConceptStructureBlueprintFieldType.DICT
        ):
            value_kind = _scalar_value_kind(field_type=field_blueprint.type) or BindingValueKind.UNDERIVABLE
            return WalkableField(name=name, value_kind=value_kind, may_hold_nothing=may_hold_nothing)


def _walkable_list_field(
    *, name: str, field_blueprint: ConceptStructureBlueprint, domain_code: str, package_alias: str | None, may_hold_nothing: bool
) -> WalkableField:
    item_type = field_blueprint.item_type
    if item_type is None:
        return WalkableField(
            name=name,
            value_kind=BindingValueKind.UNDERIVABLE,
            is_list=True,
            may_hold_nothing=may_hold_nothing,
            underivable_reason="the list declares no item_type",
        )
    if item_type == ConceptStructureBlueprintFieldType.CONCEPT:
        item_concept_ref = (
            qualify_concept_ref(concept_ref=field_blueprint.item_concept_ref, domain_code=domain_code, package_alias=package_alias)
            if field_blueprint.item_concept_ref
            else None
        )
        return WalkableField(
            name=name, value_kind=BindingValueKind.CONCEPT, concept_ref=item_concept_ref, is_list=True, may_hold_nothing=may_hold_nothing
        )
    item_field_type: ConceptStructureBlueprintFieldType | None
    try:
        item_field_type = ConceptStructureBlueprintFieldType(item_type)
    except ValueError:
        item_field_type = None
    item_value_kind = _scalar_value_kind(field_type=item_field_type) if item_field_type is not None else None
    if item_value_kind is None:
        return WalkableField(
            name=name,
            value_kind=BindingValueKind.UNDERIVABLE,
            is_list=True,
            may_hold_nothing=may_hold_nothing,
            underivable_reason=f"the list's item_type '{item_type}' derives no concept",
        )
    return WalkableField(name=name, value_kind=item_value_kind, is_list=True, may_hold_nothing=may_hold_nothing)


def walkable_fields_from_structure(
    *, structure: Mapping[str, ConceptStructureBlueprintType], domain_code: str, package_alias: str | None = None
) -> tuple[WalkableField, ...]:
    """The fields of a declared structure, in declaration order, their concept refs qualified in `domain_code`.

    A dependency package's structure passes the package's alias, under which its own concept refs are keyed.
    """
    normalized_structure = normalize_structure_blueprint(dict(structure))
    return tuple(
        _walkable_field_from_blueprint(name=field_name, field_blueprint=field_blueprint, domain_code=domain_code, package_alias=package_alias)
        for field_name, field_blueprint in normalized_structure.items()
    )


def _inherited_walkable_concept(*, concept_ref: str, refined: WalkableConcept) -> WalkableConcept:
    """A refining concept as the walk sees it: the structure it inherits, or the leaf or the void it refines."""
    match refined.shape:
        case ConceptShape.STRUCTURE:
            return WalkableConcept(concept_ref=concept_ref, shape=ConceptShape.STRUCTURE, fields=refined.fields)
        case ConceptShape.VALUE:
            return WalkableConcept(
                concept_ref=concept_ref,
                shape=ConceptShape.VALUE,
                shape_reason=f"refines '{refined.concept_ref}', which {refined.shape_reason}",
            )
        case ConceptShape.NO_STRUCTURE:
            return WalkableConcept(
                concept_ref=concept_ref,
                shape=ConceptShape.NO_STRUCTURE,
                shape_reason=f"refines '{refined.concept_ref}', which {refined.shape_reason}",
            )


class LibraryConceptWalkResolver(ConceptWalkResolver):
    """The walk's view of the concepts of a loaded library.

    A concept ref the walk hands it is a key of the library: a host or native concept's ref, or a dependency's
    `alias->domain.Code`. The concepts a dependency's concept names, through its fields or its `refines`, are keyed under
    the same alias, so a walk that starts in a package stays in it.
    """

    def __init__(self, *, concept_library: ConceptLibraryAbstract):
        self._concept_library = concept_library

    @override
    def resolve_walkable_concept(self, *, concept_ref: str) -> WalkableConcept:
        return self._resolve(concept_ref=concept_ref, visited=frozenset())

    def _resolve(self, *, concept_ref: str, visited: frozenset[str]) -> WalkableConcept:
        if concept_ref in visited:
            return WalkableConcept(concept_ref=concept_ref, shape=ConceptShape.NO_STRUCTURE, shape_reason="refines itself through a cycle")
        try:
            concept = self._concept_library.get_required_concept(concept_ref=concept_ref)
        except ConceptLibraryError:
            return WalkableConcept(concept_ref=concept_ref, shape=ConceptShape.NO_STRUCTURE, shape_reason="is not a concept of the library")
        if SpecialDomain.is_native(domain_code=concept.domain_code) and concept.code in NativeConceptCode.values_list():
            # Every native, a native refining another included (Markdown refines Text), is read off its own pinned definition.
            return walkable_native_concept(native_code=NativeConceptCode(concept.code))
        if concept.is_described_only:
            # Whether written `Note = "A note"` or as a table holding a description alone, which the runtime makes refine
            # `native.Text`: the standard gives such a concept no structure, so a path never enters it.
            return WalkableConcept(concept_ref=concept_ref, shape=ConceptShape.NO_STRUCTURE, shape_reason=_DESCRIBED_ONLY_REASON)
        package_alias = _package_alias_of(concept_key=concept_ref)
        if concept.declared_structure is not None:
            return WalkableConcept(
                concept_ref=concept_ref,
                shape=ConceptShape.STRUCTURE,
                fields=walkable_fields_from_structure(
                    structure=concept.declared_structure, domain_code=concept.domain_code, package_alias=package_alias
                ),
            )
        if concept.refines is not None:
            refined_ref = qualify_concept_ref(concept_ref=concept.refines, domain_code=concept.domain_code, package_alias=package_alias)
            refined = self._resolve(concept_ref=refined_ref, visited=visited | {concept_ref})
            return _inherited_walkable_concept(concept_ref=concept_ref, refined=refined)
        return self._walkable_from_structure_class(concept=concept, concept_key=concept_ref, package_alias=package_alias)

    def _walkable_from_structure_class(self, *, concept: Concept, concept_key: str, package_alias: str | None) -> WalkableConcept:
        """A concept whose structure exists only as a Python class, walked through the class's own fields."""
        try:
            structure_class = self._concept_library.get_structure_class(concept=concept)
        except ConceptStructureClassNotFoundError:
            return WalkableConcept(
                concept_ref=concept_key, shape=ConceptShape.NO_STRUCTURE, shape_reason="has a structure class that cannot be resolved"
            )
        walkable_fields = tuple(
            self._walkable_field_from_class_field(name=field_name, field_info=field_info, package_alias=package_alias)
            for field_name, field_info in structure_class.model_fields.items()
            if not field_name.startswith("_")
        )
        return WalkableConcept(concept_ref=concept_key, shape=ConceptShape.STRUCTURE, fields=walkable_fields)

    def _walkable_field_from_class_field(self, *, name: str, field_info: FieldInfo, package_alias: str | None) -> WalkableField:
        # A class states what a field may hold through its annotation: one that admits `None` may hold nothing, whether it
        # is required or has a default, and so does one left unrequired with no default.
        is_nullable = _admits_none(annotation=field_info.annotation)
        may_hold_nothing = is_nullable or (not field_info.is_required() and field_info.default is None and field_info.default_factory is None)
        annotation, _ = _strip_optional(annotation=field_info.annotation)
        is_list = get_origin(annotation) is list
        if is_list:
            list_args = get_args(annotation)
            if not list_args:
                return WalkableField(
                    name=name,
                    value_kind=BindingValueKind.UNDERIVABLE,
                    is_list=True,
                    may_hold_nothing=may_hold_nothing,
                    underivable_reason="the list declares no item type",
                )
            annotation, _ = _strip_optional(annotation=list_args[0])
        value_kind = _python_value_kind(annotation=annotation)
        if value_kind is not None:
            return WalkableField(name=name, value_kind=value_kind, is_list=is_list, may_hold_nothing=may_hold_nothing)
        if isinstance(annotation, type) and issubclass(annotation, StuffContent):
            concept_keys = self._concept_keys_for_class(class_name=annotation.__name__, package_alias=package_alias)
            if len(concept_keys) == 1:
                return WalkableField(
                    name=name, value_kind=BindingValueKind.CONCEPT, concept_ref=concept_keys[0], is_list=is_list, may_hold_nothing=may_hold_nothing
                )
            reason = (
                f"its class '{annotation.__name__}' is the structure of no concept"
                if not concept_keys
                else f"its class '{annotation.__name__}' is the structure of several concepts ({', '.join(concept_keys)})"
            )
            return WalkableField(
                name=name, value_kind=BindingValueKind.UNDERIVABLE, is_list=is_list, may_hold_nothing=may_hold_nothing, underivable_reason=reason
            )
        return WalkableField(
            name=name,
            value_kind=BindingValueKind.UNDERIVABLE,
            is_list=is_list,
            may_hold_nothing=may_hold_nothing,
            underivable_reason=f"its Python type '{annotation}' maps to no concept",
        )

    def _concept_keys_for_class(self, *, class_name: str, package_alias: str | None) -> list[str]:
        """The keys of the concepts whose structure is the class named `class_name`, those of the walking package first.

        When several concepts share the class, the ones the walking concept's package can name, natives included, are
        kept, so a dependency's class-backed concept maps to the package's own concept rather than to a host one.
        """
        concept_keys = sorted(
            {
                library_concept_key(concept_library=self._concept_library, concept=listed_concept)
                for listed_concept in self._concept_library.list_concepts()
                if listed_concept.structure_class_name == class_name
            }
        )
        if len(concept_keys) <= 1:
            return concept_keys
        return [concept_key for concept_key in concept_keys if _package_alias_of(concept_key=concept_key) == package_alias] or concept_keys


def _admits_none(*, annotation: Any) -> bool:
    """Whether a field annotation admits `None`: `None` itself, `Any`, or a union with a `None` arm."""
    if annotation is None or annotation is type(None) or annotation is Any:
        return True
    origin = get_origin(annotation)
    if origin is Union or origin is types.UnionType:
        return any(_admits_none(annotation=arm) for arm in get_args(annotation))
    return False


def _strip_optional(*, annotation: Any) -> tuple[Any, bool]:
    """An annotation without its `None` arm, and whether it had one."""
    origin = get_origin(annotation)
    if origin is Union or origin is types.UnionType:
        arms = [arm for arm in get_args(annotation) if arm is not type(None)]
        if len(arms) == 1:
            return arms[0], True
    return annotation, False


def _python_value_kind(*, annotation: Any) -> BindingValueKind | None:
    """The value kind of a plain Python type on a structure class, or `None` when it is not a plain value."""
    if get_origin(annotation) is Literal:
        return BindingValueKind.TEXT
    if get_origin(annotation) is dict or annotation is dict:
        return BindingValueKind.JSON
    if not isinstance(annotation, type):
        return None
    # `bool` before `int`, which it subclasses, and `datetime` before `date`, likewise.
    if issubclass(annotation, bool):
        return BindingValueKind.YES_NO
    if issubclass(annotation, (int, float)):
        return BindingValueKind.NUMBER
    if issubclass(annotation, str):
        return BindingValueKind.TEXT
    if issubclass(annotation, datetime.datetime):
        return BindingValueKind.DATETIME
    if issubclass(annotation, datetime.date):
        return BindingValueKind.DATE
    if issubclass(annotation, datetime.time):
        return BindingValueKind.TIME
    return None


class BlueprintConceptWalkResolver(ConceptWalkResolver):
    """The walk's view of one bundle's concept blueprints, keyed by domain-qualified ref, and of the natives.

    With `walks_single_field_natives`, a single-field native is walked through its pinned field, as a template reads it,
    rather than refused as a binding's leaf: the fix planner asks whether a template's read of a dotted path holds.
    """

    def __init__(self, *, concept_blueprints: Mapping[str, ConceptBlueprint | str], walks_single_field_natives: bool = False):
        self._concept_blueprints = concept_blueprints
        self._walks_single_field_natives = walks_single_field_natives

    @override
    def resolve_walkable_concept(self, *, concept_ref: str) -> WalkableConcept:
        return self._resolve(concept_ref=concept_ref, visited=frozenset())

    def _resolve(self, *, concept_ref: str, visited: frozenset[str]) -> WalkableConcept:
        if NativeConceptCode.is_native_concept_ref_or_code(concept_ref_or_code=concept_ref):
            return walkable_native_concept(
                native_code=NativeConceptCode(concept_ref.rsplit(".", maxsplit=1)[-1]),
                walks_single_field=self._walks_single_field_natives,
            )
        if concept_ref in visited:
            return WalkableConcept(concept_ref=concept_ref, shape=ConceptShape.NO_STRUCTURE, shape_reason="refines itself through a cycle")
        concept_blueprint = self._concept_blueprints.get(concept_ref)
        if concept_blueprint is None:
            return WalkableConcept(concept_ref=concept_ref, shape=ConceptShape.NO_STRUCTURE, shape_reason="is not declared in this bundle")
        if isinstance(concept_blueprint, str):
            return WalkableConcept(concept_ref=concept_ref, shape=ConceptShape.NO_STRUCTURE, shape_reason=_DESCRIBED_ONLY_REASON)
        domain_code = concept_ref.rsplit(".", maxsplit=1)[0]
        if isinstance(concept_blueprint.structure, dict):
            return WalkableConcept(
                concept_ref=concept_ref,
                shape=ConceptShape.STRUCTURE,
                fields=walkable_fields_from_structure(structure=concept_blueprint.structure, domain_code=domain_code),
            )
        if isinstance(concept_blueprint.structure, str):
            return WalkableConcept(
                concept_ref=concept_ref,
                shape=ConceptShape.NO_STRUCTURE,
                shape_reason="has a Python class for a structure, which a bundle does not show",
            )
        if concept_blueprint.refines is not None:
            refined_ref = qualify_concept_ref(concept_ref=concept_blueprint.refines, domain_code=domain_code)
            refined = self._resolve(concept_ref=refined_ref, visited=visited | {concept_ref})
            return _inherited_walkable_concept(concept_ref=concept_ref, refined=refined)
        return WalkableConcept(concept_ref=concept_ref, shape=ConceptShape.NO_STRUCTURE, shape_reason=_DESCRIBED_ONLY_REASON)
