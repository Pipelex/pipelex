"""The golden chain — the checked-in snapshots the coverage gate reads and regenerates.

One directory per surface, holding two files per schema version:

    pipelex/migration/goldens/<surface-id>/fingerprint@N.json
    pipelex/migration/goldens/<surface-id>/defaults@N.toml

plus, for a pre-history entry only, the hand-authored document it migrates from:

    pipelex/migration/goldens/<surface-id>/before@N.toml

**The head link tracks; every link below it is frozen.** `update-migration-schemas` rewrites the
snapshot for the surface's *current* version from live sources on every run, and a version bump
simply leaves the previous version's files behind as history. Freezing the head instead would
rot: an additive change absorbed by the defaults layer needs no bump, so a head frozen at the last
bump would drift from the live model and eventually stop validating against it — while the whole
point of the last link is that it is what the current model reads.

There is no separate reserved-path registry file. Every path a schema version removed is
`fingerprint@N-1` minus `fingerprint@N`, so the registry is *derived* from this chain (plus the
declarations of any pre-history entry) rather than stored beside it. A stored copy could disagree
with the chain it summarizes, and the only way to check it would be to recompute it.
"""

import json
from pathlib import Path

from pipelex.migration.exceptions import MigrationGoldenError
from pipelex.migration.fingerprint import SurfaceFingerprint

GOLDENS_DIR_NAME = "goldens"
FINGERPRINT_STEM = "fingerprint"
DEFAULTS_STEM = "defaults"
PRE_HISTORY_STEM = "before"
VERSION_MARKER = "@"


def goldens_dir(*, migration_dir: Path, surface_id: str) -> Path:
    return migration_dir / GOLDENS_DIR_NAME / surface_id


def fingerprint_golden_path(*, migration_dir: Path, surface_id: str, schema_version: int) -> Path:
    return goldens_dir(migration_dir=migration_dir, surface_id=surface_id) / f"{FINGERPRINT_STEM}{VERSION_MARKER}{schema_version}.json"


def defaults_golden_path(*, migration_dir: Path, surface_id: str, schema_version: int) -> Path:
    return goldens_dir(migration_dir=migration_dir, surface_id=surface_id) / f"{DEFAULTS_STEM}{VERSION_MARKER}{schema_version}.toml"


def pre_history_document_path(*, migration_dir: Path, surface_id: str, schema_version: int) -> Path:
    """The hand-authored document a pre-history entry migrates *from*.

    `before@N.toml` sits beside the chain and is the one file here that is neither snapshotted nor
    regenerated: a change that predates the first fingerprint has no `defaults@N-1` to start from,
    because there was no snapshot yet, so its author writes the old shape down instead. Nothing
    regenerates it — a regenerated one would describe today's models, which is exactly what it is
    not about.
    """
    return goldens_dir(migration_dir=migration_dir, surface_id=surface_id) / f"{PRE_HISTORY_STEM}{VERSION_MARKER}{schema_version}.toml"


def read_fingerprint_golden(*, migration_dir: Path, surface_id: str, schema_version: int) -> SurfaceFingerprint | None:
    """The stored fingerprint for one schema version, or `None` when it has never been snapshotted.

    Raises:
        MigrationGoldenError: the file cannot be read as a fingerprint, or its body describes a
            different surface or schema version than its filename claims — a copied or misnamed
            link must not be compared as the link it stands in for.
    """
    path = fingerprint_golden_path(migration_dir=migration_dir, surface_id=surface_id, schema_version=schema_version)
    if not path.exists():
        return None
    try:
        fingerprint = SurfaceFingerprint.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        msg = f"unreadable fingerprint golden at {path}: {exc}"
        raise MigrationGoldenError(msg) from exc
    if fingerprint.surface_id != surface_id or fingerprint.schema_version != schema_version:
        msg = (
            f"fingerprint golden at {path} describes surface '{fingerprint.surface_id}' at schema version "
            f"{fingerprint.schema_version}, not '{surface_id}' at schema version {schema_version} as its name says"
        )
        raise MigrationGoldenError(msg)
    return fingerprint


def render_fingerprint_golden(*, fingerprint: SurfaceFingerprint) -> str:
    """Serialize a fingerprint for checking in.

    Indented and newline-terminated so that a regeneration produces a diff a reviewer can read
    line by line — the diff *is* the gate's output, and a single-line JSON blob would hide the one
    changed path among two hundred unchanged ones.
    """
    payload = fingerprint.model_dump(mode="json", exclude_none=True)
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def write_fingerprint_golden(*, migration_dir: Path, fingerprint: SurfaceFingerprint) -> Path:
    path = fingerprint_golden_path(
        migration_dir=migration_dir,
        surface_id=fingerprint.surface_id,
        schema_version=fingerprint.schema_version,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_fingerprint_golden(fingerprint=fingerprint), encoding="utf-8")
    return path


def write_defaults_golden(*, migration_dir: Path, surface_id: str, schema_version: int, document: str) -> Path:
    path = defaults_golden_path(migration_dir=migration_dir, surface_id=surface_id, schema_version=schema_version)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(document, encoding="utf-8")
    return path
