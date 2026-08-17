"""What a real migration run is aimed at — the directories, the walk's depth, and the version floor.

`test_runner.py` covers what happens to one file. This module covers the questions that only have
answers once a run is pointed at a real machine: which directories it reaches, how deep it goes,
and which files it refuses before replaying anything over them.
"""

from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from pipelex.migration.ledger import MigrationLedger
from pipelex.migration.plan import FileBlockedReason, MigrationReport
from pipelex.migration.run import config_directories_to_migrate
from pipelex.migration.runner import migrate_file
from pipelex.migration.surfaces import build_config_surface_registry
from pipelex.suggested_fix import RenameTableKeyOp
from pipelex.system.configuration.config_loader import config_manager
from pipelex.system.configuration.config_surface import declared_schema_version
from tests.unit.pipelex.migration.conftest import EntryBuilder, LedgerBuilder, SurfaceBuilder
from tests.unit.pipelex.migration.test_runner import MOMENT

CONFIG_LOADER_CLASS = "pipelex.system.configuration.config_loader.ConfigLoader"


def pretend_config_dirs(mocker: MockerFixture, *, global_dir: Path, project_dir: Path | None) -> None:
    """Put the loader's two directory properties where the test wants them.

    The properties are patched on the class rather than the `config_manager` singleton being
    replaced wholesale, and that is the point: the walk *is* `ConfigLoader.existing_config_dirs`
    (`config_directories_to_migrate` reads it and does nothing else), so a mocked-out loader would
    leave the derivation and its one caller both untested.
    """
    mocker.patch(f"{CONFIG_LOADER_CLASS}.global_config_dir", new_callable=mocker.PropertyMock, return_value=global_dir)
    mocker.patch(f"{CONFIG_LOADER_CLASS}.project_config_dir", new_callable=mocker.PropertyMock, return_value=project_dir)


