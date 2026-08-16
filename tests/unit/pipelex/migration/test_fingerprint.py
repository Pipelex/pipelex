"""Unit tests for the fingerprint — the projection the coverage gate diffs.

The tests are written against small synthetic models rather than the real configuration tree, on
purpose. What matters here is that the projection records the things a user's TOML file actually
contains — paths, requiredness, enumerated spellings, the value beneath the file — and ignores the
things it does not, such as which Python class a table happens to be. A real-model test would go
red on every legitimate configuration change and teach everyone to regenerate rather than read.
"""

from collections.abc import Mapping
from decimal import Decimal
from enum import Enum, StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from pipelex.migration.fingerprint import ENUM_TYPE, TABLE_TYPE, ConstraintKind, compute_fingerprint


class _Mode(StrEnum):
    FAST = "fast"
    SLOW = "slow"


class _Level(int, Enum):
    """Deliberately not a `StrEnum`: the projection has to say so rather than stringify it."""

    LOW = 1
    HIGH = 2


class _Leaf(BaseModel):
    name: str
    count: int = 3


class _Synthetic(BaseModel):
    mode: _Mode
    leaf: _Leaf
    optional_leaf: _Leaf | None = None
    deck: dict[str, _Leaf]
    labels: dict[str, str]
    modes: dict[str, _Mode]
    mode_list: list[_Mode]
    mode_maps: list[dict[str, _Mode]]
    level: _Level = _Level.LOW
    tags: list[str]
    bounded: Annotated[int, Field(ge=1)] | Literal["unbounded"] = 1
    # A field-level bound binds the whole field, whatever a union member declares for itself —
    # pydantic applies it on top of the member's own. The field is never validated here; the
    # fingerprint reads the annotation and the metadata, and this is the shape that separates them.
    capped: Annotated[int, Field(le=100)] | Literal["auto"] = Field(default="auto", le=6)
    retries: int = Field(default=3, ge=0, le=10)
    lenient: str = Field(default="x", strict=False)
    item_bounded: list[Annotated[int, Field(ge=1)]] = Field(default_factory=list[int])
    amount: Decimal = Field(default=Decimal(1), ge=Decimal(0))


class _SelfReferential(BaseModel):
    value: str = "x"
    child: "_SelfReferential | None" = None


_DEFAULTS: dict[str, Any] = {
    "mode": "fast",
    "leaf": {"name": "written"},
    "labels": {"a": "b"},
    "tags": ["one"],
}


def _fingerprint(*, defaults: dict[str, Any] | None = None):
    return compute_fingerprint(
        surface_id="synthetic",
        schema_version=1,
        config_model=_Synthetic,
        defaults_document=_DEFAULTS if defaults is None else defaults,
    )


