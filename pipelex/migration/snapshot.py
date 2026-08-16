"""Regeneration — writing the golden chain that the coverage check reads.

`update-migration-schemas` writes, for each surface, the snapshot of its *current* schema version:
the fingerprint and the complete reference document. Older versions are never rewritten, so a
bump leaves the previous version's files behind as the frozen history the chain is made of.

**The head snapshot is not written blindly.** The head link is the only one that tracks, which
makes it the only one a regeneration can damage: run after deleting a field and it rewrites
`fingerprint@N` with the field gone, erasing the very removal the coverage gate exists to catch —
and the gate is then green over a change that breaks every user's file. So the regenerator reads
the stored head first, and refuses the surface when the models have lost a path, an enumerated
spelling or a slice of a value domain against it. Two situations produce that diff and they have
different remedies, which is why the refusal names both rather than picking one: a real removal
wants a version bump and an entry, and a change to the fingerprint *format* over an unreleased
schema wants the same regeneration under `--force`.

The reference document is the defaults layer verbatim: for a packaged-document surface a byte copy
of the shipped TOML, for a model-defaults surface the document synthesized from the model's own
defaults. Neither carries a generated-by banner, because these files are not reports about a
document — they *are* the document, and a later phase applies migration operations to them.
"""

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from pipelex.migration.coverage import diff_fingerprints
from pipelex.migration.exceptions import MigrationSnapshotRefusedError
from pipelex.migration.fingerprint import SurfaceFingerprint, compute_fingerprint
from pipelex.migration.goldens import read_fingerprint_golden, write_defaults_golden, write_fingerprint_golden
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


def snapshot_surface(*, surface: Surface, migration_dir: Path, force: bool = False) -> SurfaceSnapshot:
    ledger = load_ledger(migration_dir=migration_dir, surface_id=surface.surface_id)
    schema_version = ledger.surface.current_schema_version
    fingerprint = compute_surface_fingerprint(surface=surface, schema_version=schema_version)
    if not force:
        _refuse_a_destructive_head_overwrite(surface=surface, fingerprint=fingerprint, schema_version=schema_version, migration_dir=migration_dir)
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


def _refuse_a_destructive_head_overwrite(
    *,
    surface: Surface,
    fingerprint: SurfaceFingerprint,
    schema_version: int,
    migration_dir: Path,
) -> None:
    """Stop before overwriting a head golden that records material the models no longer have.

    Raises:
        MigrationSnapshotRefusedError: the stored head has a path, an enumerated spelling or a
            value domain the live models lost.
    """
    stored = read_fingerprint_golden(migration_dir=migration_dir, surface_id=surface.surface_id, schema_version=schema_version)
    if stored is None:
        # Nothing to erase: the first snapshot of a version is what the gate is asking for.
        return
    diff = diff_fingerprints(before=stored, after=fingerprint)
    if not diff.has_removals and not diff.narrowed_paths:
        return
    lost: list[str] = []
    if diff.has_removals:
        lost.append(f"it no longer has {diff.render_removals()}")
    if diff.narrowed_paths:
        lost.append(f"it accepts fewer values at {diff.render_narrowings()}")
    msg = (
        f"surface '{surface.surface_id}': refusing to overwrite the golden for schema version {schema_version}, because "
        f"{' and '.join(lost)}. Rewriting the head link here would erase exactly what the coverage gate exists to catch, "
        f"leaving it green over a change that breaks every file carrying that material. If this is a real change, bump "
        f"current_schema_version to {schema_version + 1} and add the entry '{surface.surface_id}@{schema_version + 1}' "
        f"accounting for it — a removal by the operation that removes it, and a narrowing by a remap_value on the path, "
        f"or by marking the entry unsafe and naming the path in declared_narrowed_paths, since no structural operation "
        f"can repair a value. If schema version {schema_version} has not been released and the golden merely predates a "
        f"change to the fingerprint format itself, re-record it with `--force`"
    )
    raise MigrationSnapshotRefusedError(msg)


def snapshot_registry(*, registry: SurfaceRegistry, migration_dir: Path, force: bool = False) -> list[SurfaceSnapshot]:
    return [snapshot_surface(surface=surface, migration_dir=migration_dir, force=force) for surface in registry.surfaces]
