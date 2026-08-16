"""What an `unsafe` entry promises — the one guarantee the engine owes a user it cannot help.

The promise, in one sentence: an `unsafe` entry is reported on every run, to every file that still
carries the material it is about, and to no other file. Two defects broke it in opposite
directions, and both are pinned here.

- **An entry with no operations was reported to nobody, ever** (R9). The engine decided whether to
  report an `unsafe` entry by rehearsing its operations, so the contract's own form for "a change
  only a human can make" — the only remedy the coverage gate offers for a tightened bound — was
  accepted by the accounting and then guaranteed never to reach anyone. Such an entry now declares
  the paths whose value domain narrowed, and the declaration is what gets questioned.
- **An entry went silent as soon as a later `safe` entry renamed its target.** `unsafe@2` is about
  `[reporting] mode`; `safe@3` renames `reporting` to `output`. Run 1 reported the entry and then
  applied the rename; run 2 found no `reporting.mode`, said nothing, and left a file whose boot
  still fails. The material is now traced forward through every later `safe` entry, so the same
  file is reported on every run for as long as it carries it.

Silence is tested as carefully as reporting: the reason `unsafe` entries are questioned at all is
that reporting one unconditionally warns every user with a perfectly current file, at every boot,
forever.
"""

from pipelex.migration.engine import replay_ledger_over_text
from pipelex.migration.ledger import MigrationLedger
from pipelex.migration.material import declared_path_spellings, unsafe_op_variants
from pipelex.migration.plan import BlockedEntryReason
from pipelex.migration.safety import MigrationSafety
from pipelex.suggested_fix import DeleteTableOp, RemapValueOp, RenameTableKeyOp
from tests.unit.pipelex.migration.conftest import EntryBuilder, LedgerBuilder

FILE_SETTING_RETRIES = """\
[reporting]
retries = 40
"""

FILE_NOT_SETTING_RETRIES = """\
[reporting]
directory = "out"
"""

FILE_WITH_A_STALE_MODE = """\
[reporting]
mode = "legacy"
"""

FILE_WITH_A_STALE_MODE_UNDER_THE_NEW_NAME = """\
[output]
mode = "legacy"
"""

FILE_WITH_USER_KEYS_UNDER_AN_OPEN_MAPPING = """\
[levels]
my_package = "verbose"
"""


