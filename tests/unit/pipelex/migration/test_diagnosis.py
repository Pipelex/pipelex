"""Unit tests for the downgrade diagnosis — what a migration cannot explain about a file.

Everything a ledger explains has been carried forward by the time a replay ends, so what is left
over is either a typo or a key from a newer pipelex. The tests are about the two ways that answer
goes wrong: naming something the report has already accounted for, and rendering a key the user
chose rather than the one the schema does not know.
"""

from typing import Any

import pytest
from pydantic import BaseModel, Field

from pipelex.migration.diagnosis import diagnose_unexplained_paths
from pipelex.migration.fingerprint import SurfaceFingerprint, compute_fingerprint
from pipelex.migration.ledger import MigrationLedger
from pipelex.migration.plan import BlockedEntry, BlockedEntryReason
from pipelex.migration.safety import MigrationSafety
from pipelex.migration.surfaces import DefaultsLayerKind, DocumentShape, Surface
from pipelex.suggested_fix import DeleteKeyOp, MigrationOp, RemapValueOp, RenameTableKeyOp
from tests.unit.pipelex.migration.conftest import EXAMPLE_SURFACE_ID, EntryBuilder, LedgerBuilder


class Output(BaseModel):
    directory: str = "out"


class Reporting(BaseModel):
    output: Output = Field(default_factory=Output)
    retries: int = 1


class Queue(BaseModel):
    retries: int = 1


class Schema(BaseModel):
    label: str = "hello"
    reporting: Reporting = Field(default_factory=Reporting)
    levels: dict[str, str] = Field(default_factory=dict[str, str])
    queues: dict[str, Queue] = Field(default_factory=dict[str, Queue])


class BackendFileNode(BaseModel):
    """One root table of a document whose root keys are the user's — every field optional."""

    sdk: str | None = None
    max_tokens: int | None = None


def _surface(*, config_model: type[BaseModel] = Schema, document_shape: DocumentShape = DocumentShape.WHOLE_DOCUMENT) -> Surface:
    return Surface(
        surface_id=EXAMPLE_SURFACE_ID,
        title="An example configuration surface",
        base_file="example.toml",
        config_model=config_model,
        document_shape=document_shape,
        defaults_layer_kind=DefaultsLayerKind.MODEL_DEFAULTS,
    )


def _fingerprint() -> SurfaceFingerprint:
    return compute_fingerprint(surface_id=EXAMPLE_SURFACE_ID, schema_version=3, config_model=Schema, defaults_document={})


def _diagnose(*, document: dict[str, Any], ledger: MigrationLedger, blocked: list[BlockedEntry] | None = None) -> list[str]:
    found = diagnose_unexplained_paths(
        surface=_surface(),
        fingerprint=_fingerprint(),
        document=document,
        ledger=ledger,
        blocked=blocked or [],
    )
    return [unexplained.path for unexplained in found]


def _diagnose_backend_document(*, document: dict[str, Any], ledger: MigrationLedger) -> list[str]:
    surface = _surface(config_model=BackendFileNode, document_shape=DocumentShape.MODEL_SPEC_TABLES)
    found = diagnose_unexplained_paths(
        surface=surface,
        fingerprint=surface.fingerprint_at(schema_version=1),
        document=document,
        ledger=ledger,
        blocked=[],
    )
    return [unexplained.path for unexplained in found]


def _blocked(*, to_schema_version: int, reason: BlockedEntryReason = BlockedEntryReason.UNSAFE) -> BlockedEntry:
    return BlockedEntry(
        entry_id=f"{EXAMPLE_SURFACE_ID}@{to_schema_version}",
        to_schema_version=to_schema_version,
        reason=reason,
        detail="reported by the engine",
    )


@pytest.fixture
def empty_ledger(build_ledger: LedgerBuilder) -> MigrationLedger:
    return build_ledger(entries=[])


