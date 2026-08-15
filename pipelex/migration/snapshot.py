"""Regeneration — writing the golden chain that the coverage check reads.

`update-migration-schemas` writes, for each surface, the snapshot of its *current* schema version:
the fingerprint and the complete reference document. Older versions are never rewritten, so a
bump leaves the previous version's files behind as the frozen history the chain is made of.

The reference document is the defaults layer verbatim: for a packaged-document surface a byte copy
of the shipped TOML, for a model-defaults surface the document synthesized from the model's own
defaults. Neither carries a generated-by banner, because these files are not reports about a
document — they *are* the document, and a later phase applies migration operations to them.
"""

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from pipelex.migration.fingerprint import SurfaceFingerprint, compute_fingerprint
from pipelex.migration.goldens import write_defaults_golden, write_fingerprint_golden
from pipelex.migration.ledger import load_ledger
from pipelex.migration.surfaces import Surface, SurfaceRegistry


class SurfaceSnapshot(BaseModel):
    """Where one surface's regeneration landed, for reporting."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    surface_id: str
    schema_version: int
    fingerprint_path: Path
    defaults_path: Path
    path_count: int


def snapshot_surface(*, surface: Surface, migration_dir: Path) -> SurfaceSnapshot:
    ledger = load_ledger(migration_dir=migration_dir, surface_id=surface.surface_id)
    schema_version = ledger.surface.current_schema_version
    fingerprint = compute_surface_fingerprint(surface=surface, schema_version=schema_version)
    fingerprint_path = write_fingerprint_golden(migration_dir=migration_dir, fingerprint=fingerprint)
    defaults_path = write_defaults_golden(
        migration_dir=migration_dir,
        surface_id=surface.surface_id,
        schema_version=schema_version,
        document=surface.render_reference_document(),
    )
    return SurfaceSnapshot(
        surface_id=surface.surface_id,
        schema_version=schema_version,
        fingerprint_path=fingerprint_path,
        defaults_path=defaults_path,
        path_count=len(fingerprint.paths),
    )


def compute_surface_fingerprint(*, surface: Surface, schema_version: int) -> SurfaceFingerprint:
    return compute_fingerprint(
        surface_id=surface.surface_id,
        schema_version=schema_version,
        config_model=surface.config_model,
        defaults_document=surface.read_defaults_document(),
    )


def snapshot_registry(*, registry: SurfaceRegistry, migration_dir: Path) -> list[SurfaceSnapshot]:
    return [snapshot_surface(surface=surface, migration_dir=migration_dir) for surface in registry.surfaces]
