"""The derivation walk of a binding step: the concept its `from` path reaches, read off declared structures alone.

A binding step `{ from = "invoice.total", result = "total_amount" }` stores the value at a path under a new
name, and the concept of that value is derived before any run, by walking the path through the structures
the concepts declare, one segment at a time:

| The segment names a field declared as | The walk continues into, or the result is |
|---|---|
| `type = "concept"`, `concept_ref = X` | `X`, whose structure the next segment walks |
| `type = "list"`, `item_type = "concept"`, `item_concept_ref = X` | `X`, crossing a list |
| `type = "text"`, or `choices` | `native.Text`, a leaf |
| `type = "number"` or `"integer"` | `native.Number`, a leaf |
| `type = "boolean"` | `native.YesNo`, a leaf |
| `type = "date"` or `"datetime"` | `native.Date`, a leaf |
| `type = "time"` | `native.Time`, a leaf |
| `type = "list"` with a scalar `item_type` | that scalar's native concept, a leaf, crossing a list |
| `type = "dict"` | `native.JSON`, a leaf |

The walk is pure: it reads concepts through a `ConceptWalkResolver`, which says, for a concept ref, what
the walk may see of it (`WalkableConcept`). The resolver over a loaded library and the one over a bundle's
own blueprints live in `binding_concept_resolvers`; this module never maps a Python class back to a concept.
"""

from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.pipes.variable_multiplicity import VariableMultiplicity, is_multiple_multiplicity
from pipelex.pipe_controllers.binding.exceptions import BindingPathUnresolvedError
from pipelex.tools.misc.string_utils import get_root_from_dotted_path


class BindingValueKind(StrEnum):
    """What a field holds, as the walk and the runtime see it: a concept's content, a plain value, or nothing derivable."""

    CONCEPT = "concept"
    TEXT = "text"
    NUMBER = "number"
    YES_NO = "yes_no"
    DATE = "date"
    DATETIME = "datetime"
    TIME = "time"
    JSON = "json"
    # A field holding `native.Anything`, whose generated class types it `Any`: any raw value, stored as the native its
    # type maps to, as an `Anything` input is shaped. A leaf like a plain value, since `Anything` has no structure.
    ANYTHING = "anything"
    # A list with no `item_type`, or a field whose concept cannot be derived: no concept exists for its value.
    UNDERIVABLE = "underivable"

    @property
    def leaf_native_concept_code(self) -> NativeConceptCode | None:
        """The native concept a plain value of this kind is stored as, or `None` for a concept's content and for the underivable."""
        match self:
            case BindingValueKind.TEXT:
                return NativeConceptCode.TEXT
            case BindingValueKind.NUMBER:
                return NativeConceptCode.NUMBER
            case BindingValueKind.YES_NO:
                return NativeConceptCode.YES_NO
            case BindingValueKind.DATE | BindingValueKind.DATETIME:
                return NativeConceptCode.DATE
            case BindingValueKind.TIME:
                return NativeConceptCode.TIME
            case BindingValueKind.JSON:
                return NativeConceptCode.JSON
            case BindingValueKind.ANYTHING:
                return NativeConceptCode.ANYTHING
            case BindingValueKind.CONCEPT | BindingValueKind.UNDERIVABLE:
                return None

    @property
    def leaf_description(self) -> str:
        """How a message names a field of this kind, which is a leaf unless it holds a concept."""
        match self:
            case BindingValueKind.TEXT:
                return "a text field"
            case BindingValueKind.NUMBER:
                return "a number field"
            case BindingValueKind.YES_NO:
                return "a boolean field"
            case BindingValueKind.DATE:
                return "a date field"
            case BindingValueKind.DATETIME:
                return "a datetime field"
            case BindingValueKind.TIME:
                return "a time field"
            case BindingValueKind.JSON:
                return "a dict field"
            case BindingValueKind.ANYTHING:
                return "a field holding any value"
            case BindingValueKind.CONCEPT:
                return "a concept field"
            case BindingValueKind.UNDERIVABLE:
                return "a field with no derivable concept"


