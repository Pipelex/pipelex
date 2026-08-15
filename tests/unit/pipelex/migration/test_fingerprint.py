"""Unit tests for the fingerprint — the projection the coverage gate diffs.

The tests are written against small synthetic models rather than the real configuration tree, on
purpose. What matters here is that the projection records the things a user's TOML file actually
contains — paths, requiredness, enumerated spellings, the value beneath the file — and ignores the
things it does not, such as which Python class a table happens to be. A real-model test would go
red on every legitimate configuration change and teach everyone to regenerate rather than read.
"""

from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from pipelex.migration.fingerprint import ENUM_TYPE, TABLE_TYPE, compute_fingerprint


class _Mode(StrEnum):
    FAST = "fast"
    SLOW = "slow"


class _Leaf(BaseModel):
    name: str
    count: int = 3


class _Synthetic(BaseModel):
    mode: _Mode
    leaf: _Leaf
    optional_leaf: _Leaf | None = None
    deck: dict[str, _Leaf]
    labels: dict[str, str]
    tags: list[str]
    bounded: Annotated[int, Field(ge=1)] | Literal["unbounded"] = 1


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
            "tags",
            "bounded",
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

    def test_a_string_literal_counts_as_an_enumerated_spelling(self) -> None:
        """A `Literal` and an `Enum` are the same thing to a TOML file: a closed set of spellings."""
        assert _fingerprint().paths["bounded"].enum_members == ["unbounded"]

    def test_a_constraint_object_is_not_rendered_into_the_type(self) -> None:
        """`Annotated[int, Field(ge=1)]` renders as `int` — a pydantic upgrade must not move the golden."""
        assert _fingerprint().paths["bounded"].value_type == "int | literal"

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
