"""The fingerprint — a normalized projection of a surface's model tree.

The fingerprint is what the coverage gate diffs, so what it records and what it deliberately
ignores is the whole design. It records, per TOML-addressable path: the type, whether the path is
required within its parent, the enumerated member set where there is one, the value the surface's
defaults layer supplies, an open-node marker with the value-schema paths beneath it recorded under
a `*` segment, and a projection of the value's numeric and length bounds.

It is **deliberately not raw `model_json_schema()` output**, which moves for reasons that have
nothing to do with our schema — reference layout, titles, ordering, the validation library's own
version. A gate that cries wolf gets regenerated reflexively, and that is how a gate dies. The
same reasoning drives two normalizations that look like information loss and are not: a nested
model renders as `table` and an enum as `enum`, so renaming a *Python class* moves nothing, while
renaming a *field* or an enum *member* — the things a user's file actually contains — moves the
fingerprint and is caught.

The bound projection is built on the same principle, which is why it is a **closed whitelist**:
only the constraint kinds named in `CONSTRAINT_ATTRIBUTE_BY_CARRIER` are read, and anything else
an annotation carries is dropped rather than serialized. What lands in the golden is then a
function of our schema rather than of the validation library's representation of it — a strictness
flag, a before-validator, a pattern object or a constraint kind invented by a future release moves
nothing. `pattern` is excluded on purpose and permanently: regex containment is not decidable for
real expressions, so every pattern edit would read as a tightening, produce false positives, and
teach everyone to wave the gate through.

See `docs/migration-ledger.md` → "The fingerprint".
"""

import types
from collections.abc import Mapping, Sequence
from enum import Enum, StrEnum
from typing import Annotated, Any, Literal, Union, cast, get_args, get_origin

from annotated_types import Ge, Gt, Le, Lt, MaxLen, MinLen, MultipleOf
from pydantic import BaseModel, ConfigDict, Field
from pydantic.fields import FieldInfo

from pipelex.suggested_fix import WILDCARD_SEGMENT

PATH_SEPARATOR = "."
UNION_SEPARATOR = " | "
"""How a union renders in `value_type` — the one definition both the writer here and the parser in
`narrowing.py` read, so the two cannot drift apart."""

TABLE_TYPE = "table"
"""The rendering of a nested model. Class names are deliberately not recorded — see the module docstring."""

ENUM_TYPE = "enum"
"""The rendering of an enumerated type. The member set carries the shape; the class name does not."""

LITERAL_TYPE = "literal"
"""The rendering of a `Literal[...]`. Its spellings are recorded as enumerated members, like an enum's."""

STRING_TYPE = "str"
"""The rendering of `str` — the type every enumerated spelling widens into."""


class ConstraintKind(StrEnum):
    """The closed whitelist of constraint kinds the fingerprint records.

    Each value is also the attribute name the matching `annotated_types` object carries, which is
    what lets one mapping serve both the projection and the golden's key names.
    """

    GT = "gt"
    GE = "ge"
    LT = "lt"
    LE = "le"
    MIN_LENGTH = "min_length"
    MAX_LENGTH = "max_length"
    MULTIPLE_OF = "multiple_of"

    @property
    def widest_is_the_lower_value(self) -> bool:
        """Which direction of this kind admits more values — the merge rule across union members.

        A union's value domain is the union of its members' domains, so a bound found on one
        member never binds the others: the widest of the two is the one the path really has.
        """
        match self:
            case ConstraintKind.GT | ConstraintKind.GE | ConstraintKind.MIN_LENGTH | ConstraintKind.MULTIPLE_OF:
                return True
            case ConstraintKind.LT | ConstraintKind.LE | ConstraintKind.MAX_LENGTH:
                return False


CONSTRAINT_ATTRIBUTE_BY_CARRIER: dict[type[Any], ConstraintKind] = {
    Gt: ConstraintKind.GT,
    Ge: ConstraintKind.GE,
    Lt: ConstraintKind.LT,
    Le: ConstraintKind.LE,
    MinLen: ConstraintKind.MIN_LENGTH,
    MaxLen: ConstraintKind.MAX_LENGTH,
    MultipleOf: ConstraintKind.MULTIPLE_OF,
}
"""The whitelist itself. `annotated_types` is a zero-dependency interchange vocabulary, not
validation-library internals, which is what makes reading it compatible with the strip above."""