class WalkableField(BaseModel):
    """One field of a walkable structure, as the walk reads it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    value_kind: BindingValueKind
    # The concept the field (or each item of the list) holds, domain-qualified, when `value_kind` is CONCEPT.
    concept_ref: str | None = None
    is_list: bool = False
    # Whether the field may hold nothing: it is neither `required` nor given a `default_value`.
    may_hold_nothing: bool = False
    # Why no concept can be derived for the field's value, when `value_kind` is UNDERIVABLE.
    underivable_reason: str | None = None


class ConceptShape(StrEnum):
    """What a concept offers a path walking into it."""

    # Declared fields, which the next segment names.
    STRUCTURE = "structure"
    # A native holding its value in a single field (`Text`, `Number`, `Time`, `JSON`, `Markdown`), or a
    # concept refining one: a leaf wherever the walk reaches it, which a path may end on but never enter.
    VALUE = "value"
    # No structure to walk: a structureless native (`Dynamic`, `Anything`, `Composite`), a concept declared
    # with neither `structure` nor `refines`, a concept refining one of those, or a concept nothing resolves.
    NO_STRUCTURE = "no_structure"


class WalkableConcept(BaseModel):
    """A concept as the walk sees it: its ref, its shape, and its fields when it has a structure."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    concept_ref: str
    shape: ConceptShape
    fields: tuple[WalkableField, ...] = ()
    # Why the concept offers nothing to walk, for a VALUE or NO_STRUCTURE shape, written to follow "which".
    shape_reason: str | None = None

    def get_field(self, *, name: str) -> WalkableField | None:
        for walkable_field in self.fields:
            if walkable_field.name == name:
                return walkable_field
        return None

    @property
    def field_names(self) -> list[str]:
        return [walkable_field.name for walkable_field in self.fields]


class ConceptWalkResolver(Protocol):
    """What the walk needs to know of a concept, given its domain-qualified ref."""

    def resolve_walkable_concept(self, *, concept_ref: str) -> WalkableConcept: ...


class BindingSegment(BaseModel):
    """One field segment of a derived path, as the runtime walks it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    # Whether the field holds a list, whose items the rest of the path is applied to.
    crosses_list: bool


class BindingRoot(BaseModel):
    """The concept and multiplicity of a binding's root, as the sequence knows them at the binding step."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    concept_ref: str
    multiplicity: VariableMultiplicity | None = None


