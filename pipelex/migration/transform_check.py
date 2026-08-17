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

- **Every path the migration creates, the new shape has** — its reference document or its
  fingerprint. This is the wrong destination, the misordered rename and the operation that lands in
  a table the new shape does not carry. The fingerprint is consulted alongside the document because
  a document cannot express every legal path: an optional key whose default is `None` is absent
  from the reference document, TOML having no null, while being a perfectly ordinary destination —
  and a misspelled destination is in neither, so nothing is weakened. A created path whose
  *container* is gone from the new document is exempt too: when a whole entry of an open mapping
  was dropped from the reference document between versions, nothing can be said about what an
  operation did inside it.
- **Every path the two reference documents share survives the migration.** This is over-deletion —
  an entry that dropped a parent table where it meant to drop one child. A path the new shape no
  longer has is not this check's business: the schema removed it, and coverage is what demands the
  operation that accounts for it.
- **The last link's migrated document is accepted at the current schema**, read the way a user's
  file is actually read: beneath the current defaults layer for a surface that has one, on its own for
  a copied document, and validated the way that surface's loader validates. This is where a wrong
  value lands — a remap rewriting to a spelling the schema rejects, a destination the model does not
  know.

This is also where a **pre-history** entry is verified, and it is verified by exactly these three
claims: an entry whose change predates the first fingerprint has no `defaults@N-1` to start from,
so it ships a hand-authored `before@N.toml` saying what the old shape was, and the link runs from
there. Nothing else about the check changes — which is the point of that exception's shape. What
the entry may declare and address is `check-ledger`'s half.

What the comparator deliberately does not do, and why (each stated in `docs/migration-ledger.md` too):

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

**A created path is checked against `defaults@N` *or* `fingerprint@N`, not against the document
alone.** An optional key whose default is `None` has no value in any reference document — TOML has
no null and the synthesized document drops it — so a migration that moves a user's value onto such
a key creates a path the document legitimately lacks. Checking the document alone would refuse the
one destination the schema most obviously has. The fingerprint is checked-in data like everything
else here, so consulting it costs the check nothing it was protecting.