class TestFingerprintPaths:
    def test_every_addressable_path_is_recorded_and_nothing_else_is(self) -> None:
        """The path set is the vocabulary every ledger operation is written in."""
        assert _fingerprint().path_names() == {
            "mode",
            "leaf",
            "leaf.name",
            "leaf.count",
            "optional_leaf",
            "optional_leaf.name",
            "optional_leaf.count",
            "deck",
            "deck.*",
            "deck.*.name",
            "deck.*.count",
            "labels",
            "labels.*",
            "modes",
            "modes.*",
            "mode_list",
            "mode_maps",
            "level",
            "tags",
            "bounded",
            "capped",
            "retries",
            "lenient",
            "item_bounded",
            "amount",
        }

    def test_paths_are_stably_ordered(self) -> None:
        """The golden's line order must not depend on field declaration order or dict iteration.

        A fingerprint is checked in and read as a diff; ordering that moved for its own reasons
        would bury the one real change among two hundred reordered lines.
        """
        paths = list(_fingerprint().paths)
        assert paths == sorted(paths)

    def test_an_open_mapping_is_marked_and_its_value_schema_lands_under_a_wildcard(self) -> None:
        """The keys belong to the user; the value schema belongs to us and is addressable."""
        fingerprint = _fingerprint()
        assert fingerprint.paths["deck"].open_node is True
        assert fingerprint.paths["deck.*"].value_type == TABLE_TYPE
        assert fingerprint.paths["deck.*.name"].value_type == "str"

    def test_an_abstract_mapping_is_an_open_node_too(self) -> None:
        """`Mapping[str, X]` is the same shape to a file as `dict[str, X]`; the gate must see it as open,
        or a wildcard operation over it would be refused as addressing a path the fingerprint lacks.
        """

        class _WithMapping(BaseModel):
            entries: Mapping[str, _Leaf]

        fingerprint = compute_fingerprint(surface_id="synthetic", schema_version=1, config_model=_WithMapping, defaults_document={})
        assert fingerprint.paths["entries"].open_node is True
        assert fingerprint.paths["entries.*.name"].value_type == "str"

    def test_a_scalar_mapping_gets_a_wildcard_leaf_and_no_deeper_paths(self) -> None:
        fingerprint = _fingerprint()
        assert fingerprint.paths["labels"].open_node is True
        assert fingerprint.paths["labels.*"].value_type == "str"
        assert not [path for path in fingerprint.path_names() if path.startswith("labels.*.")]

    def test_an_optional_table_is_walked_as_the_table_it_is(self) -> None:
        """`X | None` is unwrapped: the keys inside it are perfectly addressable when present."""
        fingerprint = _fingerprint()
        assert fingerprint.paths["optional_leaf"].value_type == TABLE_TYPE
        assert fingerprint.paths["optional_leaf"].required is False
        assert fingerprint.paths["optional_leaf.name"].required is True

    def test_a_self_referential_model_terminates(self) -> None:
        """Nothing in the configuration tree is recursive today; this is what stops the next one hanging the gate.

        A recursive model has no finite path set, so the walk records the repeating table and
        stops descending into it. The paths beneath it are unaddressable, which is the honest
        answer — and it is the same answer the applier gives for an array of tables.
        """
        fingerprint = compute_fingerprint(
            surface_id="recursive",
            schema_version=1,
            config_model=_SelfReferential,
            defaults_document={},
        )
        assert fingerprint.path_names() == {"value", "child"}


