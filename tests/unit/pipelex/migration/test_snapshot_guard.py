"""Unit tests for the head-golden regeneration guard.

The head link is the only one that tracks, which makes it the only one a regeneration can damage.
Run the regenerator after deleting a field and it rewrites `fingerprint@N` with the field gone,
erasing the removal the coverage gate exists to catch — and the gate is then green over a change
that breaks every file carrying it. These tests pin the refusal, its two-sided message, and the
one escape a fingerprint *format* change legitimately needs.
"""

import re
from enum import StrEnum
from pathlib import Path

import pytest
from pydantic import BaseModel, Field

from pipelex.migration.exceptions import MigrationSnapshotRefusedError
from pipelex.migration.goldens import read_fingerprint_golden
from pipelex.migration.ledger import ledgers_dir
from pipelex.migration.snapshot import snapshot_surface
from pipelex.migration.surfaces import DefaultsLayerKind, Surface

SURFACE_ID = "synthetic-config"


class _Tier(StrEnum):
    BASIC = "basic"
    PREMIUM = "premium"


class _TierWithoutBasic(StrEnum):
    PREMIUM = "premium"


class _SchemaOne(BaseModel):
    label: str = "hello"
    tier: _Tier = _Tier.BASIC
    retries: int = Field(default=3, ge=1)


class _LabelGone(BaseModel):
    tier: _Tier = _Tier.BASIC
    retries: int = Field(default=3, ge=1)


class _MemberGone(BaseModel):
    label: str = "hello"
    tier: _TierWithoutBasic = _TierWithoutBasic.PREMIUM
    retries: int = Field(default=3, ge=1)


class _BoundTightened(BaseModel):
    label: str = "hello"
    tier: _Tier = _Tier.BASIC
    retries: int = Field(default=3, ge=2)


class _KeyAdded(BaseModel):
    label: str = "hello"
    tier: _Tier = _Tier.BASIC
    retries: int = Field(default=3, ge=1)
    extra: str = "new"


def _surface(*, config_model: type[BaseModel]) -> Surface:
    return Surface(
        surface_id=SURFACE_ID,
        title="A synthetic configuration surface",
        base_file="synthetic.toml",
        config_model=config_model,
        defaults_layer_kind=DefaultsLayerKind.MODEL_DEFAULTS,
    )


def _write_ledger(*, migration_dir: Path) -> None:
    ledgers = ledgers_dir(migration_dir=migration_dir)
    ledgers.mkdir(parents=True, exist_ok=True)
    (ledgers / f"{SURFACE_ID}.toml").write_text(
        f"""
[surface]
id                         = "{SURFACE_ID}"
title                      = "A synthetic configuration surface"
base_file                  = "synthetic.toml"
current_schema_version     = 1
min_supported_schema_version = 0
""",
        encoding="utf-8",
    )


class TestTheSnapshotGuard:
    def test_the_first_snapshot_of_a_version_is_written(self, tmp_path: Path) -> None:
        """Nothing to erase: writing a link that does not exist is what the gate is asking for."""
        _write_ledger(migration_dir=tmp_path)

        snapshot_surface(surface=_surface(config_model=_SchemaOne), migration_dir=tmp_path)

        stored = read_fingerprint_golden(migration_dir=tmp_path, surface_id=SURFACE_ID, schema_version=1)
        assert stored is not None
        assert "label" in stored.paths

    def test_an_additive_change_re_records_freely(self, tmp_path: Path) -> None:
        """A regeneration that erases nothing is the ordinary case and must stay frictionless."""
        _write_ledger(migration_dir=tmp_path)
        snapshot_surface(surface=_surface(config_model=_SchemaOne), migration_dir=tmp_path)

        snapshot_surface(surface=_surface(config_model=_KeyAdded), migration_dir=tmp_path)

        stored = read_fingerprint_golden(migration_dir=tmp_path, surface_id=SURFACE_ID, schema_version=1)
        assert stored is not None
        assert "extra" in stored.paths

    @pytest.mark.parametrize("config_model", [_LabelGone, _MemberGone, _BoundTightened])
    def test_a_head_golden_recording_lost_material_is_not_overwritten(self, tmp_path: Path, config_model: type[BaseModel]) -> None:
        """A removed path, a retired spelling and a tightened bound all break a file, and all refuse.

        Without the refusal a habitual regeneration is enough to make the coverage gate green over
        any of them — the golden it compares against would already have been rewritten.
        """
        _write_ledger(migration_dir=tmp_path)
        snapshot_surface(surface=_surface(config_model=_SchemaOne), migration_dir=tmp_path)

        with pytest.raises(MigrationSnapshotRefusedError):
            snapshot_surface(surface=_surface(config_model=config_model), migration_dir=tmp_path)

        stored = read_fingerprint_golden(migration_dir=tmp_path, surface_id=SURFACE_ID, schema_version=1)
        assert stored is not None
        assert stored.paths["label"].value_type == "str"
        assert stored.paths["tier"].enum_members == ["basic", "premium"]
        assert stored.paths["retries"].constraints is not None

    def test_the_refusal_names_both_remedies(self, tmp_path: Path) -> None:
        """The diff has two readings and the message must not pick one on the author's behalf."""
        _write_ledger(migration_dir=tmp_path)
        snapshot_surface(surface=_surface(config_model=_SchemaOne), migration_dir=tmp_path)

        with pytest.raises(MigrationSnapshotRefusedError, match=re.escape(f"'{SURFACE_ID}@2'")) as caught:
            snapshot_surface(surface=_surface(config_model=_LabelGone), migration_dir=tmp_path)

        assert "--force" in str(caught.value)

    def test_the_refusal_names_the_remedy_a_narrowing_actually_has(self, tmp_path: Path) -> None:
        """A tightened bound is not repaired by a bump alone, and the message must not imply it is.

        The guard refuses on a narrowing as well as on a removal, but named only the removal's
        remedy — "add the entry accounting for it" — which for a bound an author has just tightened
        reads as though bumping the version were the whole of it. No structural operation can
        repair a value, so the entry has to carry a remap or say `unsafe` and name the path.
        """
        _write_ledger(migration_dir=tmp_path)
        snapshot_surface(surface=_surface(config_model=_SchemaOne), migration_dir=tmp_path)

        with pytest.raises(MigrationSnapshotRefusedError) as caught:
            snapshot_surface(surface=_surface(config_model=_BoundTightened), migration_dir=tmp_path)

        message = str(caught.value)
        assert "accepts fewer values at" in message
        assert "declared_narrowed_paths" in message
        assert "remap_value" in message

    def test_force_re_records_the_head_over_lost_material(self, tmp_path: Path) -> None:
        """The escape a fingerprint *format* change needs, over a schema version nobody has released."""
        _write_ledger(migration_dir=tmp_path)
        snapshot_surface(surface=_surface(config_model=_SchemaOne), migration_dir=tmp_path)

        snapshot_surface(surface=_surface(config_model=_LabelGone), migration_dir=tmp_path, force=True)

        stored = read_fingerprint_golden(migration_dir=tmp_path, surface_id=SURFACE_ID, schema_version=1)
        assert stored is not None
        assert "label" not in stored.paths
