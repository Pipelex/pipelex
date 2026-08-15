"""Unit tests for the applier's migration-only behaviour: ``move_key``, ``remap_value``,
the ``*`` wildcard segment, and the ``CONFLICT`` outcome.

Everything here is exercised on plain TOML strings rather than on ``.mthds`` fixtures, and
compared as serialized bytes without the MTHDS formatter — because that is exactly how a
configuration migration runs. Migration serializes with ``tomlkit.dumps`` and nothing else, so
a rename must not also reflow the user's spacing, and the byte compare is what pins it.
"""

from typing import Any, cast

import tomlkit

from pipelex.pipeline.fixes.applier import FixOpOutcome, apply_fix_ops
from pipelex.suggested_fix import (
    DeleteKeyOp,
    EnsureTableOp,
    FixOp,
    MoveKeyOp,
    RemapValueOp,
    RenameTableKeyOp,
)

_DOC = """\
# A configuration file with a user's own spacing.
root_key = "kept"

[reporting]
enabled        = true
output_config  = { path = "out.json" }

[reporting.retention]
days = 30

[deck]

[deck.gpt]
provider = "openai"
tier     = "premium"

[deck.claude]
provider = "anthropic"
tier     = "legacy"
"""


def _value_at(*, text: str, path: list[str]) -> Any:
    """Read one value out of serialized TOML by path — one typed funnel over tomlkit's ``Item``."""
    node = cast("dict[str, Any]", tomlkit.parse(text))
    for segment in path[:-1]:
        node = cast("dict[str, Any]", node[segment])
    return node[path[-1]]


def _table_at(*, text: str, path: list[str]) -> dict[str, Any]:
    """The table at ``path`` in serialized TOML, as a plain mapping."""
    return cast("dict[str, Any]", _value_at(text=text, path=path))


def _apply(*, text: str, ops: list[FixOp]) -> tuple[str, list[FixOpOutcome]]:
    """Apply ops to a parsed document and return (serialized bytes, outcomes)."""
    toml_doc = tomlkit.parse(text)
    applications = apply_fix_ops(toml_doc=toml_doc, ops=ops)
    dumped: str = tomlkit.dumps(toml_doc)  # pyright: ignore[reportUnknownMemberType]
    return dumped, [application.outcome for application in applications]