class TestWhatTheSchemaDoesNotKnow:
    def test_a_root_key_no_model_knows_is_reported_with_both_readings(self, empty_ledger: MigrationLedger) -> None:
        found = diagnose_unexplained_paths(
            surface=_surface(),
            fingerprint=_fingerprint(),
            document={"label": "hi", "not_a_real_setting": True},
            ledger=empty_ledger,
            blocked=[],
        )

        assert [unexplained.path for unexplained in found] == ["not_a_real_setting"]
        note = found[0].note
        assert "typo" in note
        assert "newer pipelex" in note, "the downgrade reading is the one nothing else in the report offers"

    def test_a_per_model_request_header_is_not_something_the_schema_cannot_explain(self, empty_ledger: MigrationLedger) -> None:
        """A backend file's headers are legal by *shape*, so they resolve against no recorded path.

        Without this the diagnosis would report `x-portkey-provider` on **every** `pipelex migrate`
        run over a machine that has a portkey backend — the kit's own file carries such keys — and the
        report would be telling the user to fix a key we ship and endorse.
        """
        document = {"defaults": {"sdk": "openai"}, "gpt-4o": {"max_tokens": 1, "x-portkey-provider": "openai"}}

        assert _diagnose_backend_document(document=document, ledger=empty_ledger) == []

    def test_the_same_header_inside_defaults_is_reported_because_the_loader_refuses_it_there(self, empty_ledger: MigrationLedger) -> None:
        """`[defaults]` and a model table are one node to the fingerprint and two to the loader.

        A model table goes through `split_model_spec_keys`, so a header on it is legal. `[defaults]`
        is copied into every model of the file **unsplit**, so the same key there is
        `extra_forbidden` on all of them and the file does not boot. Admitting it would report the
        one file that cannot start as the one file with nothing to explain — and on the command the
        boot error sends that reader to for the diagnosis.
        """
        document = {"defaults": {"sdk": "openai", "x-portkey-provider": "openai"}, "gpt-4o": {"max_tokens": 1}}

        assert _diagnose_backend_document(document=document, ledger=empty_ledger) == ["*.x-portkey-provider"]

    def test_a_typo_inside_a_model_table_is_still_reported_at_the_wildcard(self, empty_ledger: MigrationLedger) -> None:
        """The other half: the admission is by shape, not by "the model allows extras".

        `promting_target` carries no hyphen, so it is a typo or a dead field rather than a header —
        exactly the key class this surface exists to explain — and it is reported at the spelling the
        schema uses, with the model name the user chose left out of it.
        """
        document = {"defaults": {"sdk": "openai"}, "gpt-4o": {"promting_target": "openai"}}

        assert _diagnose_backend_document(document=document, ledger=empty_ledger) == ["*.promting_target"]

    def test_a_document_the_schema_knows_entirely_is_reported_clean(self, empty_ledger: MigrationLedger) -> None:
        document = {"label": "hi", "reporting": {"output": {"directory": "elsewhere"}, "retries": 3}}

        assert _diagnose(document=document, ledger=empty_ledger) == []

    def test_an_unknown_key_inside_a_known_table_is_reported_at_its_full_path(self, empty_ledger: MigrationLedger) -> None:
        document = {"reporting": {"retires": 3}}

        assert _diagnose(document=document, ledger=empty_ledger) == ["reporting.retires"]

    def test_an_unknown_table_is_reported_once_rather_than_once_per_key_inside_it(self, empty_ledger: MigrationLedger) -> None:
        """The shallowest name is the one the user has to fix; listing the subtree buries it."""
        document = {"reportng": {"output": {"directory": "out"}, "retries": 3}}

        assert _diagnose(document=document, ledger=empty_ledger) == ["reportng"]

    def test_a_table_where_the_schema_wants_a_scalar_is_left_to_the_model(self, empty_ledger: MigrationLedger) -> None:
        """A type error, not a downgrade. Descending would invent unknown paths under a known one."""
        document = {"reporting": {"retries": {"how_many": 3}}}

        assert _diagnose(document=document, ledger=empty_ledger) == []


class TestKeysTheUserChose:
    """A key beneath an open mapping belongs to the user, and is no more rendered than a value."""

    def test_a_users_own_key_beneath_an_open_mapping_is_not_reported(self, empty_ledger: MigrationLedger) -> None:
        document = {"levels": {"my_private_package": "INFO"}}

        assert _diagnose(document=document, ledger=empty_ledger) == []

    def test_a_typo_inside_an_open_mappings_value_is_reported_as_the_schema_spells_it(self, empty_ledger: MigrationLedger) -> None:
        document = {"queues": {"my_private_queue": {"retreis": 2}}}

        found = _diagnose(document=document, ledger=empty_ledger)

        assert found == ["queues.*.retreis"]
        assert "my_private_queue" not in found[0], "the user's own key is not the thing the schema does not know"

    def test_nesting_below_an_open_mappings_scalar_value_is_left_to_the_model(self, empty_ledger: MigrationLedger) -> None:
        document = {"levels": {"my_private_package": {"level": "INFO"}}}

        assert _diagnose(document=document, ledger=empty_ledger) == []


class TestTheReservedMetaTable:
    def test_the_reserved_schema_version_is_not_reported(self, empty_ledger: MigrationLedger) -> None:
        """Boot tolerates the key, so a migration must not tell the user it is a typo."""
        document = {"meta": {"schema_version": 2}, "label": "hi"}

        assert _diagnose(document=document, ledger=empty_ledger) == []
        assert document == {"meta": {"schema_version": 2}, "label": "hi"}, "a diagnosis reads; it does not edit what it was handed"

    def test_a_meta_table_carrying_anything_else_is_reported(self, empty_ledger: MigrationLedger) -> None:
        """Only that one key is reserved, and what is left over is a table no schema knows.

        Reported as `meta` rather than `meta.author`, which is the shallowest-unknown rule and also
        what the boot says: no configuration model has a `meta` field, so `extra="forbid"` rejects
        the table and not the key inside it.
        """
        document = {"meta": {"schema_version": 2, "author": "someone"}}

        assert _diagnose(document=document, ledger=empty_ledger) == ["meta"]


