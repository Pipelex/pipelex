"""The transform goldens — do an entry's operations really say what the schema change did?

Coverage proves an entry *exists* for every removal. Convergence proves replay is *harmless* on a
current file. Neither proves the entry is *right*: a rename whose `new_key` is misspelled passes
both — the removed path is accounted for, and over a current document the source is absent so the
operation skips — and then migrates every user file to a key `extra="forbid"` rejects, with the
tool reporting success. This check closes that, by doing the migration for real on the one pair of
documents the golden chain keeps for it: the reference document of schema version N-1 and the one
of N, with entry N in between.

Three claims per link, and every one of them is one-directional on purpose — a comparator that
demands the two documents agree outright goes red on any honest bump, where the same commit adds
keys, edits comments and flips unrelated defaults:

- **Every path the migration creates, the new reference document has.** This is the wrong
  destination, the misordered rename and the operation that lands in a table the new shape does
  not carry. A created path whose *container* is gone from the new document is exempt: when a whole
  entry of an open mapping was dropped from the reference document between versions, nothing can
  be said about what an operation did inside it.
- **Every path the two reference documents share survives the migration.** This is over-deletion —
  an entry that dropped a parent table where it meant to drop one child. A path the new shape no
  longer has is not this check's business: the schema removed it, and coverage is what demands the
  operation that accounts for it.
- **The last link's migrated document is accepted by the current model**, read the way a user's
  file is actually read: beneath the current defaults layer. This is where a wrong value lands —
  a remap rewriting to a spelling the schema rejects, a destination the model does not know.

Two departures from the contract's first wording, both recorded in `docs/migration-ledger.md`:

**`paths(defaults@N)` minus `added_at_N` is not the comparator.** A raw fingerprint difference counts a
rename's *destination* as an addition, so subtracting it would demand the destination be absent
from the expected shape — exactly where a correct rename puts it. That is the same defect the
symbolic end-state check met and answered with containment; the answer here is the same, expressed
over documents: additions are tolerated because nothing asserts them, rather than subtracted.
Tolerating them by subtraction would also be blind by construction to everything a fingerprint
cannot see — a model added to a packaged deck between versions lives beneath an open node, where
the fingerprint records a value schema and never a key.

**Value equality against `defaults@N` is unsound and is not asserted.** A default flipped in the
same commit as a rename would make the check red with no remedy available to anyone: the older
link is frozen, the head link tracks, and a migrated file legitimately carries the user's old
value where the new reference document carries the new default. What the contract wanted from it —
*the operations produce values the new schema accepts* — is checked where it can be checked
soundly: by the last link's validation here, and by `check-ledger`'s remap legality, which refuses
a remap whose target spelling the new schema does not accept.

See `docs/migration-ledger.md` → "Transform goldens".
"""

from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from pipelex.migration.documents import document_paths
from pipelex.migration.engine import apply_ops_over_text
from pipelex.migration.fingerprint import PATH_SEPARATOR
from pipelex.migration.goldens import defaults_golden_path
from pipelex.migration.ledger import MigrationEntry, MigrationLedger, MigrationSafety, load_ledger
from pipelex.migration.surfaces import Surface, SurfaceRegistry
from pipelex.system.configuration.config_surface import strip_reserved_meta
from pipelex.tools.misc.json_utils import deep_update
from pipelex.tools.misc.toml_utils import load_toml_from_content


class TransformIssueKind(StrEnum):
    """Why a link of the transform chain failed. Distinct kinds so a red gate says what broke."""

    DEFAULTS_GOLDEN_MISSING = "defaults_golden_missing"
    TRANSFORM_CONFLICTED = "transform_conflicted"
    DESTINATION_NOT_IN_NEW_SHAPE = "destination_not_in_new_shape"
    SURVIVING_PATH_REMOVED = "surviving_path_removed"
    MIGRATED_DOCUMENT_REJECTED = "migrated_document_rejected"