class TestFingerprintRecords:
    def test_an_enumerated_path_records_its_members_and_not_its_class_name(self) -> None:
        """Renaming a Python enum class changes no user's file, so it must move nothing."""
        record = _fingerprint().paths["mode"]
        assert record.value_type == ENUM_TYPE
        assert record.enum_members == ["fast", "slow"]

    def test_the_members_beneath_an_open_mapping_are_recorded_on_the_wildcard_and_not_on_the_table(self) -> None:
        """The container's own value is a table, not an enumerated spelling.

        Recording the members twice made the coverage gate demand a `remap_value` at the container
        path as well as at the wildcard one — and a remap of a table value can never fire, so the
        demand had no legal answer. The wildcard record is the one an operation can address.
        """
        fingerprint = _fingerprint()
        assert fingerprint.paths["modes"].enum_members is None
        assert fingerprint.paths["modes.*"].enum_members == ["fast", "slow"]

    def test_the_members_inside_a_list_are_recorded_on_the_list_itself(self) -> None:
        """A list gets no child record, so the list's own path is the only place they can live.

        Dropping them there would make a member removed from a `list[enum]` invisible to the gate;
        the remedy for one is an `unsafe` entry, which the coverage gate asks for by name.
        """
        assert _fingerprint().paths["mode_list"].enum_members == ["fast", "slow"]

    def test_the_members_of_a_mapping_nested_in_a_list_are_recorded_on_the_list_itself(self) -> None:
        """The suppression belongs to the field's own open node, not to every mapping anywhere inside it.

        A `list[dict[str, enum]]` has no `*` child — the field's open node is the list, and a list
        gets no child record — so suppressing the mapping's members here dropped them entirely, and
        retiring one moved nothing in the fingerprint at all. The gate would have passed a change
        that breaks every file carrying the spelling.
        """
        fingerprint = _fingerprint()
        assert fingerprint.paths["mode_maps"].enum_members == ["fast", "slow"]
        assert "mode_maps.*" not in fingerprint.path_names()

    def test_an_enum_over_non_string_values_records_no_spelling(self) -> None:
        """The same rule a `Literal` over non-strings already follows, for the same reason.

        A remap rewrites a *string* value, so recording `1` and `2` as spellings would let the
        accounting credit a `remap_value` the applier skips on every run — a green gate over a file
        the new schema rejects. Recording nothing makes the projection's blind spot visible as a
        blind spot, which is what the `Literal` rule already does.
        """
        assert _fingerprint().paths["level"].enum_members is None

    def test_a_string_literal_counts_as_an_enumerated_spelling(self) -> None:
        """A `Literal` and an `Enum` are the same thing to a TOML file: a closed set of spellings."""
        assert _fingerprint().paths["bounded"].enum_members == ["unbounded"]

    def test_a_constraint_object_is_not_rendered_into_the_type(self) -> None:
        """`Annotated[int, Field(ge=1)]` renders as `int` — a pydantic upgrade must not move the golden."""
        assert _fingerprint().paths["bounded"].value_type == "int | literal"

    def test_a_whitelisted_bound_is_recorded_under_its_own_key(self) -> None:
        """A tightened bound breaks a user's file while moving nothing else in the projection."""
        assert _fingerprint().paths["retries"].constraints == {ConstraintKind.GE: 0, ConstraintKind.LE: 10}

    def test_a_bound_pydantic_folded_into_the_field_metadata_is_still_found(self) -> None:
        """`Field(ge=0)` never appears in the annotation — pydantic moves it to the field's metadata,
        so a walk reading the annotation alone would be blind to every bound declared the usual way.
        """
        assert ConstraintKind.GE in (_fingerprint().paths["retries"].constraints or {})

    def test_a_field_level_bound_binds_the_whole_field_and_a_member_may_not_loosen_it(self) -> None:
        """`Field(le=6)` on the field is applied on top of whatever a union member declares.

        Merging the two sources by "widest wins" would record `le=100` and read a later tightening
        of the field-level bound as a change to an already-looser one — the gate going quiet on
        exactly the values that stop validating.
        """
        assert _fingerprint().paths["capped"].constraints == {ConstraintKind.LE: 6}

    def test_a_bound_nested_inside_a_union_member_is_found_too(self) -> None:
        """The shape `Annotated[int, Field(ge=1)] | Literal["unbounded"]`, which the type rendering strips."""
        assert _fingerprint().paths["bounded"].constraints == {ConstraintKind.GE: 1}

    def test_metadata_outside_the_whitelist_is_dropped_rather_than_serialized(self) -> None:
        """The closed whitelist is what keeps the golden a function of our schema.

        `Field(strict=False)` is on dozens of configuration fields as a house convention. Recording
        it — or any other carrier the validation library invents — would move goldens for reasons
        that have nothing to do with what a user's file may contain.
        """
        assert _fingerprint().paths["lenient"].constraints is None

    def test_a_bound_on_a_container_item_is_not_attributed_to_the_container(self) -> None:
        """`list[Annotated[int, Field(ge=1)]]` bounds the items, not the list."""
        assert _fingerprint().paths["item_bounded"].constraints is None

    def test_a_bound_over_a_non_numeric_value_is_dropped(self) -> None:
        """A `Decimal` (or a date) bound is outside the projection — the whitelist is over kinds *and* value types."""
        assert _fingerprint().paths["amount"].constraints is None

    def test_a_path_with_no_bound_records_none(self) -> None:
        assert _fingerprint().paths["leaf.name"].constraints is None

    def test_a_nested_model_renders_as_a_table(self) -> None:
        assert _fingerprint().paths["leaf"].value_type == TABLE_TYPE

    def test_the_defaults_layer_value_is_recorded_where_one_exists(self) -> None:
        fingerprint = _fingerprint()
        assert fingerprint.paths["leaf.name"].default == "written"
        assert fingerprint.paths["mode"].default == "fast"
        assert fingerprint.paths["tags"].default == ["one"]

    def test_a_path_the_defaults_document_omits_records_no_value(self) -> None:
        assert _fingerprint().paths["leaf.count"].default is None

    def test_a_table_records_no_default_of_its_own(self) -> None:
        """Its children each record theirs; repeating the subtree would bloat the golden for nothing."""
        assert _fingerprint().paths["leaf"].default is None


class TestEffectiveRequiredness:
    def test_a_required_path_under_required_ancestors_is_effectively_required(self) -> None:
        assert _fingerprint().is_effectively_required(path="leaf.name") is True

    def test_a_required_path_under_an_optional_table_is_not(self) -> None:
        """A document that omits the whole table owes nothing to the keys inside it."""
        assert _fingerprint().is_effectively_required(path="optional_leaf.name") is False

    def test_an_optional_path_is_not(self) -> None:
        assert _fingerprint().is_effectively_required(path="leaf.count") is False
