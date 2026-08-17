"""Unit tests for reading the golden chain — what a stored fingerprint has to be before the gate trusts it.

The chain is checked-in history that the coverage check reads as truth, link by link. A link that
is unreadable, or that describes a different surface or version than its filename claims, must
stop the check with a named error rather than be compared as if it were the link it stands in for.
"""

from pathlib import Path

import pytest
from pydantic import BaseModel

from pipelex.migration.exceptions import MigrationGoldenError
from pipelex.migration.fingerprint import compute_fingerprint
from pipelex.migration.goldens import fingerprint_golden_path, read_fingerprint_golden, write_fingerprint_golden

SURFACE_ID = "synthetic-config"


class _Schema(BaseModel):
    label: str = "hello"


def _fingerprint(*, surface_id: str = SURFACE_ID, schema_version: int = 1):
    return compute_fingerprint(surface_id=surface_id, schema_version=schema_version, config_model=_Schema, defaults_document={})


class TestReadingTheGoldenChain:
    def test_a_written_golden_reads_back_as_itself(self, tmp_path: Path) -> None:
        fingerprint = _fingerprint()
        write_fingerprint_golden(migration_dir=tmp_path, fingerprint=fingerprint)
        assert read_fingerprint_golden(migration_dir=tmp_path, surface_id=SURFACE_ID, schema_version=1) == fingerprint

    def test_a_link_that_was_never_snapshotted_is_none(self, tmp_path: Path) -> None:
        assert read_fingerprint_golden(migration_dir=tmp_path, surface_id=SURFACE_ID, schema_version=1) is None

    def test_a_golden_whose_body_disagrees_with_its_filename_is_refused(self, tmp_path: Path) -> None:
        """A copied or misnamed link would otherwise be compared as the version it stands in for, and pass."""
        path = fingerprint_golden_path(migration_dir=tmp_path, surface_id=SURFACE_ID, schema_version=2)
        path.parent.mkdir(parents=True)
        path.write_text(_fingerprint(schema_version=1).model_dump_json(), encoding="utf-8")
        with pytest.raises(MigrationGoldenError, match="schema version 1"):
            read_fingerprint_golden(migration_dir=tmp_path, surface_id=SURFACE_ID, schema_version=2)

    def test_a_golden_describing_another_surface_is_refused(self, tmp_path: Path) -> None:
        path = fingerprint_golden_path(migration_dir=tmp_path, surface_id=SURFACE_ID, schema_version=1)
        path.parent.mkdir(parents=True)
        path.write_text(_fingerprint(surface_id="other-config").model_dump_json(), encoding="utf-8")
        with pytest.raises(MigrationGoldenError, match="other-config"):
            read_fingerprint_golden(migration_dir=tmp_path, surface_id=SURFACE_ID, schema_version=1)

    def test_a_golden_that_is_not_a_fingerprint_is_refused_by_name(self, tmp_path: Path) -> None:
        path = fingerprint_golden_path(migration_dir=tmp_path, surface_id=SURFACE_ID, schema_version=1)
        path.parent.mkdir(parents=True)
        path.write_text("{not json", encoding="utf-8")
        with pytest.raises(MigrationGoldenError, match="unreadable fingerprint golden"):
            read_fingerprint_golden(migration_dir=tmp_path, surface_id=SURFACE_ID, schema_version=1)

    def test_a_golden_that_cannot_be_read_from_disk_is_refused_by_name(self, tmp_path: Path) -> None:
        """A directory where the file should be: exists, but is not readable as a file."""
        path = fingerprint_golden_path(migration_dir=tmp_path, surface_id=SURFACE_ID, schema_version=1)
        path.mkdir(parents=True)
        with pytest.raises(MigrationGoldenError, match="unreadable fingerprint golden"):
            read_fingerprint_golden(migration_dir=tmp_path, surface_id=SURFACE_ID, schema_version=1)