class TestWhichDirectoriesAreWalked:
    def test_the_global_directory_comes_first_and_the_project_one_second(self, tmp_path: Path, mocker: MockerFixture) -> None:
        global_dir = tmp_path / "home" / ".pipelex"
        project_dir = tmp_path / "project" / ".pipelex"
        global_dir.mkdir(parents=True)
        project_dir.mkdir(parents=True)
        pretend_config_dirs(mocker, global_dir=global_dir, project_dir=project_dir)

        assert config_directories_to_migrate() == [global_dir, project_dir]

    def test_a_machine_with_no_project_directory_is_an_ordinary_machine(self, tmp_path: Path, mocker: MockerFixture) -> None:
        global_dir = tmp_path / "home" / ".pipelex"
        global_dir.mkdir(parents=True)
        pretend_config_dirs(mocker, global_dir=global_dir, project_dir=None)

        assert config_directories_to_migrate() == [global_dir]

    def test_a_global_directory_that_does_not_exist_is_skipped(self, tmp_path: Path, mocker: MockerFixture) -> None:
        pretend_config_dirs(mocker, global_dir=tmp_path / "nowhere" / ".pipelex", project_dir=None)

        assert config_directories_to_migrate() == []

    def test_a_project_rooted_at_the_home_directory_is_walked_once(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Every file would otherwise be migrated twice, and the second pass would back up the first.

        A backup of an already-migrated file is not a backup of anything, and it is the copy the
        pruning rotation would keep.
        """
        shared_dir = tmp_path / ".pipelex"
        shared_dir.mkdir(parents=True)
        pretend_config_dirs(mocker, global_dir=shared_dir, project_dir=shared_dir)

        assert config_directories_to_migrate() == [shared_dir]

    def test_the_walk_is_the_same_set_the_stale_boot_warning_decides_against(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """One derivation, read from both ends.

        `stale_configuration_warning` names `pipelex migrate` only for a file under one of these
        directories. If the walk were derived a second time, a boot could promise a remedy the
        command then declines — which is the defect this delegation exists to make impossible.
        """
        global_dir = tmp_path / "home" / ".pipelex"
        global_dir.mkdir(parents=True)
        pretend_config_dirs(mocker, global_dir=global_dir, project_dir=None)

        assert config_directories_to_migrate() == config_manager.existing_config_dirs


class TestTheWalkIsNotRecursive:
    """A subdirectory of a configuration directory holds a different kind of thing.

    The specimen is real and it is the reason this is pinned rather than assumed:
    `.pipelex/inference/backends/pipelex_gateway.toml` matches the `pipelex-config` tier glob
    `pipelex_*.toml` exactly, and is an inference backend definition rather than a configuration
    surface file. A recursive walk would claim it, replay the main configuration's ledger over it,
    and rewrite it.
    """

    SPECIMEN = Path("inference") / "backends" / "pipelex_gateway.toml"

    def test_the_real_gateway_backend_file_is_not_claimed_where_it_actually_lives(self, tmp_path: Path) -> None:
        specimen = tmp_path / self.SPECIMEN
        specimen.parent.mkdir(parents=True)
        specimen.write_text("", encoding="utf-8")
        (tmp_path / "pipelex.toml").write_text("", encoding="utf-8")

        claimed = build_config_surface_registry().files_by_surface_in_directory(directory=tmp_path)

        assert [path.name for _, path in claimed] == ["pipelex.toml"]

    def test_the_same_file_name_at_the_top_level_is_claimed(self, tmp_path: Path) -> None:
        """The other half of the claim: depth is what saves the specimen, not its name.

        Without this, the test above would still pass if the tier glob stopped matching, and it
        would be proving nothing about recursion at all.
        """
        (tmp_path / self.SPECIMEN.name).write_text("", encoding="utf-8")

        claimed = build_config_surface_registry().files_by_surface_in_directory(directory=tmp_path)

        assert [(surface.surface_id, path.name) for surface, path in claimed] == [("pipelex-config", self.SPECIMEN.name)]


class TestTheSchemaVersionFloor:
    """A file that declares where it stands, against a ledger that says how far back it reaches.

    This is the one thing a replay cannot work out for itself: the applier skips an operation whose
    target is absent and reports success, so a ledger that no longer carries the oldest entries
    would run over a file older than them, change nothing, and call it clean.
    """

    def _stale_file(self, *, tmp_path: Path, declared: int | None) -> Path:
        target = tmp_path / "example.toml"
        header = f"[meta]\nschema_version = {declared}\n\n" if declared is not None else ""
        target.write_text(f"{header}[reporting]\noutput_config = 'out'\n", encoding="utf-8")
        return target

    def _ledger(self, *, build_entry: EntryBuilder, build_ledger: LedgerBuilder, floor: int) -> MigrationLedger:
        return build_ledger(
            entries=[
                build_entry(to_schema_version=2, ops=[RenameTableKeyOp(table_path=["reporting"], key="output_config", new_key="output")]),
                build_entry(to_schema_version=3, ops=[RenameTableKeyOp(table_path=["reporting"], key="output", new_key="destination")]),
            ],
            min_supported_schema_version=floor,
        )

    @pytest.mark.parametrize("declared", [1, 0])
    def test_a_file_declaring_a_version_below_the_floor_is_refused_and_left_alone(
        self,
        declared: int,
        tmp_path: Path,
        build_entry: EntryBuilder,
        build_ledger: LedgerBuilder,
        build_surface: SurfaceBuilder,
    ) -> None:
        target = self._stale_file(tmp_path=tmp_path, declared=declared)
        original = target.read_text(encoding="utf-8")
        ledger = self._ledger(build_entry=build_entry, build_ledger=build_ledger, floor=2)

        plan = migrate_file(surface=build_surface(), ledger=ledger, file_path=target, dry_run=False, moment=MOMENT)

        assert plan.blocked_reason is FileBlockedReason.UNSUPPORTED_SCHEMA_VERSION
        assert plan.blocked_detail is not None
        assert f"declares schema version {declared}" in plan.blocked_detail
        assert not plan.was_written
        assert target.read_text(encoding="utf-8") == original

    def test_a_file_declaring_exactly_the_floor_is_migrated(
        self,
        tmp_path: Path,
        build_entry: EntryBuilder,
        build_ledger: LedgerBuilder,
        build_surface: SurfaceBuilder,
    ) -> None:
        """The floor is the oldest version the ledger still reaches, not the first one it refuses."""
        target = self._stale_file(tmp_path=tmp_path, declared=2)
        ledger = self._ledger(build_entry=build_entry, build_ledger=build_ledger, floor=2)

        plan = migrate_file(surface=build_surface(), ledger=ledger, file_path=target, dry_run=False, moment=MOMENT)

        assert plan.blocked_reason is None
        assert plan.was_written

    def test_a_file_declaring_nothing_is_migrated(
        self,
        tmp_path: Path,
        build_entry: EntryBuilder,
        build_ledger: LedgerBuilder,
        build_surface: SurfaceBuilder,
    ) -> None:
        """Which is every file in the field: nothing writes the reserved key."""
        target = self._stale_file(tmp_path=tmp_path, declared=None)
        ledger = self._ledger(build_entry=build_entry, build_ledger=build_ledger, floor=2)

        plan = migrate_file(surface=build_surface(), ledger=ledger, file_path=target, dry_run=False, moment=MOMENT)

        assert plan.blocked_reason is None
        assert plan.was_written


class TestReadingTheDeclaredSchemaVersion:
    """The reserved key is read exactly as tolerantly as boot strips it, and no more."""

    def test_a_declared_integer_is_read(self) -> None:
        assert declared_schema_version(config_dict={"meta": {"schema_version": 4}}) == 4

    @pytest.mark.parametrize(
        "config_dict",
        [
            {},
            {"meta": {}},
            {"meta": {"other": 1}},
            {"meta": "not a table"},
            {"meta": {"schema_version": "2"}},
            {"meta": {"schema_version": 2.0}},
            {"meta": {"schema_version": True}},
        ],
        ids=["absent", "empty-meta", "other-key", "meta-is-not-a-table", "string", "float", "bool"],
    )
    def test_anything_that_is_not_a_plain_integer_is_no_declaration_at_all(self, config_dict: dict[str, object]) -> None:
        """A malformed declaration boots fine, because the strip removes the key whatever it holds.

        Acting on it here would make migration stricter than the reader the key exists for — and
        `True` is the trap: it is an `int` to Python and never a schema version.
        """
        assert declared_schema_version(config_dict=config_dict) is None


class TestTheDocumentTheDiagnosisReadsIsTheOneTheRunLeaves:
    """A run diagnoses what it is about to leave behind, not what it found.

    The distinction is invisible on a file that needed nothing and is the whole answer on a file
    that did: every stale key the ledger repairs would be reported as unexplained if the diagnosis
    read the document as it arrived.
    """

    def _ledger(self, *, build_entry: EntryBuilder, build_ledger: LedgerBuilder) -> MigrationLedger:
        return build_ledger(
            entries=[build_entry(to_schema_version=2, ops=[RenameTableKeyOp(table_path=["reporting"], key="output_config", new_key="output")])]
        )

    def test_a_key_the_ledger_renames_is_not_reported_as_unexplained(
        self,
        tmp_path: Path,
        build_entry: EntryBuilder,
        build_ledger: LedgerBuilder,
        build_surface: SurfaceBuilder,
    ) -> None:
        target = tmp_path / "example.toml"
        target.write_text('[reporting]\noutput_config = { directory = "out" }\n', encoding="utf-8")

        plan = migrate_file(
            surface=build_surface(),
            ledger=self._ledger(build_entry=build_entry, build_ledger=build_ledger),
            file_path=target,
            dry_run=False,
            moment=MOMENT,
        )

        assert plan.steps, "the scenario is worthless unless the rename actually fired"
        assert plan.unexplained == []

    def test_a_dry_run_diagnoses_the_document_it_would_have_written(
        self,
        tmp_path: Path,
        build_entry: EntryBuilder,
        build_ledger: LedgerBuilder,
        build_surface: SurfaceBuilder,
    ) -> None:
        """The document only exists in memory here, which is why the diagnosis belongs to the run."""
        target = tmp_path / "example.toml"
        target.write_text('[reporting]\noutput_config = { directory = "out" }\nretires = 3\n', encoding="utf-8")

        plan = migrate_file(
            surface=build_surface(),
            ledger=self._ledger(build_entry=build_entry, build_ledger=build_ledger),
            file_path=target,
            dry_run=True,
            moment=MOMENT,
        )

        assert not plan.was_written
        assert [unexplained.path for unexplained in plan.unexplained] == ["reporting.retires"]


class TestADryRunPredictsExactlyWhatAWritePassRewrites:
    """`changed_plans` on a dry run must name the same files `written_plans` names after a write.

    The runner writes a file whenever anything applied to it — a whole entry, or the part of a
    conflicting one that landed before the conflict. A dry run that only counted whole entries
    would tell the interactive command and the doctor there is nothing to run on a file the write
    pass then rewrites.
    """

    def _half_migrated_file(self, *, tmp_path: Path) -> Path:
        """`output_config` moves; `format` finds its destination already taken and blocks the entry."""
        target = tmp_path / "example.toml"
        target.write_text('[reporting]\noutput_config = "out"\nformat = "json"\ndestination_format = "toml"\n', encoding="utf-8")
        return target

    def _ledger(self, *, build_entry: EntryBuilder, build_ledger: LedgerBuilder) -> MigrationLedger:
        return build_ledger(
            entries=[
                build_entry(
                    to_schema_version=2,
                    ops=[
                        RenameTableKeyOp(table_path=["reporting"], key="output_config", new_key="output"),
                        RenameTableKeyOp(table_path=["reporting"], key="format", new_key="destination_format"),
                    ],
                )
            ]
        )

    def test_a_partly_applied_entry_counts_as_a_change_on_both_passes(
        self,
        tmp_path: Path,
        build_entry: EntryBuilder,
        build_ledger: LedgerBuilder,
        build_surface: SurfaceBuilder,
    ) -> None:
        target = self._half_migrated_file(tmp_path=tmp_path)
        ledger = self._ledger(build_entry=build_entry, build_ledger=build_ledger)

        rehearsal = migrate_file(surface=build_surface(), ledger=ledger, file_path=target, dry_run=True, moment=MOMENT)
        assert rehearsal.steps == [], "the scenario is worthless unless the entry actually blocks"
        assert rehearsal.blocked, "…and worthless unless the block is an entry's"
        assert rehearsal.blocked[0].applied_ops, "…and worthless unless part of it applied first"

        dry = MigrationReport(plans=[rehearsal])
        write = MigrationReport(plans=[migrate_file(surface=build_surface(), ledger=ledger, file_path=target, dry_run=False, moment=MOMENT)])

        assert [plan.file_path for plan in write.written_plans] == [target]
        assert [plan.file_path for plan in dry.changed_plans] == [plan.file_path for plan in write.written_plans]
