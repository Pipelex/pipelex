"""Unit tests for the replay engine — what a ledger does to one document.

The guarantees under test are the ones a user's machine depends on: every run replays everything
and the applier skips what is already done, an `unsafe` entry is never written and stays silent on
a file that does not need it, and serialization contributes no changes of its own.
"""

from typing import Any, cast

import tomlkit

from pipelex.migration.engine import replay_ledger_over_text
from pipelex.migration.plan import BlockedEntryReason
from pipelex.migration.safety import MigrationSafety
from pipelex.suggested_fix import DeleteKeyOp, MoveKeyOp, RenameTableKeyOp
from tests.unit.pipelex.migration.conftest import EntryBuilder, LedgerBuilder

OLD_SHAPE = """\
# A user's file, with their own comments and spacing.
[reporting]
output_config   = { directory = "out" }
retention       = 30

[legacy_reporting]
enabled = true
"""

CURRENT_SHAPE = """\
[reporting]
output = { directory = "out" }

[storage]
retention = 30
"""


class TestReplayEngine:
    def test_a_safe_entry_applies_and_reports_only_the_operations_that_fired(
        self,
        build_entry: EntryBuilder,
        build_ledger: LedgerBuilder,
    ) -> None:
        entry = build_entry(
            to_schema_version=2,
            ops=[
                RenameTableKeyOp(table_path=["reporting"], key="output_config", new_key="output"),
                MoveKeyOp(table_path=["reporting"], key="retention", new_table_path=["storage"], new_key="retention"),
                DeleteKeyOp(table_path=["reporting"], key="never_existed"),
            ],
        )
        ledger = build_ledger(entries=[entry])

        replay = replay_ledger_over_text(ledger=ledger, text=OLD_SHAPE)

        assert not replay.blocked
        assert len(replay.steps) == 1
        step = replay.steps[0]
        assert step.entry_id == "example-config@2"
        assert [op.kind for op in step.applied_ops] == ["rename_table_key", "move_key"]
        assert replay.did_change_document
        assert "output = " in replay.text
        assert "[storage]" in replay.text

    def test_replay_over_an_already_current_file_is_a_byte_level_no_op(
        self,
        build_entry: EntryBuilder,
        build_ledger: LedgerBuilder,
    ) -> None:
        """Replay neutrality, stated over a file the current schema accepts.

        Every operation's source is material some schema version removed, so on a current file
        every operation skips — and skipping mutates nothing, so the bytes are identical.
        """
        ledger = build_ledger(
            entries=[
                build_entry(
                    to_schema_version=2,
                    ops=[
                        RenameTableKeyOp(table_path=["reporting"], key="output_config", new_key="output"),
                        MoveKeyOp(table_path=["reporting"], key="retention", new_table_path=["storage"], new_key="retention"),
                    ],
                )
            ]
        )

        replay = replay_ledger_over_text(ledger=ledger, text=CURRENT_SHAPE)

        assert not replay.steps
        assert not replay.blocked
        assert not replay.did_change_document
        assert replay.text == CURRENT_SHAPE

    def test_replaying_twice_equals_replaying_once(
        self,
        build_entry: EntryBuilder,
        build_ledger: LedgerBuilder,
    ) -> None:
        ledger = build_ledger(
            entries=[
                build_entry(
                    to_schema_version=2,
                    ops=[RenameTableKeyOp(table_path=["reporting"], key="output_config", new_key="output")],
                )
            ]
        )

        once = replay_ledger_over_text(ledger=ledger, text=OLD_SHAPE)
        twice = replay_ledger_over_text(ledger=ledger, text=once.text)

        assert not twice.steps
        assert twice.text == once.text

    def test_entries_compose_in_sequence_for_a_file_coming_from_the_first_version(
        self,
        build_entry: EntryBuilder,
        build_ledger: LedgerBuilder,
    ) -> None:
        """A key renamed at 2 and moved at 3 lands correctly for a file still at 1.

        This is also the shape that catches the tomlkit rename-then-address defect the engine
        re-reads the document to work around: without the re-read, the move raises `KeyError`
        from inside the library rather than relocating the key.
        """
        ledger = build_ledger(
            entries=[
                build_entry(
                    to_schema_version=2,
                    ops=[RenameTableKeyOp(table_path=["reporting"], key="retention", new_key="keep_days")],
                ),
                build_entry(
                    to_schema_version=3,
                    ops=[MoveKeyOp(table_path=["reporting"], key="keep_days", new_table_path=["storage"], new_key="keep_days")],
                ),
            ]
        )

        replay = replay_ledger_over_text(ledger=ledger, text=OLD_SHAPE)

        assert [step.to_schema_version for step in replay.steps] == [2, 3]
        migrated = cast("dict[str, Any]", tomlkit.loads(replay.text))
        assert migrated["storage"]["keep_days"] == 30
        assert "retention" not in migrated["reporting"]

    def test_an_unsafe_entry_is_reported_without_writing_anything(
        self,
        build_entry: EntryBuilder,
        build_ledger: LedgerBuilder,
    ) -> None:
        ledger = build_ledger(
            entries=[
                build_entry(
                    to_schema_version=2,
                    safety=MigrationSafety.UNSAFE,
                    guidance="Decide which reporting directory you want.",
                    ops=[RenameTableKeyOp(table_path=["reporting"], key="output_config", new_key="output")],
                )
            ]
        )

        replay = replay_ledger_over_text(ledger=ledger, text=OLD_SHAPE)

        assert not replay.steps
        assert len(replay.blocked) == 1
        blocked = replay.blocked[0]
        assert blocked.reason is BlockedEntryReason.UNSAFE
        assert blocked.guidance == "Decide which reporting directory you want."
        assert not blocked.applied_ops
        assert not replay.did_change_document
        assert replay.text == OLD_SHAPE

    def test_an_unsafe_entry_with_nothing_to_do_stays_silent(
        self,
        build_entry: EntryBuilder,
        build_ledger: LedgerBuilder,
    ) -> None:
        """Otherwise every user with a perfectly current file is warned at every boot, forever."""
        ledger = build_ledger(
            entries=[
                build_entry(
                    to_schema_version=2,
                    safety=MigrationSafety.UNSAFE,
                    ops=[RenameTableKeyOp(table_path=["reporting"], key="output_config", new_key="output")],
                )
            ]
        )

        replay = replay_ledger_over_text(ledger=ledger, text=CURRENT_SHAPE)

        assert not replay.blocked
        assert not replay.steps

    def test_a_conflicting_entry_is_blocked_and_still_names_what_it_did_apply(
        self,
        build_entry: EntryBuilder,
        build_ledger: LedgerBuilder,
    ) -> None:
        """A user who hand-fixed half of a migration gets a conflict, not a clobbered file.

        The entry is reported once — in `blocked[]`, carrying the operations that did land — so
        the report never claims an entry arrived whole when part of it could not.
        """
        half_fixed = """\
[reporting]
output_config = { directory = "out" }
output = { directory = "mine" }
retention = 30
"""
        ledger = build_ledger(
            entries=[
                build_entry(
                    to_schema_version=2,
                    ops=[
                        MoveKeyOp(table_path=["reporting"], key="retention", new_table_path=["storage"], new_key="retention"),
                        RenameTableKeyOp(table_path=["reporting"], key="output_config", new_key="output"),
                    ],
                )
            ]
        )

        replay = replay_ledger_over_text(ledger=ledger, text=half_fixed)

        assert not replay.steps
        assert len(replay.blocked) == 1
        blocked = replay.blocked[0]
        assert blocked.reason is BlockedEntryReason.CONFLICT
        assert [op.kind for op in blocked.applied_ops] == ["move_key"]
        assert "already present" in blocked.detail

    def test_a_replay_that_applies_nothing_returns_the_very_text_it_was_given(
        self,
        build_entry: EntryBuilder,
        build_ledger: LedgerBuilder,
    ) -> None:
        """Byte-level neutrality is a property of this code, not of the TOML library.

        A run in which every operation skips returns the input string untouched, so no round-trip
        through the serializer can contribute a change of its own.
        """
        ledger = build_ledger(entries=[build_entry(to_schema_version=2, ops=[DeleteKeyOp(table_path=["nowhere"], key="gone")])])

        replay = replay_ledger_over_text(ledger=ledger, text=OLD_SHAPE)

        assert replay.text is OLD_SHAPE

    def test_a_report_never_echoes_a_value_read_from_the_users_file(
        self,
        build_entry: EntryBuilder,
        build_ledger: LedgerBuilder,
    ) -> None:
        secret_bearing = """\
[reporting]
output_config = { directory = "out" }
api_key = "sk-live-DO-NOT-RENDER-THIS"
"""
        ledger = build_ledger(
            entries=[
                build_entry(
                    to_schema_version=2,
                    safety=MigrationSafety.UNSAFE,
                    guidance="Move your reporting settings by hand.",
                    ops=[RenameTableKeyOp(table_path=["reporting"], key="output_config", new_key="output")],
                )
            ]
        )

        replay = replay_ledger_over_text(ledger=ledger, text=secret_bearing)

        # The entry must actually be reported — a report of nothing renders no value trivially.
        assert [blocked.entry_id for blocked in replay.blocked] == ["example-config@2"]
        rendered = replay.model_dump_json(exclude={"text"})
        assert "DO-NOT-RENDER-THIS" not in rendered