class PathFingerprint(BaseModel):
    """What the fingerprint records about one TOML-addressable path."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    value_type: str
    required: bool
    """Required *within its parent*. Whether the path is required in a document also depends on
    whether its ancestors are present — see `is_effectively_required` on the surface fingerprint."""

    enum_members: list[str] | None = None
    default: Any | None = None
    """The value the surface's defaults layer supplies, or `None` for none recorded. TOML has no
    null, so an absent default and a null default are the same thing and need no distinction."""

    open_node: bool = False
    """A mapping from arbitrary user-owned keys to a value schema. The keys belong to the user;
    the value schema belongs to us and is recorded beneath a `*` segment."""

    constraints: dict[ConstraintKind, int | float] | None = None
    """The whitelisted bounds on the value, or `None` for none recorded. Recorded so that a bound
    a schema change *tightens* is visible to the gate: it keeps every path and every enumerated
    spelling, so nothing else in the projection moves, while a value a user's file legitimately
    carries stops validating. What is deliberately absent is everything outside the whitelist —
    see the module docstring."""


class SurfaceFingerprint(BaseModel):
    """A whole surface's model tree, projected and stably ordered."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    surface_id: str
    schema_version: int
    paths: dict[str, PathFingerprint] = Field(default_factory=dict[str, PathFingerprint])

    def path_names(self) -> set[str]:
        return set(self.paths)

    def is_effectively_required(self, *, path: str) -> bool:
        """Whether a document that the defaults layer feeds must carry this path.

        A path nested under an optional table is not required of a document that omits the table,
        so requiredness only propagates through ancestors that are themselves required.
        """
        segments = path.split(PATH_SEPARATOR)
        for depth in range(1, len(segments) + 1):
            ancestor = self.paths.get(PATH_SEPARATOR.join(segments[:depth]))
            if ancestor is None or not ancestor.required:
                return False
        return True


def compute_fingerprint(
    *,
    surface_id: str,
    schema_version: int,
    config_model: type[BaseModel],
    defaults_document: dict[str, Any],
) -> SurfaceFingerprint:
    """Project a surface's model tree against its defaults document."""
    collected: dict[str, PathFingerprint] = {}
    _walk_model(
        config_model=config_model,
        prefix=(),
        defaults=defaults_document,
        ancestry=(config_model,),
        collected=collected,
    )
    return SurfaceFingerprint(
        surface_id=surface_id,
        schema_version=schema_version,
        paths={path: collected[path] for path in sorted(collected)},
    )


def _walk_model(
    *,
    config_model: type[BaseModel],
    prefix: tuple[str, ...],
    defaults: dict[str, Any] | None,
    ancestry: tuple[type[BaseModel], ...],
    collected: dict[str, PathFingerprint],
) -> None:
    for field_name, field_info in config_model.model_fields.items():
        _record_field(
            path=(*prefix, field_name),
            annotation=field_info.annotation,
            # A top-level `Annotated[int, Field(ge=1)]` is unwrapped by pydantic before we ever see
            # the annotation: the constraint is folded into the field's metadata instead, so a walk
            # that read the annotation alone would be blind to every bound declared the usual way.
            field_metadata=field_info.metadata,
            required=field_info.is_required(),
            defaults_value=_defaults_value(defaults=defaults, key=field_name),
            ancestry=ancestry,
            collected=collected,
        )