class BindingDerivation(BaseModel):
    """What a binding step binds, derived before any run: the concept, the multiplicity and the static absence."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str
    concept_ref: str
    # `None` for a single value, `True` for a list. A bare name keeps its root's multiplicity unchanged.
    multiplicity: VariableMultiplicity | None
    # Static, single results only: the path walks a field that may hold nothing. A list result never is.
    may_find_nothing: bool
    # The dotted path up to the first field along the way that may hold nothing, for the taint message.
    first_optional_path: str | None = None
    # How the runtime stores the value it reaches: a concept's content is copied whole, a plain value wrapped.
    leaf_kind: BindingValueKind
    segments: tuple[BindingSegment, ...] = ()
    # The multiplicity of the root the path starts from, as the sequence knows it at the binding step.
    root_multiplicity: VariableMultiplicity | None = None

    @property
    def root_name(self) -> str:
        return get_root_from_dotted_path(self.path)

    @property
    def is_bare_name(self) -> bool:
        return not self.segments

    @property
    def is_plural(self) -> bool:
        return is_multiple_multiplicity(multiplicity=self.multiplicity)

    def provenance_path(self, *, item_segment: str) -> tuple[str, ...] | None:
        """Where, below its root, the value the binding binds comes from, `item_segment` standing for any item of a list crossed.

        A list sits at its own path and its items at that path followed by the item segment, so what the binding binds has
        such a path when it is the value at one path of its root, or the items of a list field reached across items:

        - a single value, or one list field of a single root, is at its fields' path: `invoice.lines` is `("lines",)`;
        - a bare name is its root's own value, a list included: `()`;
        - a list gathered across items whose last field is itself a list holds the items of that field, wherever they sit:
          the item segment follows a list root, and every field before the last that crosses a list, so `cases.transcripts`
          over a list root is `("[]", "transcripts")` and `case.folders.transcripts` is `("folders", "[]", "transcripts")`.

        A list gathered from a field that is not itself a list, `cases.attachment` over a list root, holds values that are
        items of no list at one path, so it has no such path: `None`.

        Args:
            item_segment: The segment the caller's paths use for any item of a list.

        Returns:
            The segments below the root, or `None` for a list gathered from a field that is not a list.
        """
        if self.is_bare_name:
            return ()
        *leading_segments, last_segment = self.segments
        if self.is_plural and not last_segment.crosses_list:
            return None
        provenance: list[str] = [item_segment] if is_multiple_multiplicity(multiplicity=self.root_multiplicity) else []
        for segment in leading_segments:
            provenance.append(segment.name)
            if segment.crosses_list:
                provenance.append(item_segment)
        provenance.append(last_segment.name)
        return tuple(provenance)


def _quoted(*, names: list[str]) -> str:
    return ", ".join(f"'{name}'" for name in names)


def _fields_phrase(*, walkable_concept: WalkableConcept) -> str:
    if not walkable_concept.fields:
        return "It has no fields."
    return f"Its fields are: {_quoted(names=walkable_concept.field_names)}."


def derive_binding(*, path: str, root: BindingRoot, resolver: ConceptWalkResolver) -> BindingDerivation:
    """Walk a binding step's `from` path through declared structures and derive what the step binds.

    Args:
        path: The binding step's `from`, already known to follow the path grammar.
        root: The root's concept and multiplicity, from the latest value stored under its name before the step.
        resolver: How the walk reads a concept.

    Returns:
        The derived concept, multiplicity and static absence, with the segments the runtime walks.

    Raises:
        BindingPathUnresolvedError: When the path cannot be walked, naming the segment that failed and the
            fields available there.
    """
    segment_names = path.split(".")[1:]
    if not segment_names:
        # A bare name binds a renamed copy of the whole value, with the root's concept and multiplicity unchanged.
        return BindingDerivation(
            path=path,
            concept_ref=root.concept_ref,
            multiplicity=root.multiplicity,
            may_find_nothing=False,
            leaf_kind=BindingValueKind.CONCEPT,
            root_multiplicity=root.multiplicity,
        )

    crosses_any_list = is_multiple_multiplicity(multiplicity=root.multiplicity)
    may_find_nothing = False
    first_optional_path: str | None = None
    segments: list[BindingSegment] = []
    reached_path = get_root_from_dotted_path(path)
    # What the next segment walks: a concept, or the plain field the previous segment ended on.
    current_concept: WalkableConcept | None = resolver.resolve_walkable_concept(concept_ref=root.concept_ref)
    current_leaf_field: WalkableField | None = None
    derived_concept_ref = root.concept_ref
    leaf_kind = BindingValueKind.CONCEPT

    for segment_index, segment_name in enumerate(segment_names):
        if current_leaf_field is not None:
            msg = (
                f"Cannot bind '{path}': '{reached_path}' is {current_leaf_field.value_kind.leaf_description}, a leaf holding a plain value "
                f"with no fields, so the segment '{segment_name}' cannot follow it. It has no fields."
            )
            raise BindingPathUnresolvedError(msg, path=path, failed_segment=segment_name, available_fields=[])
        if current_concept is None:
            msg = f"Cannot bind '{path}': nothing is known of '{reached_path}', so the segment '{segment_name}' cannot be walked."
            raise BindingPathUnresolvedError(msg, path=path, failed_segment=segment_name, available_fields=[])
        match current_concept.shape:
            case ConceptShape.VALUE:
                msg = (
                    f"Cannot bind '{path}': '{reached_path}' holds a '{current_concept.concept_ref}', which {current_concept.shape_reason}, "
                    f"so it is a leaf and the segment '{segment_name}' cannot follow it. It has no fields to walk."
                )
                raise BindingPathUnresolvedError(msg, path=path, failed_segment=segment_name, available_fields=[])
            case ConceptShape.NO_STRUCTURE:
                msg = (
                    f"Cannot bind '{path}': '{reached_path}' holds a '{current_concept.concept_ref}', which {current_concept.shape_reason}, "
                    f"so the segment '{segment_name}' has no structure to walk. It has no fields."
                )
                raise BindingPathUnresolvedError(msg, path=path, failed_segment=segment_name, available_fields=[])
            case ConceptShape.STRUCTURE:
                pass

        walkable_field = current_concept.get_field(name=segment_name)
        if walkable_field is None:
            msg = (
                f"Cannot bind '{path}': '{reached_path}' holds a '{current_concept.concept_ref}', which has no field '{segment_name}'. "
                f"{_fields_phrase(walkable_concept=current_concept)}"
            )
            raise BindingPathUnresolvedError(msg, path=path, failed_segment=segment_name, available_fields=current_concept.field_names)

        reached_path = f"{reached_path}.{segment_name}"
        is_last_segment = segment_index == len(segment_names) - 1
        if walkable_field.may_hold_nothing and not may_find_nothing:
            may_find_nothing = True
            first_optional_path = reached_path
        if walkable_field.is_list:
            crosses_any_list = True
        segments.append(BindingSegment(name=segment_name, crosses_list=walkable_field.is_list))

        match walkable_field.value_kind:
            case BindingValueKind.UNDERIVABLE:
                reason = walkable_field.underivable_reason or "no concept can be derived for its value"
                if is_last_segment:
                    msg = (
                        f"Cannot bind '{path}': the path ends on the segment '{segment_name}', at '{reached_path}', where {reason}, "
                        "so no concept can be derived for the result."
                    )
                    raise BindingPathUnresolvedError(msg, path=path, failed_segment=segment_name, available_fields=[])
                next_segment = segment_names[segment_index + 1]
                msg = (
                    f"Cannot bind '{path}': '{reached_path}' has no declared fields, since {reason}, "
                    f"so the segment '{next_segment}' cannot follow it."
                )
                raise BindingPathUnresolvedError(msg, path=path, failed_segment=next_segment, available_fields=[])
            case BindingValueKind.CONCEPT:
                if walkable_field.concept_ref is None:
                    msg = f"Cannot bind '{path}': the concept field '{reached_path}' names no concept."
                    raise BindingPathUnresolvedError(msg, path=path, failed_segment=segment_name, available_fields=[])
                derived_concept_ref = walkable_field.concept_ref
                # A field holding `native.Anything` holds a raw value of any type, generated as `Any`, never a content.
                holds_anything = walkable_field.concept_ref == NativeConceptCode.ANYTHING.concept_ref
                leaf_kind = BindingValueKind.ANYTHING if holds_anything else BindingValueKind.CONCEPT
                current_leaf_field = None
                if is_last_segment:
                    current_concept = None
                else:
                    current_concept = resolver.resolve_walkable_concept(concept_ref=walkable_field.concept_ref)
            case (
                BindingValueKind.TEXT
                | BindingValueKind.NUMBER
                | BindingValueKind.YES_NO
                | BindingValueKind.DATE
                | BindingValueKind.DATETIME
                | BindingValueKind.TIME
                | BindingValueKind.JSON
                | BindingValueKind.ANYTHING
            ):
                native_code = walkable_field.value_kind.leaf_native_concept_code
                if native_code is None:
                    msg = f"Cannot bind '{path}': '{reached_path}' holds a plain value with no native concept."
                    raise BindingPathUnresolvedError(msg, path=path, failed_segment=segment_name, available_fields=[])
                derived_concept_ref = native_code.concept_ref
                leaf_kind = walkable_field.value_kind
                current_leaf_field = walkable_field
                current_concept = None

    multiplicity: VariableMultiplicity | None = True if crosses_any_list else None
    return BindingDerivation(
        path=path,
        concept_ref=derived_concept_ref,
        multiplicity=multiplicity,
        # A list result is never absent: wherever a segment holds nothing, that part of the path contributes no items.
        may_find_nothing=may_find_nothing and not crosses_any_list,
        first_optional_path=first_optional_path if not crosses_any_list else None,
        leaf_kind=leaf_kind,
        segments=tuple(segments),
        root_multiplicity=root.multiplicity,
    )