class TestWhatAnUnsafeEntryPromises:
    def test_an_op_free_entry_is_reported_to_a_file_that_sets_a_declared_path(
        self,
        build_entry: EntryBuilder,
        build_ledger: LedgerBuilder,
    ) -> None:
        """R9 — the declaration is the predicate, because there is nothing to rehearse."""
        entry = build_entry(
            to_schema_version=2,
            ops=[],
            safety=MigrationSafety.UNSAFE,
            guidance="`retries` now tops out at 6.",
            declared_narrowed_paths=["reporting.retries"],
        )
        ledger = build_ledger(entries=[entry])

        replay = replay_ledger_over_text(ledger=ledger, text=FILE_SETTING_RETRIES)

        assert [blocked.entry_id for blocked in replay.blocked] == ["example-config@2"]
        assert replay.blocked[0].reason is BlockedEntryReason.VALUE_DOMAIN_NARROWED
        assert replay.blocked[0].narrowed_paths == ["reporting.retries"]
        assert replay.blocked[0].guidance == "`retries` now tops out at 6."
        assert replay.text is FILE_SETTING_RETRIES

    def test_an_op_free_entry_stays_silent_on_a_file_that_never_sets_the_declared_path(
        self,
        build_entry: EntryBuilder,
        build_ledger: LedgerBuilder,
    ) -> None:
        """The whole reason an entry is questioned: a user who never set the key is not warned."""
        entry = build_entry(
            to_schema_version=2,
            ops=[],
            safety=MigrationSafety.UNSAFE,
            declared_narrowed_paths=["reporting.retries"],
        )
        ledger = build_ledger(entries=[entry])

        replay = replay_ledger_over_text(ledger=ledger, text=FILE_NOT_SETTING_RETRIES)

        assert replay.blocked == []
        assert replay.steps == []
        assert replay.text is FILE_NOT_SETTING_RETRIES

    def test_a_declaration_beneath_an_open_mapping_matches_the_users_own_key(
        self,
        build_entry: EntryBuilder,
        build_ledger: LedgerBuilder,
    ) -> None:
        """A schema path is not a document path: the schema says `levels.*`, the file says `levels.my_package`."""
        entry = build_entry(
            to_schema_version=2,
            ops=[],
            safety=MigrationSafety.UNSAFE,
            declared_narrowed_paths=["levels.*"],
        )
        ledger = build_ledger(entries=[entry])

        replay = replay_ledger_over_text(ledger=ledger, text=FILE_WITH_USER_KEYS_UNDER_AN_OPEN_MAPPING)

        assert [blocked.entry_id for blocked in replay.blocked] == ["example-config@2"]
        assert replay.blocked[0].narrowed_paths == ["levels.*"], "the ledger's spelling is reported, never the user's own key"
        assert "my_package" not in replay.blocked[0].detail

    def test_a_declaration_beneath_an_open_mapping_stays_silent_on_an_empty_one(
        self,
        build_entry: EntryBuilder,
        build_ledger: LedgerBuilder,
    ) -> None:
        """`*` is one key of an open node, never the node itself — a user with no entries set is not warned."""
        entry = build_entry(
            to_schema_version=2,
            ops=[],
            safety=MigrationSafety.UNSAFE,
            declared_narrowed_paths=["levels.*"],
        )
        ledger = build_ledger(entries=[entry])

        assert replay_ledger_over_text(ledger=ledger, text="[levels]\n").blocked == []

    def test_the_old_shape_is_reported_and_the_later_rename_still_applies(
        self,
        build_entry: EntryBuilder,
        build_ledger: LedgerBuilder,
    ) -> None:
        """Run 1, unchanged behaviour: the entry speaks at its own spelling, the later entry works."""
        ledger = _ledger_with_an_unsafe_remap_then_a_rename(build_entry=build_entry, build_ledger=build_ledger)

        replay = replay_ledger_over_text(ledger=ledger, text=FILE_WITH_A_STALE_MODE)

        assert [blocked.entry_id for blocked in replay.blocked] == ["example-config@2"]
        assert [step.entry_id for step in replay.steps] == ["example-config@3"]
        assert "[output]" in replay.text

    def test_the_migrated_shape_is_still_reported_on_every_later_run(
        self,
        build_entry: EntryBuilder,
        build_ledger: LedgerBuilder,
    ) -> None:
        """Run 2 and every run after it. Before the forward trace this was clean while boot failed."""
        ledger = _ledger_with_an_unsafe_remap_then_a_rename(build_entry=build_entry, build_ledger=build_ledger)

        replay = replay_ledger_over_text(ledger=ledger, text=FILE_WITH_A_STALE_MODE_UNDER_THE_NEW_NAME)

        assert [blocked.entry_id for blocked in replay.blocked] == ["example-config@2"]
        assert replay.text is FILE_WITH_A_STALE_MODE_UNDER_THE_NEW_NAME

    def test_a_current_value_under_the_new_name_says_nothing(
        self,
        build_entry: EntryBuilder,
        build_ledger: LedgerBuilder,
    ) -> None:
        """The forward trace must not cost the silence: the remap is still about a stale spelling."""
        ledger = _ledger_with_an_unsafe_remap_then_a_rename(build_entry=build_entry, build_ledger=build_ledger)

        replay = replay_ledger_over_text(ledger=ledger, text='[output]\nmode = "classic"\n')

        assert replay.blocked == []
        assert replay.steps == []

    def test_a_declared_path_is_traced_forward_too(
        self,
        build_entry: EntryBuilder,
        build_ledger: LedgerBuilder,
    ) -> None:
        """The op-free shape meets the same rename, and the declaration follows the material."""
        ledger = build_ledger(
            entries=[
                build_entry(
                    to_schema_version=2,
                    ops=[],
                    safety=MigrationSafety.UNSAFE,
                    declared_narrowed_paths=["reporting.retries"],
                ),
                build_entry(to_schema_version=3, ops=[RenameTableKeyOp(table_path=[], key="reporting", new_key="output")]),
            ]
        )

        replay = replay_ledger_over_text(ledger=ledger, text="[output]\nretries = 40\n")

        assert [blocked.entry_id for blocked in replay.blocked] == ["example-config@2"]

    def test_a_declared_path_is_named_as_the_file_this_run_writes_spells_it(
        self,
        build_entry: EntryBuilder,
        build_ledger: LedgerBuilder,
    ) -> None:
        """The user is sent to check the file the run *wrote*, so that is the spelling to name.

        The entry is questioned against the text as it stands when the replay reaches it, and the
        later `safe` entries of the same replay then rename the material out from under it. Naming
        the spelling that matched sends the user looking for a key the migrated file no longer has.
        """
        ledger = build_ledger(
            entries=[
                build_entry(
                    to_schema_version=2,
                    ops=[],
                    safety=MigrationSafety.UNSAFE,
                    declared_narrowed_paths=["reporting.retries"],
                ),
                build_entry(to_schema_version=3, ops=[RenameTableKeyOp(table_path=[], key="reporting", new_key="output")]),
            ]
        )

        replay = replay_ledger_over_text(ledger=ledger, text=FILE_SETTING_RETRIES)

        assert "[output]" in replay.text, "the rename applied, so the file no longer spells it `reporting`"
        assert replay.blocked[0].narrowed_paths == ["output.retries"]
        assert "output.retries" in replay.blocked[0].detail
        assert "reporting.retries" not in replay.blocked[0].detail

    def test_material_a_later_entry_retires_leaves_nothing_to_say_to_a_file_migrated_that_far(
        self,
        build_entry: EntryBuilder,
        build_ledger: LedgerBuilder,
    ) -> None:
        """Tracing forward follows material, and stops where the material stops.

        A file migrated past the deletion no longer carries anything the entry is about, and
        warning it about a section it no longer has would be the crying wolf the questioning
        exists to prevent. A file that still carries the old shape is still reported.
        """
        ledger = build_ledger(
            entries=[
                build_entry(
                    to_schema_version=2,
                    ops=[],
                    safety=MigrationSafety.UNSAFE,
                    declared_narrowed_paths=["reporting.retries"],
                ),
                build_entry(to_schema_version=3, ops=[DeleteTableOp(table_path=["reporting"])]),
            ]
        )

        assert replay_ledger_over_text(ledger=ledger, text='[storage]\ndirectory = "out"\n').blocked == []
        assert [blocked.entry_id for blocked in replay_ledger_over_text(ledger=ledger, text=FILE_SETTING_RETRIES).blocked] == ["example-config@2"]

    def test_an_ordinary_ledger_has_exactly_one_spelling_to_rehearse(
        self,
        build_entry: EntryBuilder,
        build_ledger: LedgerBuilder,
    ) -> None:
        """The common case costs nothing: no later entry moves this entry's material."""
        entry = build_entry(
            to_schema_version=2,
            ops=[RemapValueOp(table_path=["reporting"], key="mode", mapping={"legacy": "classic"})],
            safety=MigrationSafety.UNSAFE,
        )
        ledger = build_ledger(entries=[entry, build_entry(to_schema_version=3, ops=[DeleteTableOp(table_path=["archive"])])])

        assert unsafe_op_variants(ledger=ledger, entry=entry) == [entry.ops]

    def test_a_later_unsafe_entry_moves_nothing_because_it_is_never_applied(
        self,
        build_entry: EntryBuilder,
        build_ledger: LedgerBuilder,
    ) -> None:
        """Only an entry that is *applied* can give material a new spelling."""
        entry = build_entry(
            to_schema_version=2,
            ops=[],
            safety=MigrationSafety.UNSAFE,
            declared_narrowed_paths=["reporting.retries"],
        )
        ledger = build_ledger(
            entries=[
                entry,
                build_entry(
                    to_schema_version=3,
                    ops=[RenameTableKeyOp(table_path=[], key="reporting", new_key="output")],
                    safety=MigrationSafety.UNSAFE,
                ),
            ]
        )

        assert declared_path_spellings(ledger=ledger, entry=entry) == ["reporting.retries"]

    def test_a_declaration_is_traced_back_through_the_entrys_own_operations(
        self,
        build_entry: EntryBuilder,
        build_ledger: LedgerBuilder,
    ) -> None:
        """The declaration is spelled at the entry's own version, and the entry never applies.

        So a file the entry blocks keeps the previous version's spelling, and questioning only the
        post-entry one would find nothing in the very files the entry exists for.
        """
        entry = build_entry(
            to_schema_version=2,
            ops=[RenameTableKeyOp(table_path=[], key="reporting", new_key="output")],
            safety=MigrationSafety.UNSAFE,
            declared_narrowed_paths=["output.retries"],
        )
        ledger = build_ledger(entries=[entry])

        assert declared_path_spellings(ledger=ledger, entry=entry) == ["output.retries", "reporting.retries"]


def _ledger_with_an_unsafe_remap_then_a_rename(*, build_entry: EntryBuilder, build_ledger: LedgerBuilder) -> MigrationLedger:
    """`unsafe@2` is about `reporting.mode`; `safe@3` renames the table it sits in."""
    return build_ledger(
        entries=[
            build_entry(
                to_schema_version=2,
                ops=[RemapValueOp(table_path=["reporting"], key="mode", mapping={"legacy": "classic"})],
                safety=MigrationSafety.UNSAFE,
            ),
            build_entry(to_schema_version=3, ops=[RenameTableKeyOp(table_path=[], key="reporting", new_key="output")]),
        ]
    )
