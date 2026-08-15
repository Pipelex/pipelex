"""Unit tests for the ledger models — what a ledger file may say, refused at parse time.

A ledger is permanent data that the engine, the gate and a future human all read as truth, so the
invariants that make it readable are enforced when the file is parsed rather than diagnosed later
by whichever consumer happened to trip over them. The tests below are the inventory of what "the
ledger parses" is actually worth.
"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from pipelex.migration.exceptions import MigrationLedgerError
from pipelex.migration.ledger import MigrationLedger, MigrationSafety, ledgers_dir, load_ledger
from pipelex.suggested_fix import DeleteKeyOp

_SURFACE_BLOCK = {
    "id": "example-config",
    "title": "An example surface",
    "base_file": "example.toml",
    "tier_glob": "example_*.toml",
    "current_schema_version": 1,
    "min_supported_schema_version": 0,
}


def _entry(**overrides: object) -> dict[str, object]:
    entry: dict[str, object] = {
        "id": "example-config@2",
        "to_schema_version": 2,
        "introduced_in": "0.46.0",
        "breaking": True,
        "safety": "safe",
        "title": "Drop a retired key",
        "description": "It is gone.",
        "ops": [{"kind": "delete_key", "table_path": ["reporting"], "key": "legacy"}],
    }
    entry.update(overrides)
    return entry


class TestTheSurfaceBlock:
    def test_a_ledger_with_no_entries_is_valid_at_schema_one(self) -> None:
        """Every surface starts here, and starting empty must not need a placeholder entry."""
        ledger = MigrationLedger.model_validate({"surface": _SURFACE_BLOCK})
        assert ledger.surface.current_schema_version == 1
        assert ledger.migration == []

    def test_a_floor_above_the_current_version_is_refused(self) -> None:
        """The floor exists so a squash fails loudly; above the current version it would fail everything."""
        surface = {**_SURFACE_BLOCK, "min_supported_schema_version": 2}
        with pytest.raises(ValidationError, match="is above current_schema_version"):
            MigrationLedger.model_validate({"surface": surface})

    def test_an_unknown_key_in_the_surface_block_is_refused(self) -> None:
        """A misspelled setting that parses is a setting that silently does nothing."""
        surface = {**_SURFACE_BLOCK, "tier_globs": "example_*.toml"}
        with pytest.raises(ValidationError):
            MigrationLedger.model_validate({"surface": surface})


class TestEntryInvariants:
    def test_a_well_formed_entry_parses_into_typed_operations(self) -> None:
        surface = {**_SURFACE_BLOCK, "current_schema_version": 2}
        ledger = MigrationLedger.model_validate({"surface": surface, "migration": [_entry()]})
        assert ledger.migration[0].safety is MigrationSafety.SAFE
        assert isinstance(ledger.migration[0].ops[0], DeleteKeyOp)

    def test_a_materializing_operation_is_refused_at_parse_time(self) -> None:
        """The migration subset is what makes "a ledger never writes a value" a parse error.

        Writing a default into a user's file converts an inherited value into an explicitly set
        one, and no amount of review discipline catches that as reliably as the type does.
        """
        surface = {**_SURFACE_BLOCK, "current_schema_version": 2}
        entry = _entry(ops=[{"kind": "set_key", "table_path": ["reporting"], "key": "enabled", "value": True}])
        with pytest.raises(ValidationError):
            MigrationLedger.model_validate({"surface": surface, "migration": [entry]})

    def test_an_entry_named_for_the_wrong_version_is_refused(self) -> None:
        surface = {**_SURFACE_BLOCK, "current_schema_version": 2}
        entry = _entry(id="example-config@3")
        with pytest.raises(ValidationError, match="must be named 'example-config@2'"):
            MigrationLedger.model_validate({"surface": surface, "migration": [entry]})

    def test_a_gap_in_the_versions_is_refused(self) -> None:
        """Entries compose in sequence, so a missing version means a file from before it lands nowhere."""
        surface = {**_SURFACE_BLOCK, "current_schema_version": 3}
        entry = _entry(id="example-config@3", to_schema_version=3)
        with pytest.raises(ValidationError, match="expected an entry for schema version 2"):
            MigrationLedger.model_validate({"surface": surface, "migration": [entry]})

    def test_a_bump_with_no_entry_to_explain_it_is_refused(self) -> None:
        surface = {**_SURFACE_BLOCK, "current_schema_version": 2}
        with pytest.raises(ValidationError, match="needs the entry that produced it"):
            MigrationLedger.model_validate({"surface": surface, "migration": []})

    def test_an_entry_with_no_operations_must_be_unsafe(self) -> None:
        """`safe` means the applier acts; with nothing to do there is nothing to act on."""
        surface = {**_SURFACE_BLOCK, "current_schema_version": 2}
        with pytest.raises(ValidationError, match="cannot be 'safe'"):
            MigrationLedger.model_validate({"surface": surface, "migration": [_entry(ops=[])]})

    def test_an_op_free_entry_is_legitimate_when_unsafe(self) -> None:
        """A change only a human can make is still a change the ledger should record."""
        surface = {**_SURFACE_BLOCK, "current_schema_version": 2}
        ledger = MigrationLedger.model_validate({"surface": surface, "migration": [_entry(ops=[], safety="unsafe")]})
        assert ledger.migration[0].ops == []

    def test_declared_removed_paths_belong_to_a_pre_history_entry(self) -> None:
        """An entry with an observable diff is accounted against that diff, never its own claim."""
        surface = {**_SURFACE_BLOCK, "current_schema_version": 2}
        entry = _entry(declared_removed_paths=["reporting.legacy"])
        with pytest.raises(ValidationError, match="pre-history entries only"):
            MigrationLedger.model_validate({"surface": surface, "migration": [entry]})

    def test_nothing_migrates_to_schema_version_one(self) -> None:
        """Version 1 is the shape a surface starts at; there is no earlier shape to come from."""
        surface = {**_SURFACE_BLOCK, "current_schema_version": 1}
        entry = _entry(id="example-config@1", to_schema_version=1)
        with pytest.raises(ValidationError):
            MigrationLedger.model_validate({"surface": surface, "migration": [entry]})


class TestLoadingFromDisk:
    def test_a_missing_ledger_names_the_surface_and_the_path(self, tmp_path: Path) -> None:
        with pytest.raises(MigrationLedgerError, match="no ledger for surface 'absent-config'"):
            load_ledger(migration_dir=tmp_path, surface_id="absent-config")

    def test_an_inconsistent_ledger_fails_the_load_rather_than_a_later_consumer(self, tmp_path: Path) -> None:
        directory = ledgers_dir(migration_dir=tmp_path)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "broken-config.toml").write_text(
            """
[surface]
id                           = "broken-config"
title                        = "Broken"
base_file                    = "broken.toml"
current_schema_version       = 4
min_supported_schema_version = 0
""",
            encoding="utf-8",
        )
        with pytest.raises(MigrationLedgerError, match="invalid ledger for surface 'broken-config'"):
            load_ledger(migration_dir=tmp_path, surface_id="broken-config")

    def test_a_ledger_that_is_not_toml_fails_as_a_ledger_error_not_a_parser_traceback(self, tmp_path: Path) -> None:
        directory = ledgers_dir(migration_dir=tmp_path)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "garbled-config.toml").write_text("[surface\nid = = 'nope'\n", encoding="utf-8")
        with pytest.raises(MigrationLedgerError, match="unparseable ledger for surface 'garbled-config'"):
            load_ledger(migration_dir=tmp_path, surface_id="garbled-config")