def _record_field(
    *,
    path: tuple[str, ...],
    annotation: Any,
    required: bool,
    defaults_value: Any,
    ancestry: tuple[type[BaseModel], ...],
    collected: dict[str, PathFingerprint],
    field_metadata: Sequence[Any] = (),
) -> None:
    resolved = _strip_annotated(annotation=annotation)
    nested_model = _as_nested_model(annotation=resolved)
    open_value_type = _as_open_mapping_value(annotation=resolved)
    dotted = PATH_SEPARATOR.join(path)

    if nested_model is not None:
        # A table's own default is not recorded: every child records its own, and recording the
        # whole subtree again would bloat the golden without making any diff more legible.
        collected[dotted] = PathFingerprint(value_type=TABLE_TYPE, required=required)
        if nested_model in ancestry:
            # A model reachable from itself would walk forever. Nothing in the configuration tree
            # is recursive today; this is the guard that keeps a future one from hanging the gate.
            return
        _walk_model(
            config_model=nested_model,
            prefix=path,
            defaults=_as_mapping(value=defaults_value),
            ancestry=(*ancestry, nested_model),
            collected=collected,
        )
        return

    collected[dotted] = PathFingerprint(
        value_type=_render_type(annotation=resolved),
        required=required,
        enum_members=_collect_enum_members(annotation=resolved),
        default=_json_safe(value=defaults_value),
        open_node=open_value_type is not None,
        constraints=_collect_constraints(annotation=annotation, field_metadata=field_metadata),
    )

    if open_value_type is not None:
        # The keys under an open node are the user's and cannot be enumerated; the value schema
        # is ours, and an operation may address it through the `*` segment.
        _record_field(
            path=(*path, WILDCARD_SEGMENT),
            annotation=open_value_type,
            required=True,
            defaults_value=None,
            ancestry=ancestry,
            collected=collected,
        )


def _defaults_value(*, defaults: dict[str, Any] | None, key: str) -> Any:
    if defaults is None:
        return None
    return defaults.get(key)