class TransformIssue(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    surface_id: str
    kind: TransformIssueKind = Field(strict=False)
    message: str


def check_transforms(*, registry: SurfaceRegistry, migration_dir: Path) -> list[TransformIssue]:
    """Verify the transform-golden chain of every surface in a registry."""
    issues: list[TransformIssue] = []
    for surface in registry.surfaces:
        issues.extend(check_transform_chain(surface=surface, migration_dir=migration_dir))
    return issues


def check_transform_chain(*, surface: Surface, migration_dir: Path) -> list[TransformIssue]:
    """Verify one surface's chain, pairwise, one link per ledger entry.

    Pairwise is enough: the links compose by induction into the whole chain, because a replay from
    any historical snapshot skips every entry at or below that snapshot's version — their sources
    are material permanently removed.

    Raises:
        MigrationLedgerError: the ledger is missing, unparseable, or internally inconsistent.
    """
    ledger = load_ledger(migration_dir=migration_dir, surface_id=surface.surface_id)
    issues: list[TransformIssue] = []
    for entry in ledger.migration:
        issues.extend(_check_link(surface=surface, ledger=ledger, entry=entry, migration_dir=migration_dir))
    return issues


def _check_link(*, surface: Surface, ledger: MigrationLedger, entry: MigrationEntry, migration_dir: Path) -> list[TransformIssue]:
    if entry.pre_history:
        # A pre-history entry's `before` document is hand-authored rather than snapshotted — there
        # was no fingerprint yet — so it has no link of this chain to be verified against. It is
        # refused outright by `check-ledger` until the check that reads that document exists.
        return []
    if entry.safety is MigrationSafety.UNSAFE:
        # An unsafe entry is reported and never applied, so no document ever makes this transition
        # mechanically. Demanding that its operations reach the new shape would demand a
        # completeness the vocabulary explicitly grants it the right to lack: an entry with no
        # operations at all is legal precisely when it is unsafe.
        return []

    version = entry.to_schema_version
    is_head = version == ledger.surface.current_schema_version
    before_text = _read_defaults_golden(migration_dir=migration_dir, surface_id=surface.surface_id, schema_version=version - 1)
    if before_text is None:
        return [_defaults_golden_missing(surface=surface, entry=entry, migration_dir=migration_dir, schema_version=version - 1)]
    after_text = _read_defaults_golden(migration_dir=migration_dir, surface_id=surface.surface_id, schema_version=version)
    if after_text is None:
        # The head link has no snapshot until `update-migration-schemas` runs, and the coverage
        # gate already asks for exactly that, by name. Saying it twice adds nothing.
        if is_head:
            return []
        return [_defaults_golden_missing(surface=surface, entry=entry, migration_dir=migration_dir, schema_version=version)]

    application = apply_ops_over_text(text=before_text, ops=entry.ops)
    if application.conflicts:
        details = "; ".join(str(conflict.detail) for conflict in application.conflicts)
        return [
            _issue(
                surface=surface,
                kind=TransformIssueKind.TRANSFORM_CONFLICTED,
                message=(
                    f"entry '{entry.id}': {len(application.conflicts)} of its operations conflict when applied to the reference "
                    f"document of schema version {version - 1} — {details}. A document at the version the entry migrates *from* "
                    f"is the one document it must be able to migrate, so a conflict here is a conflict on every file in the field"
                ),
            )
        ]

    issues = _check_paths(surface=surface, entry=entry, before_text=before_text, after_text=after_text, migrated_text=application.text)
    if is_head:
        issues.extend(_check_the_migrated_document_is_accepted(surface=surface, entry=entry, after_text=after_text, migrated_text=application.text))
    return issues


def _check_paths(*, surface: Surface, entry: MigrationEntry, before_text: str, after_text: str, migrated_text: str) -> list[TransformIssue]:
    version = entry.to_schema_version
    before_paths = _paths_of(text=before_text)
    after_paths = _paths_of(text=after_text)
    migrated_paths = _paths_of(text=migrated_text)

    created = migrated_paths - before_paths
    unexpected = {path for path in created - after_paths if _ancestors_are_in(path=path, paths=after_paths)}
    removed = (before_paths & after_paths) - migrated_paths

    issues = [
        _issue(
            surface=surface,
            kind=TransformIssueKind.DESTINATION_NOT_IN_NEW_SHAPE,
            message=(
                f"entry '{entry.id}': migrating the reference document of schema version {version - 1} produces '{path}', which "
                f"schema version {version}'s reference document does not have — a destination is misspelled, or lands where the "
                f"new shape carries nothing. Every file this entry migrates would end up holding that key, with the tool "
                f"reporting success"
            ),
        )
        for path in _shallowest(paths=unexpected)
    ]
    issues.extend(
        _issue(
            surface=surface,
            kind=TransformIssueKind.SURVIVING_PATH_REMOVED,
            message=(
                f"entry '{entry.id}': '{path}' is in the reference documents of schema versions {version - 1} and {version} alike, "
                f"but migrating the first one removes it — an operation targets a parent where it meant to target one child, or "
                f"renames away material the new shape still has"
            ),
        )
        for path in _shallowest(paths=removed)
    )
    return issues


def _check_the_migrated_document_is_accepted(*, surface: Surface, entry: MigrationEntry, after_text: str, migrated_text: str) -> list[TransformIssue]:
    """The last link's output must be something the current model accepts.

    Read the way a user's file is really read: beneath the surface's current defaults layer, not
    alone. A migrated file is *expected* to lack whatever the new version added — that is what
    makes an additive change absorbable — so validating it on its own would report the defaults
    layer doing its job as a failure.

    Only the last link can be checked this way, and that is not a shortcut: it is the only link
    whose model we still have. Earlier ones are covered by induction, having been the last link
    when they were authored.
    """
    document: dict[str, Any] = load_toml_from_content(after_text)
    deep_update(document, updates=load_toml_from_content(migrated_text))
    strip_reserved_meta(config_dict=document)
    try:
        surface.config_model.model_validate(document)
    except ValidationError as exc:
        return [
            _issue(
                surface=surface,
                kind=TransformIssueKind.MIGRATED_DOCUMENT_REJECTED,
                message=(
                    f"entry '{entry.id}': the reference document of schema version {entry.to_schema_version - 1}, migrated by this "
                    f"entry and read beneath the current defaults, is not accepted by {surface.config_model.__name__} — {exc}. "
                    f"An operation writes a value or a key the schema does not take, so every file it migrates fails to load"
                ),
            )
        ]
    return []


def _read_defaults_golden(*, migration_dir: Path, surface_id: str, schema_version: int) -> str | None:
    path = defaults_golden_path(migration_dir=migration_dir, surface_id=surface_id, schema_version=schema_version)
    return path.read_text(encoding="utf-8") if path.exists() else None


def _paths_of(*, text: str) -> set[str]:
    return document_paths(document=load_toml_from_content(text))


def _ancestors_are_in(*, path: str, paths: set[str]) -> bool:
    """Whether every table containing this path is present in a path set.

    A created path is only meaningful against a document that still has somewhere to put it: when
    the reference documents disagree about a whole container — an entry of an open mapping dropped
    between versions, say — what an operation did inside it says nothing about the operation.
    """
    segments = path.split(PATH_SEPARATOR)
    return all(PATH_SEPARATOR.join(segments[:depth]) in paths for depth in range(1, len(segments)))


def _shallowest(*, paths: set[str]) -> list[str]:
    """The topmost path of each affected subtree, sorted.

    A `delete_table` one level too high takes a whole section with it, and naming every leaf it
    took would bury the one path the author has to look at under its own consequences.
    """
    return sorted(path for path in paths if not _has_ancestor_in(path=path, paths=paths))


def _has_ancestor_in(*, path: str, paths: set[str]) -> bool:
    segments = path.split(PATH_SEPARATOR)
    return any(PATH_SEPARATOR.join(segments[:depth]) in paths for depth in range(1, len(segments)))


def _defaults_golden_missing(*, surface: Surface, entry: MigrationEntry, migration_dir: Path, schema_version: int) -> TransformIssue:
    path = defaults_golden_path(migration_dir=migration_dir, surface_id=surface.surface_id, schema_version=schema_version)
    return _issue(
        surface=surface,
        kind=TransformIssueKind.DEFAULTS_GOLDEN_MISSING,
        message=(
            f"entry '{entry.id}' cannot be verified against what it did: no reference document at {path.name}. Run `make umig` if "
            f"the current schema version was just bumped; below the current version this is a broken chain, and the missing link "
            f"has to be restored rather than regenerated — a regenerated one would describe today's models, not that version's"
        ),
    )


def _issue(*, surface: Surface, kind: TransformIssueKind, message: str) -> TransformIssue:
    return TransformIssue(surface_id=surface.surface_id, kind=kind, message=message)