See `docs/migration-ledger.md` → "Transform goldens".
"""

from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from pipelex.migration.documents import document_paths, path_matches_pattern
from pipelex.migration.engine import apply_ops_over_text
from pipelex.migration.exceptions import MigrationGoldenError
from pipelex.migration.fingerprint import PATH_SEPARATOR, SurfaceFingerprint
from pipelex.migration.goldens import defaults_golden_path, pre_history_document_path, read_fingerprint_golden
from pipelex.migration.ledger import MigrationEntry, MigrationLedger, load_ledger
from pipelex.migration.safety import MigrationSafety
from pipelex.migration.surfaces import Surface, SurfaceRegistry
from pipelex.system.configuration.config_surface import strip_reserved_meta
from pipelex.tools.misc.json_utils import deep_update
from pipelex.tools.misc.toml_utils import load_toml_from_content


class TransformIssueKind(StrEnum):
    """Why a link of the transform chain failed. Distinct kinds so a red gate says what broke."""

    DEFAULTS_GOLDEN_MISSING = "defaults_golden_missing"
    PRE_HISTORY_DOCUMENT_MISSING = "pre_history_document_missing"
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
    if entry.safety is MigrationSafety.UNSAFE:
        # An unsafe entry is reported and never applied, so no document ever makes this transition
        # mechanically. Demanding that its operations reach the new shape would demand a
        # completeness the vocabulary explicitly grants it the right to lack: an entry with no
        # operations at all is legal precisely when it is unsafe.
        return []

    version = entry.to_schema_version
    is_head = version == ledger.surface.current_schema_version
    before_text = _read_document_the_entry_migrates_from(surface=surface, entry=entry, migration_dir=migration_dir)
    if before_text is None:
        return [_starting_document_missing(surface=surface, entry=entry, migration_dir=migration_dir)]
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
                    f"entry '{entry.id}': {len(application.conflicts)} of its operations conflict when applied to "
                    f"{_starting_document_label(entry=entry)} — {details}. A document at the version the entry migrates *from* "
                    f"is the one document it must be able to migrate, so a conflict here is a conflict on every file in the field"
                ),
            )
        ]

    issues = _check_paths(
        surface=surface,
        entry=entry,
        before_text=before_text,
        after_text=after_text,
        migrated_text=application.text,
        after_fingerprint=read_fingerprint_golden(migration_dir=migration_dir, surface_id=surface.surface_id, schema_version=version),
    )
    if is_head:
        issues.extend(_check_the_migrated_document_is_accepted(surface=surface, entry=entry, after_text=after_text, migrated_text=application.text))
    return issues


def _check_paths(
    *,
    surface: Surface,
    entry: MigrationEntry,
    before_text: str,
    after_text: str,
    migrated_text: str,
    after_fingerprint: SurfaceFingerprint | None,
) -> list[TransformIssue]:
    version = entry.to_schema_version
    before_paths = _paths_of(text=before_text)
    after_paths = _paths_of(text=after_text)
    migrated_paths = _paths_of(text=migrated_text)
    recorded_paths = after_fingerprint.path_names() if after_fingerprint is not None else set[str]()

    created = {path for path in migrated_paths - before_paths if not _is_recorded(path=path, recorded_paths=recorded_paths)}
    unexpected = {path for path in created - after_paths if _ancestors_are_in(path=path, paths=after_paths)}
    removed = (before_paths & after_paths) - migrated_paths

    issues = [
        _issue(
            surface=surface,
            kind=TransformIssueKind.DESTINATION_NOT_IN_NEW_SHAPE,
            message=(
                f"entry '{entry.id}': migrating {_starting_document_label(entry=entry)} produces '{path}', which schema version "
                f"{version} has nowhere — neither its reference document nor its fingerprint carries that path, so a destination "
                f"is misspelled or lands where the new shape holds nothing. Every file this entry migrates would end up holding "
                f"that key, with the tool reporting success"
            ),
        )
        for path in _shallowest(paths=unexpected)
    ]
    issues.extend(
        _issue(
            surface=surface,
            kind=TransformIssueKind.SURVIVING_PATH_REMOVED,
            message=(
                f"entry '{entry.id}': '{path}' is in {_starting_document_label(entry=entry)} and in the reference document of "
                f"schema version {version} alike, but migrating the first one removes it — an operation targets a parent where it "
                f"meant to target one child, or renames away material the new shape still has"
            ),
        )
        for path in _shallowest(paths=removed)
    )
    return issues


def _check_the_migrated_document_is_accepted(*, surface: Surface, entry: MigrationEntry, after_text: str, migrated_text: str) -> list[TransformIssue]:
    """The last link's output must be something the current schema accepts.

    Read the way a user's file is really read, which is where the surface's own two declarations come
    in. A **layered** surface's file is read beneath the current defaults layer, and a migrated file is
    *expected* to lack whatever the new version added — that is what makes an additive change
    absorbable — so validating it alone would report the defaults layer doing its job as a failure. A
    **copied** document has nothing beneath it, and merging the reference copy of one backend
    definition under another user's would validate a hybrid no machine has.

    What "accepted" means is likewise the surface's to say (`Surface.validate_document`): for a backend
    definition file it is the loader's own merge-then-validate, because neither `[defaults]` nor a model
    table validates alone.

    Only the last link can be checked this way, and that is not a shortcut: it is the only link
    whose model we still have. Earlier ones are covered by induction, having been the last link
    when they were authored.
    """
    document: dict[str, Any]
    if surface.defaults_layer_kind.is_layered_beneath_the_users_file:
        document = load_toml_from_content(after_text)
        read_as = "read beneath the current defaults"
    else:
        document = {}
        read_as = "read on its own, as a copied document is"
    deep_update(document, updates=load_toml_from_content(migrated_text))
    strip_reserved_meta(config_dict=document)
    rejection = surface.validate_document(document=document)
    if rejection is not None:
        return [
            _issue(
                surface=surface,
                kind=TransformIssueKind.MIGRATED_DOCUMENT_REJECTED,
                message=(
                    f"entry '{entry.id}': {_starting_document_label(entry=entry)}, migrated by this "
                    f"entry and {read_as}, is not accepted at the current schema — {rejection}. "
                    f"An operation writes a value or a key the schema does not take, so every file it migrates fails to load"
                ),
            )
        ]
    return []


def _read_defaults_golden(*, migration_dir: Path, surface_id: str, schema_version: int) -> str | None:
    return _read_golden_text(path=defaults_golden_path(migration_dir=migration_dir, surface_id=surface_id, schema_version=schema_version))


def _read_golden_text(*, path: Path) -> str | None:
    """A golden's text, `None` when it does not exist — and a named refusal when it exists but cannot be read.

    Raises:
        MigrationGoldenError: the file is there and is not readable UTF-8 text. A gate has to say
            which file, the same way `read_fingerprint_golden` does; a raw traceback from deep in a
            comparison names nothing an author can act on.
    """
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, ValueError) as exc:
        msg = f"unreadable golden at {path}: {exc}"
        raise MigrationGoldenError(msg) from exc


def _read_document_the_entry_migrates_from(*, surface: Surface, entry: MigrationEntry, migration_dir: Path) -> str | None:
    """The document this link starts from: the previous snapshot, or a hand-authored one.

    A pre-history entry has no previous snapshot by definition — the change predates the first
    fingerprint — so its author writes the old shape down as `before@N.toml` and the link is
    verified from there. Everything after that point is identical for both kinds of entry, which is
    the whole reason the exception is worth having: the three claims below are what actually
    verifies a pre-history entry, and they are the same three claims every other entry answers.
    """
    if entry.pre_history:
        return _read_golden_text(path=_pre_history_document_path(surface=surface, entry=entry, migration_dir=migration_dir))
    return _read_defaults_golden(migration_dir=migration_dir, surface_id=surface.surface_id, schema_version=entry.to_schema_version - 1)


def _pre_history_document_path(*, surface: Surface, entry: MigrationEntry, migration_dir: Path) -> Path:
    return pre_history_document_path(migration_dir=migration_dir, surface_id=surface.surface_id, schema_version=entry.to_schema_version)


def _starting_document_label(*, entry: MigrationEntry) -> str:
    if entry.pre_history:
        return f"its hand-authored pre-history document (before@{entry.to_schema_version}.toml)"
    return f"the reference document of schema version {entry.to_schema_version - 1}"


def _starting_document_missing(*, surface: Surface, entry: MigrationEntry, migration_dir: Path) -> TransformIssue:
    if not entry.pre_history:
        return _defaults_golden_missing(surface=surface, entry=entry, migration_dir=migration_dir, schema_version=entry.to_schema_version - 1)
    path = _pre_history_document_path(surface=surface, entry=entry, migration_dir=migration_dir)
    return _issue(
        surface=surface,
        kind=TransformIssueKind.PRE_HISTORY_DOCUMENT_MISSING,
        message=(
            f"entry '{entry.id}' is marked pre_history and there is no {path.name} beside the golden chain. A pre-history entry "
            f"is exempt from being accounted against a fingerprint diff precisely because none describes it, and this document "
            f"is what it is verified against instead — write the old shape it migrates from, by hand, at {path}"
        ),
    )


def _paths_of(*, text: str) -> set[str]:
    return document_paths(document=load_toml_from_content(text))


def _is_recorded(*, path: str, recorded_paths: set[str]) -> bool:
    """Whether a concrete document path is one the fingerprint records, wildcard included.

    A document names the user's own key where the fingerprint names `*`, so `deck.claude.new_name`
    is recorded as `deck.*.new_name`. Comparing the two literally would let a rename beneath an
    open mapping read as a misspelled destination whenever the reference document happens not to
    carry that key under that entry. The matching rule is `path_matches_pattern`'s — the one
    definition every comparison of a document against a schema path reads.
    """
    return any(path_matches_pattern(path=path, pattern=recorded) for recorded in recorded_paths)


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
