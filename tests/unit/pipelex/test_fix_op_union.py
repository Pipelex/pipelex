"""Unit tests for the ``FixOp`` discriminated union (``pipelex/suggested_fix.py``).

The union is what replaces the applier's hand-written shape checks: a malformed op must be
refused when it is parsed, not discovered halfway through a file rewrite. These tests pin the
three things that has to mean — the tag selects the variant, a variant refuses a field it does
not have, and a variant refuses to be built without the fields its handler reads — plus the
narrower ``MigrationOp`` alias, which is the whole mechanism keeping materializing operations
out of a migration ledger.
"""

import pytest
from pydantic import BaseModel, ValidationError

from pipelex.suggested_fix import (
    DeleteKeyOp,
    DeleteTableOp,
    EnsureTableOp,
    FixOp,
    FixOpKind,
    MigrationOp,
    MoveKeyOp,
    RemapValueOp,
    RenameTableKeyOp,
    SetKeyOp,
)


class _FixOpHolder(BaseModel):
    """A parse target for the wide alias — the shape ``SuggestedFix.ops`` has."""

    op: FixOp


class _MigrationOpHolder(BaseModel):
    """A parse target for the narrow alias — the shape a ledger entry's ops have."""

    op: MigrationOp


class TestFixOpUnion:
    @pytest.mark.parametrize(
        ("payload", "expected_type"),
        [
            ({"kind": "set_key", "table_path": ["pipe"], "key": "output", "value": "Text"}, SetKeyOp),
            ({"kind": "ensure_table", "table_path": ["pipe", "x", "inputs"]}, EnsureTableOp),
            ({"kind": "delete_key", "table_path": ["concept"], "key": "Text"}, DeleteKeyOp),
            ({"kind": "delete_table", "table_path": ["legacy"]}, DeleteTableOp),
            ({"kind": "rename_table_key", "table_path": [], "key": "old", "new_key": "new"}, RenameTableKeyOp),
            ({"kind": "move_key", "table_path": ["a"], "key": "k", "new_table_path": ["b"], "new_key": "k"}, MoveKeyOp),
            ({"kind": "remap_value", "table_path": ["a"], "key": "k", "mapping": {"old": "new"}}, RemapValueOp),
        ],
    )
    def test_kind_string_selects_the_variant(self, payload: dict[str, object], expected_type: type[BaseModel]) -> None:
        """A raw ``kind`` string — how an op arrives from JSON or from a ledger — picks its class."""
        assert isinstance(_FixOpHolder.model_validate({"op": payload}).op, expected_type)

    def test_a_field_the_kind_does_not_have_is_refused(self) -> None:
        """``extra="forbid"`` per variant: a ``new_key`` on a ``delete_key`` is a parse error.

        Under the flat model every op carried every optional field, so this payload parsed
        happily and the stray ``new_key`` was silently ignored at application time.
        """
        with pytest.raises(ValidationError):
            _FixOpHolder.model_validate({"op": {"kind": "delete_key", "table_path": [], "key": "x", "new_key": "y"}})

    def test_a_field_the_handler_reads_cannot_be_omitted(self) -> None:
        """A ``set_key`` without a value is refused at parse time, not raised at apply time."""
        with pytest.raises(ValidationError):
            _FixOpHolder.model_validate({"op": {"kind": "set_key", "table_path": [], "key": "x"}})

    @pytest.mark.parametrize("kind", [FixOpKind.ENSURE_TABLE, FixOpKind.DELETE_TABLE])
    def test_a_table_addressing_op_refuses_an_empty_path(self, kind: FixOpKind) -> None:
        """These two kinds address the table itself, and the document root is not a valid target."""
        with pytest.raises(ValidationError):
            _FixOpHolder.model_validate({"op": {"kind": kind, "table_path": []}})

    @pytest.mark.parametrize(
        "payload",
        [
            {"kind": "set_key", "table_path": ["section"], "key": "k", "value": "v"},
            {"kind": "ensure_table", "table_path": ["section"]},
        ],
    )
    def test_migration_alias_refuses_materializing_kinds(self, payload: dict[str, object]) -> None:
        """The narrow alias is what makes "a ledger never materializes" a parse error.

        Both kinds write material the file did not have, which is right when a typed error names
        the key and wrong under always-replay, where it would overwrite a user's own value on
        every single run. The op is well-formed — the wide alias accepts it — so the refusal is
        the alias choosing, not the payload being broken.
        """
        assert isinstance(_FixOpHolder.model_validate({"op": payload}).op, SetKeyOp | EnsureTableOp)
        with pytest.raises(ValidationError):
            _MigrationOpHolder.model_validate({"op": payload})

    def test_migration_alias_accepts_every_structural_kind(self) -> None:
        """Whatever ``is_structural`` claims is exactly what the narrow alias parses.

        Asserting the two against each other rather than against a hand-written list is what
        keeps a newly added kind from being classified in one place and forgotten in the other.
        """
        structural_kinds = {kind for kind in FixOpKind if kind.is_structural}
        payloads: dict[FixOpKind, dict[str, object]] = {
            FixOpKind.DELETE_KEY: {"kind": "delete_key", "table_path": ["s"], "key": "k"},
            FixOpKind.DELETE_TABLE: {"kind": "delete_table", "table_path": ["s"]},
            FixOpKind.RENAME_TABLE_KEY: {"kind": "rename_table_key", "table_path": ["s"], "key": "k", "new_key": "n"},
            FixOpKind.MOVE_KEY: {"kind": "move_key", "table_path": ["s"], "key": "k", "new_table_path": ["t"], "new_key": "k"},
            FixOpKind.REMAP_VALUE: {"kind": "remap_value", "table_path": ["s"], "key": "k", "mapping": {"old": "new"}},
        }
        assert set(payloads) == structural_kinds
        for payload in payloads.values():
            assert _MigrationOpHolder.model_validate({"op": payload}).op.kind.is_structural

    def test_a_wildcard_destination_is_refused(self) -> None:
        """A wildcard source means "each of these"; a wildcard destination names no target at all."""
        with pytest.raises(ValidationError):
            _FixOpHolder.model_validate(
                {"op": {"kind": "move_key", "table_path": ["deck", "*"], "key": "k", "new_table_path": ["deck", "*"], "new_key": "k"}}
            )

    def test_a_wildcard_source_is_accepted(self) -> None:
        """The source side is the whole point of the segment, and stays legal."""
        op = _FixOpHolder.model_validate(
            {"op": {"kind": "move_key", "table_path": ["deck", "*"], "key": "k", "new_table_path": ["storage"], "new_key": "k"}}
        ).op
        assert isinstance(op, MoveKeyOp)
        assert op.table_path == ["deck", "*"]

    def test_a_remap_needs_a_non_empty_mapping(self) -> None:
        """An empty mapping is an operation that can never do anything — an authoring mistake."""
        with pytest.raises(ValidationError):
            _FixOpHolder.model_validate({"op": {"kind": "remap_value", "table_path": ["a"], "key": "k", "mapping": {}}})