def _as_mapping(*, value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value  # pyright: ignore[reportUnknownVariableType]
    return None


def _strip_annotated(*, annotation: Any) -> Any:
    """Remove `Annotated[...]` wrappers and a `| None` union member.

    Optionality is already carried by requiredness, and unwrapping it here is what lets an
    optional nested table (`ndjson: NdjsonTracingConfig | None`) be walked as the table it is.
    """
    while get_origin(annotation) is Annotated:
        annotation = get_args(annotation)[0]
    if _is_union(annotation=annotation):
        members = [member for member in get_args(annotation) if member is not types.NoneType]
        if len(members) == 1:
            return _strip_annotated(annotation=members[0])
    return annotation


def _is_union(*, annotation: Any) -> bool:
    return get_origin(annotation) in {Union, types.UnionType}


def _as_nested_model(*, annotation: Any) -> type[BaseModel] | None:
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation
    return None


def _as_open_mapping_value(*, annotation: Any) -> Any:
    """The value schema of an open mapping, or `None` when the annotation is not one.

    `dict[str, X]` and `Mapping[str, X]` are the same shape to a file — a table whose keys are the
    user's — so both are open nodes.
    """
    if get_origin(annotation) not in {dict, Mapping}:
        return None
    args = get_args(annotation)
    if len(args) != 2:
        return None
    return args[1]


def _render_type(*, annotation: Any) -> str:
    # Strip at every level, not just the top one: a union member carrying its own constraint
    # (`Annotated[int, Field(ge=1)] | Literal["unbounded"]`) would otherwise render the
    # constraint object into the golden, where a pydantic upgrade could move it. The bounds are not
    # lost — `_collect_constraints` records the whitelisted ones under their own field, in a
    # vocabulary that is ours rather than the library's.
    annotation = _strip_annotated(annotation=annotation)
    if annotation is Any:
        return "any"
    if annotation is types.NoneType:
        return "none"
    if _is_union(annotation=annotation):
        return UNION_SEPARATOR.join(_render_type(annotation=member) for member in get_args(annotation))
    if get_origin(annotation) is Literal:
        return LITERAL_TYPE
    origin = get_origin(annotation)
    if origin is not None:
        args = get_args(annotation)
        rendered_args = ", ".join(_render_type(annotation=arg) for arg in args)
        return f"{_render_bare(annotation=origin)}[{rendered_args}]" if rendered_args else _render_bare(annotation=origin)
    return _render_bare(annotation=annotation)


def _render_bare(*, annotation: Any) -> str:
    if isinstance(annotation, type):
        bare_type: type[Any] = annotation
        if issubclass(bare_type, BaseModel):
            return TABLE_TYPE
        if issubclass(bare_type, Enum):
            return ENUM_TYPE
        return bare_type.__name__.lower()
    name: Any = getattr(annotation, "__name__", None)
    return name.lower() if isinstance(name, str) else "unknown"


def _collect_constraints(*, annotation: Any, field_metadata: Sequence[Any]) -> dict[ConstraintKind, int | float] | None:
    """The whitelisted bounds on one path's value, merged across the annotation's union members.

    Two sources are read and no others: the field's own metadata, which is where a top-level
    `Field(ge=1)` ends up, and the `Annotated` wrappers reachable through unions — the shape
    `Annotated[int, Field(ge=1)] | Literal["unbounded"]` that the walk would otherwise miss.

    A generic container's arguments are deliberately **not** descended into. A bound inside
    `list[Annotated[int, Field(ge=1)]]` binds the items, not the list, and recording it at the
    list's path would attribute to one path a constraint belonging to another — the value schema
    beneath an open node gets its own `*` record and its own constraints there.
    """
    carriers: list[Any] = list(field_metadata)
    _gather_constraint_carriers(annotation=annotation, carriers=carriers)
    collected: dict[ConstraintKind, int | float] = {}
    _absorb_constraint_carriers(carriers=carriers, collected=collected)
    return {kind: collected[kind] for kind in sorted(collected)} if collected else None


def _gather_constraint_carriers(*, annotation: Any, carriers: list[Any]) -> None:
    if get_origin(annotation) is Annotated:
        args = get_args(annotation)
        carriers.extend(args[1:])
        _gather_constraint_carriers(annotation=args[0], carriers=carriers)
        return
    if _is_union(annotation=annotation):
        for member in get_args(annotation):
            _gather_constraint_carriers(annotation=member, carriers=carriers)


def _absorb_constraint_carriers(*, carriers: Sequence[Any], collected: dict[ConstraintKind, int | float]) -> None:
    """Fold every carrier the whitelist recognizes into the projection, and drop the rest silently.

    Dropping is the whole point: a carrier this function does not recognize — a strictness flag, a
    before-validator, a pattern object, a kind a future release invents — must leave no trace in
    the golden, or the gate starts moving for reasons that are not about our schema.
    """
    for carrier in carriers:
        if isinstance(carrier, FieldInfo):
            # `Field(...)` inside an `Annotated` arrives as a `FieldInfo` carrying its own metadata.
            _absorb_constraint_carriers(carriers=carrier.metadata, collected=collected)
            continue
        kind = CONSTRAINT_ATTRIBUTE_BY_CARRIER.get(cast("type[Any]", type(carrier)))
        if kind is None:
            continue
        value = getattr(carrier, kind, None)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            # A bound expressed over dates, decimals or anything else is outside the projection:
            # it has no stable rendering here and no comparison this gate could make.
            continue
        existing = collected.get(kind)
        if existing is None:
            collected[kind] = value
        elif kind.widest_is_the_lower_value:
            collected[kind] = min(existing, value)
        else:
            collected[kind] = max(existing, value)


def _collect_enum_members(*, annotation: Any) -> list[str] | None:
    """Every enumerated spelling reachable in the annotation, sorted and deduplicated.

    Both sources count: an `Enum` class and a string `Literal`. They are the same thing to a TOML
    file — a closed set of legal spellings — and either can lose a member, which is the removal
    the coverage gate demands a remap for.
    """
    members: set[str] = set()
    _gather_enum_members(annotation=annotation, members=members)
    return sorted(members) if members else None


def _gather_enum_members(*, annotation: Any, members: set[str]) -> None:
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        members.update(str(member.value) for member in annotation)
        return
    if get_origin(annotation) is Literal:
        members.update(str(arg) for arg in get_args(annotation) if isinstance(arg, str))
        return
    for arg in get_args(annotation):
        _gather_enum_members(annotation=arg, members=members)


def _json_safe(*, value: Any) -> Any:
    """Coerce a defaults-layer value into something a golden file can hold verbatim."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        typed_mapping = cast("dict[Any, Any]", value)
        return {str(key): _json_safe(value=item) for key, item in typed_mapping.items()}
    if isinstance(value, Sequence):
        typed_sequence = cast("Sequence[Any]", value)
        return [_json_safe(value=item) for item in typed_sequence]
    return str(value)