class TestWhatABlockedEntryAnswersFor:
    """An entry the run would not apply is the *reason* its material is still in the file."""

    def _ledger_with_a_blocking_entry(self, *, build_entry: EntryBuilder, build_ledger: LedgerBuilder, ops: list[MigrationOp]) -> MigrationLedger:
        return build_ledger(entries=[build_entry(to_schema_version=2, safety=MigrationSafety.UNSAFE, ops=ops)])

    def test_the_old_shape_a_blocked_entry_is_about_is_not_also_called_unexplained(
        self,
        build_entry: EntryBuilder,
        build_ledger: LedgerBuilder,
    ) -> None:
        ledger = self._ledger_with_a_blocking_entry(
            build_entry=build_entry,
            build_ledger=build_ledger,
            ops=[DeleteKeyOp(table_path=["reporting"], key="legacy_mode")],
        )

        assert _diagnose(document={"reporting": {"legacy_mode": "on"}}, ledger=ledger, blocked=[_blocked(to_schema_version=2)]) == []

    def test_the_same_path_is_reported_when_no_entry_is_blocked(
        self,
        build_entry: EntryBuilder,
        build_ledger: LedgerBuilder,
    ) -> None:
        """The other half of the pair: the subtraction is the blocked entry's, not the ledger's."""
        ledger = self._ledger_with_a_blocking_entry(
            build_entry=build_entry,
            build_ledger=build_ledger,
            ops=[DeleteKeyOp(table_path=["reporting"], key="legacy_mode")],
        )

        assert _diagnose(document={"reporting": {"legacy_mode": "on"}}, ledger=ledger, blocked=[]) == ["reporting.legacy_mode"]

    def test_a_blocked_entry_answers_for_the_whole_subtree_it_would_have_taken(
        self,
        build_entry: EntryBuilder,
        build_ledger: LedgerBuilder,
    ) -> None:
        ledger = self._ledger_with_a_blocking_entry(
            build_entry=build_entry,
            build_ledger=build_ledger,
            ops=[DeleteKeyOp(table_path=[], key="legacy")],
        )
        document = {"legacy": {"mode": "on", "nested": {"deeper": 1}}}

        assert _diagnose(document=document, ledger=ledger, blocked=[_blocked(to_schema_version=2)]) == []

    def test_a_blocked_entry_answers_for_the_material_at_the_spelling_later_entries_gave_it(
        self,
        build_entry: EntryBuilder,
        build_ledger: LedgerBuilder,
    ) -> None:
        """A later `safe` entry renames the table around a blocked one, and the file follows it."""
        ledger = build_ledger(
            entries=[
                build_entry(to_schema_version=2, safety=MigrationSafety.UNSAFE, ops=[DeleteKeyOp(table_path=["old_report"], key="legacy_mode")]),
                build_entry(to_schema_version=3, ops=[RenameTableKeyOp(table_path=[], key="old_report", new_key="reporting")]),
            ]
        )

        assert _diagnose(document={"reporting": {"legacy_mode": "on"}}, ledger=ledger, blocked=[_blocked(to_schema_version=2)]) == []

    def test_a_blocked_entry_answers_for_what_it_declares_removed(
        self,
        build_entry: EntryBuilder,
        build_ledger: LedgerBuilder,
    ) -> None:
        """A pre-history entry has no fingerprint pair behind it, so its declaration is the record.

        The declared path here is one no operation addresses, which is what makes the declaration
        the only thing that can account for it.
        """
        ledger = build_ledger(
            entries=[
                build_entry(
                    to_schema_version=2,
                    safety=MigrationSafety.UNSAFE,
                    pre_history=True,
                    declared_removed_paths=["reporting.legacy_mode", "reporting.other_thing"],
                    ops=[DeleteKeyOp(table_path=["reporting"], key="other_thing")],
                )
            ]
        )

        assert _diagnose(document={"reporting": {"legacy_mode": "on"}}, ledger=ledger, blocked=[_blocked(to_schema_version=2)]) == []

    def test_a_blocked_remap_answers_for_nothing(
        self,
        build_entry: EntryBuilder,
        build_ledger: LedgerBuilder,
    ) -> None:
        """A remap moves a value and leaves the path where it was, so it explains no unknown path.

        Subtracting it would silence a genuine typo that happens to sit at a remapped key.
        """
        ledger = self._ledger_with_a_blocking_entry(
            build_entry=build_entry,
            build_ledger=build_ledger,
            ops=[RemapValueOp(table_path=["reporting"], key="mode", mapping={"old": "new"})],
        )

        assert _diagnose(document={"reporting": {"mode": "old"}}, ledger=ledger, blocked=[_blocked(to_schema_version=2)]) == ["reporting.mode"]

    def test_an_unrelated_typo_survives_a_blocked_entry(
        self,
        build_entry: EntryBuilder,
        build_ledger: LedgerBuilder,
    ) -> None:
        ledger = self._ledger_with_a_blocking_entry(
            build_entry=build_entry,
            build_ledger=build_ledger,
            ops=[DeleteKeyOp(table_path=["reporting"], key="legacy_mode")],
        )
        document = {"reporting": {"legacy_mode": "on", "retires": 3}}

        assert _diagnose(document=document, ledger=ledger, blocked=[_blocked(to_schema_version=2)]) == ["reporting.retires"]