class TestFixApplierMigrationOps:
    def test_move_key_into_a_parent_that_has_to_be_created(self) -> None:
        """A table-valued key travels whole, and its missing destination parent is created."""
        text, outcomes = _apply(
            text=_DOC,
            ops=[MoveKeyOp(table_path=["reporting"], key="retention", new_table_path=["storage"], new_key="retention")],
        )
        assert outcomes == [FixOpOutcome.APPLIED]
        assert "retention" not in _table_at(text=text, path=["reporting"])
        assert _value_at(text=text, path=["storage", "retention", "days"]) == 30

    def test_move_key_replays_to_a_no_op(self) -> None:
        """Replaying a move over the already-migrated document changes nothing — no bytes, no ops.

        This is replay neutrality in miniature, and it is the property that lets a migration run
        every entry on every file on every run without a state stamp to tell it what to skip.
        """
        move_op: FixOp = MoveKeyOp(table_path=["reporting"], key="retention", new_table_path=["storage"], new_key="retention")
        migrated, _ = _apply(text=_DOC, ops=[move_op])
        replayed, outcomes = _apply(text=migrated, ops=[move_op])
        assert outcomes == [FixOpOutcome.SKIPPED]
        assert replayed == migrated

    def test_move_key_leaves_untouched_lines_byte_identical(self) -> None:
        """Only the moved key's lines change; the user's own spacing survives everywhere else."""
        text, _ = _apply(
            text=_DOC,
            ops=[MoveKeyOp(table_path=["reporting"], key="output_config", new_table_path=["reporting"], new_key="output")],
        )
        assert "# A configuration file with a user's own spacing." in text
        assert "enabled        = true" in text
        assert "output_config" not in text

    def test_move_key_onto_an_occupied_destination_conflicts_and_writes_nothing(self) -> None:
        """A conflicting move leaves the document byte-identical — including no created parents."""
        occupied = _DOC + '\n[storage]\nretention = "already mine"\n'
        text, outcomes = _apply(
            text=occupied,
            ops=[MoveKeyOp(table_path=["reporting"], key="retention", new_table_path=["storage"], new_key="retention")],
        )
        assert outcomes == [FixOpOutcome.CONFLICT]
        assert text == occupied

    def test_move_key_blocked_by_a_scalar_destination_parent_conflicts(self) -> None:
        """A destination parent occupied by a scalar is a conflict, not a silently created table."""
        # The scalar goes in the root's own span, above the first header — a bare key written
        # after one would belong to that table, not to the root.
        blocked = _DOC.replace('root_key = "kept"', 'root_key = "kept"\nstorage  = "not a table"')
        text, outcomes = _apply(
            text=blocked,
            ops=[MoveKeyOp(table_path=["reporting"], key="retention", new_table_path=["storage", "policy"], new_key="retention")],
        )
        assert outcomes == [FixOpOutcome.CONFLICT]
        assert text == blocked

    def test_move_key_with_an_absent_source_skips(self) -> None:
        """The guarded skip that makes always-replay possible: no source, no work, no error."""
        text, outcomes = _apply(
            text=_DOC,
            ops=[MoveKeyOp(table_path=["reporting"], key="never_existed", new_table_path=["storage"], new_key="x")],
        )
        assert outcomes == [FixOpOutcome.SKIPPED]
        assert text == _DOC

    def test_remap_value_rewrites_only_mapped_values(self) -> None:
        """A mapped value is rewritten; an unmapped one is left exactly as the user wrote it."""
        text, outcomes = _apply(
            text=_DOC,
            ops=[
                RemapValueOp(table_path=["deck", "claude"], key="tier", mapping={"legacy": "standard"}),
                RemapValueOp(table_path=["deck", "gpt"], key="tier", mapping={"legacy": "standard"}),
            ],
        )
        assert outcomes == [FixOpOutcome.APPLIED, FixOpOutcome.SKIPPED]
        assert _value_at(text=text, path=["deck", "claude", "tier"]) == "standard"
        assert _value_at(text=text, path=["deck", "gpt", "tier"]) == "premium"

    def test_remap_value_on_a_non_string_skips(self) -> None:
        """Remapping exists for renamed enumerated values, which are always strings."""
        _, outcomes = _apply(text=_DOC, ops=[RemapValueOp(table_path=["reporting"], key="enabled", mapping={"true": "yes"})])
        assert outcomes == [FixOpOutcome.SKIPPED]

    def test_remap_value_detail_never_echoes_the_users_value(self) -> None:
        """A report may name paths and ledger-supplied values, never a value read from the file."""
        toml_doc = tomlkit.parse(_DOC)
        applications = apply_fix_ops(
            toml_doc=toml_doc,
            ops=[RemapValueOp(table_path=["deck", "gpt"], key="provider", mapping={"nope": "other"})],
        )
        assert applications[0].outcome is FixOpOutcome.SKIPPED
        assert applications[0].detail is not None
        assert "openai" not in applications[0].detail

    def test_wildcard_applies_to_every_entry_of_an_open_mapping(self) -> None:
        """One op renames a field inside every entry the document happens to contain."""
        text, outcomes = _apply(text=_DOC, ops=[RenameTableKeyOp(table_path=["deck", "*"], key="tier", new_key="quality")])
        assert outcomes == [FixOpOutcome.APPLIED]
        assert _value_at(text=text, path=["deck", "gpt", "quality"]) == "premium"
        assert _value_at(text=text, path=["deck", "claude", "quality"]) == "legacy"

    def test_wildcard_conflict_in_one_entry_wins_over_siblings(self) -> None:
        """A conflict anywhere surfaces: burying it under a sibling's success is what it exists to prevent."""
        occupied = _DOC.replace('[deck.claude]\nprovider = "anthropic"', '[deck.claude]\nquality  = "taken"\nprovider = "anthropic"')
        _, outcomes = _apply(text=occupied, ops=[RenameTableKeyOp(table_path=["deck", "*"], key="tier", new_key="quality")])
        assert outcomes == [FixOpOutcome.CONFLICT]

    def test_wildcard_over_an_absent_node_skips(self) -> None:
        """Nothing matches, so nothing happens — and the document is untouched."""
        text, outcomes = _apply(text=_DOC, ops=[DeleteKeyOp(table_path=["no_such_section", "*"], key="anything")])
        assert outcomes == [FixOpOutcome.SKIPPED]
        assert text == _DOC

    def test_rename_onto_an_occupied_key_is_a_conflict_not_a_skip(self) -> None:
        """The outcome that used to hide inside SKIPPED, where no caller could act on it."""
        _, outcomes = _apply(text=_DOC, ops=[RenameTableKeyOp(table_path=["reporting"], key="output_config", new_key="enabled")])
        assert outcomes == [FixOpOutcome.CONFLICT]

    def test_ensure_table_over_a_non_table_key_is_a_conflict(self) -> None:
        """The second of ``ensure_table``'s reported bugs: this used to claim the parent was missing.

        The parent is right there — it is the *key* that is occupied by something that is not a
        table, and creating the table would destroy whatever the user put there.
        """
        _, outcomes = _apply(text=_DOC, ops=[EnsureTableOp(table_path=["reporting", "output_config", "path"])])
        assert outcomes == [FixOpOutcome.CONFLICT]

    def test_ensure_table_with_a_genuinely_missing_parent_still_skips(self) -> None:
        """The absence case keeps its guarded skip — only the misreported case changed."""
        _, outcomes = _apply(text=_DOC, ops=[EnsureTableOp(table_path=["no_such_section", "child"])])
        assert outcomes == [FixOpOutcome.SKIPPED]
