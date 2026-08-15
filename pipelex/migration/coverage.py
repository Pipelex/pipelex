"""The coverage check — the forcing function that makes a schema change record what it did.

This is the half of the gate that needs no applier and no engine: it reads the checked-in ledgers
and golden chains, recomputes each surface's fingerprint, and refuses a change that would leave a
user's file broken with nothing written down about how to repair it.

The centrepiece is the **sequential path state** walk. An entry's operations chain — a parent is
renamed and then keys inside it are renamed — so the intermediate paths belong to neither the old
fingerprint nor the new one, and no ordering avoids that. The walk therefore replays the entry
symbolically over the previous fingerprint's path set and compares the end state with the new
fingerprint. One walk answers four questions at once:

- an operation whose source is absent from the state is **dead** — it can never fire;
- a path surviving the walk that the new fingerprint does not have is either an **unaccounted
  removal** or a **misspelled destination**, which is the failure the destination cross-check
  exists for: without it a typo passes coverage *and* convergence, then migrates every user file
  to a key `extra="forbid"` rejects, with the tool reporting success;
- a path of the new fingerprint that the walk deleted is **over-deletion** — an entry that dropped
  a parent table where it meant to drop one child;
- everything the new fingerprint has and the walk does not is a genuine addition, which needs no
  operation because the defaults layer absorbs it.

See `docs/migration-ledger.md` → "Legality rules" and "The checks".
"""

from collections.abc import Sequence
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from pipelex.migration.fingerprint import PATH_SEPARATOR, TABLE_TYPE, SurfaceFingerprint, compute_fingerprint
from pipelex.migration.goldens import defaults_golden_path, read_fingerprint_golden
from pipelex.migration.ledger import MigrationEntry, MigrationLedger, MigrationSafety, load_ledger
from pipelex.migration.surfaces import Surface, SurfaceRegistry
from pipelex.suggested_fix import (
    WILDCARD_SEGMENT,
    DeleteKeyOp,
    DeleteTableOp,
    MigrationOp,
    MoveKeyOp,
    RemapValueOp,
    RenameTableKeyOp,
)


class CoverageIssueKind(StrEnum):
    """Why a surface failed the gate. Distinct kinds so a red gate says which guarantee broke."""

    LEDGER_DISAGREES_WITH_REGISTRY = "ledger_disagrees_with_registry"
    GOLDEN_MISSING = "golden_missing"
    SNAPSHOT_PENDING = "snapshot_pending"
    FINGERPRINT_DRIFTED = "fingerprint_drifted"
    REMOVAL_NEEDS_A_BUMP = "removal_needs_a_bump"
    DEAD_OP = "dead_op"
    UNACCOUNTED_PATH = "unaccounted_path"
    OVER_DELETION = "over_deletion"
    ENUM_MEMBER_NOT_REMAPPED = "enum_member_not_remapped"
    ILLEGAL_REMAP = "illegal_remap"
    REQUIRED_PATH_WITHOUT_DEFAULT = "required_path_without_default"


class CoverageIssue(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    surface_id: str
    kind: CoverageIssueKind = Field(strict=False)
    message: str


class FingerprintDiff(BaseModel):
    """What moved between two fingerprints of the same surface."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    added_paths: list[str] = Field(default_factory=list[str])
    removed_paths: list[str] = Field(default_factory=list[str])
    changed_paths: list[str] = Field(default_factory=list[str])
    added_enum_members: dict[str, list[str]] = Field(default_factory=dict[str, list[str]])
    removed_enum_members: dict[str, list[str]] = Field(default_factory=dict[str, list[str]])

    @property
    def is_empty(self) -> bool:
        return not (self.added_paths or self.removed_paths or self.changed_paths or self.added_enum_members or self.removed_enum_members)

    @property
    def has_removals(self) -> bool:
        return bool(self.removed_paths or self.removed_enum_members)


def diff_fingerprints(*, before: SurfaceFingerprint, after: SurfaceFingerprint) -> FingerprintDiff:
    before_paths = before.path_names()
    after_paths = after.path_names()
    shared = sorted(before_paths & after_paths)

    added_enum_members: dict[str, list[str]] = {}
    removed_enum_members: dict[str, list[str]] = {}
    changed_paths: list[str] = []
    for path in shared:
        before_record = before.paths[path]
        after_record = after.paths[path]
        if before_record != after_record:
            changed_paths.append(path)
        before_members = set(before_record.enum_members or [])
        after_members = set(after_record.enum_members or [])
        if added := sorted(after_members - before_members):
            added_enum_members[path] = added
        if removed := sorted(before_members - after_members):
            removed_enum_members[path] = removed

    return FingerprintDiff(
        added_paths=sorted(after_paths - before_paths),
        removed_paths=sorted(before_paths - after_paths),
        changed_paths=changed_paths,
        added_enum_members=added_enum_members,
        removed_enum_members=removed_enum_members,
    )


class PathState(BaseModel):
    """The symbolic state of a path set part-way through an entry's operations.

    Each live path is carried with the path it *originated from* in the previous fingerprint, so
    that an operation acting on a path some earlier operation renamed can still be attributed to
    the schema path it is really about.
    """

    model_config = ConfigDict(extra="forbid")

    origin_by_current: dict[str, str]

    @classmethod
    def make_from_fingerprint(cls, *, fingerprint: SurfaceFingerprint) -> "PathState":
        return cls(origin_by_current={path: path for path in fingerprint.path_names()})

    def current_paths(self) -> set[str]:
        return set(self.origin_by_current)

    def subtree_of(self, *, path: str) -> list[str]:
        prefix = path + PATH_SEPARATOR
        return [current for current in self.origin_by_current if current == path or current.startswith(prefix)]

    def drop_subtree(self, *, path: str) -> None:
        for current in self.subtree_of(path=path):
            del self.origin_by_current[current]

    def move_subtree(self, *, source: str, destination: str) -> None:
        moved = {destination + current[len(source) :]: self.origin_by_current[current] for current in self.subtree_of(path=source)}
        self.drop_subtree(path=source)
        self.origin_by_current.update(moved)

    def final_path_of_origin(self, *, origin: str) -> str | None:
        for current, recorded_origin in self.origin_by_current.items():
            if recorded_origin == origin:
                return current
        return None


class RecordedRemap(BaseModel):
    """A remap that fired during the walk, attributed to the schema path it originated from."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    origin_path: str
    old_values: list[str]
    new_values: list[str]


def _joined(*, segments: Sequence[str]) -> str:
    return PATH_SEPARATOR.join(segments)


def walk_entry(*, entry: MigrationEntry, before: SurfaceFingerprint) -> tuple[PathState, list[str], list[RecordedRemap]]:
    """Replay an entry's operations symbolically over the previous fingerprint's path set.

    Returns the end state, the descriptions of any operation whose source was absent (a dead
    operation that can never fire), and the remaps that did fire, attributed to the schema path
    they originated from.
    """
    state = PathState.make_from_fingerprint(fingerprint=before)
    dead_ops: list[str] = []
    remaps: list[RecordedRemap] = []

    for op in entry.ops:
        source = _op_source_path(op=op)
        if source not in state.origin_by_current:
            dead_ops.append(f"{op.kind} on '{source}' — no such path at schema version {before.schema_version}, so it can never fire")
            continue
        _apply_op_to_state(op=op, source=source, state=state, remaps=remaps)

    return state, dead_ops, remaps


def _op_source_path(*, op: MigrationOp) -> str:
    match op:
        case DeleteTableOp():
            return _joined(segments=op.table_path)
        case DeleteKeyOp() | RenameTableKeyOp() | MoveKeyOp() | RemapValueOp():
            return _joined(segments=[*op.table_path, op.key])


def _apply_op_to_state(*, op: MigrationOp, source: str, state: PathState, remaps: list[RecordedRemap]) -> None:
    match op:
        case DeleteKeyOp() | DeleteTableOp():
            state.drop_subtree(path=source)
        case RenameTableKeyOp():
            state.move_subtree(source=source, destination=_joined(segments=[*op.table_path, op.new_key]))
        case MoveKeyOp():
            state.move_subtree(source=source, destination=_joined(segments=[*op.new_table_path, op.new_key]))
        case RemapValueOp():
            remaps.append(
                RecordedRemap(
                    origin_path=state.origin_by_current[source],
                    old_values=sorted(op.mapping),
                    new_values=sorted(set(op.mapping.values())),
                )
            )


def check_entry_accounting(*, surface_id: str, entry: MigrationEntry, before: SurfaceFingerprint, after: SurfaceFingerprint) -> list[CoverageIssue]:
    """Verify that one entry says exactly what the fingerprint diff shows happened."""
    if entry.pre_history:
        # A removal that predates the first fingerprint has no observed diff to be accounted
        # against — that is what the flag means. Such an entry declares its own removed paths and
        # ships a hand-authored `before` document, and is verified against those by `check-ledger`
        # rather than here. Checking it against a fingerprint pair it never described would
        # produce a failure naming the wrong defect.
        return []

    issues: list[CoverageIssue] = []
    state, dead_ops, remaps = walk_entry(entry=entry, before=before)

    for description in dead_ops:
        issues.append(CoverageIssue(surface_id=surface_id, kind=CoverageIssueKind.DEAD_OP, message=f"entry '{entry.id}': {description}"))

    after_paths = after.path_names()
    before_paths = before.path_names()
    end_paths = state.current_paths()

    for path in sorted(end_paths - after_paths):
        issues.append(
            CoverageIssue(
                surface_id=surface_id,
                kind=CoverageIssueKind.UNACCOUNTED_PATH,
                message=(
                    f"entry '{entry.id}': after replaying its operations, '{path}' is still there but schema version "
                    f"{after.schema_version} has no such path — either a removal with no operation accounting for it, "
                    f"or an operation whose destination is misspelled"
                ),
            )
        )

    for path in sorted((after_paths - end_paths) & before_paths):
        issues.append(
            CoverageIssue(
                surface_id=surface_id,
                kind=CoverageIssueKind.OVER_DELETION,
                message=(
                    f"entry '{entry.id}': its operations remove '{path}', but schema version {after.schema_version} still has it — "
                    f"an operation targets a parent where it meant to target one child"
                ),
            )
        )

    issues.extend(_check_enum_accounting(surface_id=surface_id, entry=entry, before=before, after=after, remaps=remaps))
    issues.extend(_check_remap_legality(surface_id=surface_id, entry=entry, after=after, state=state, remaps=remaps))
    return issues


def _check_enum_accounting(
    *,
    surface_id: str,
    entry: MigrationEntry,
    before: SurfaceFingerprint,
    after: SurfaceFingerprint,
    remaps: list[RecordedRemap],
) -> list[CoverageIssue]:
    if entry.safety is MigrationSafety.UNSAFE:
        # An unsafe entry is reported and never applied, so it is allowed to describe a change no
        # operation can make. That is what `unsafe` is for.
        return []
    diff = diff_fingerprints(before=before, after=after)
    remapped_by_origin: dict[str, set[str]] = {}
    for remap in remaps:
        remapped_by_origin.setdefault(remap.origin_path, set()).update(remap.old_values)

    issues: list[CoverageIssue] = []
    for path, removed_members in diff.removed_enum_members.items():
        unaccounted = sorted(set(removed_members) - remapped_by_origin.get(path, set()))
        if unaccounted:
            issues.append(
                CoverageIssue(
                    surface_id=surface_id,
                    kind=CoverageIssueKind.ENUM_MEMBER_NOT_REMAPPED,
                    message=(
                        f"entry '{entry.id}': '{path}' no longer accepts {unaccounted} — a file carrying one of those "
                        f"values no longer validates, so the entry needs a remap_value for each, or must be marked unsafe"
                    ),
                )
            )
    return issues


def _check_remap_legality(
    *,
    surface_id: str,
    entry: MigrationEntry,
    after: SurfaceFingerprint,
    state: PathState,
    remaps: list[RecordedRemap],
) -> list[CoverageIssue]:
    """A `safe` remap must be provably unable to fire on a current-valid file.

    That holds when the target is enumerated at the new schema and every old spelling in the
    mapping now falls outside its member set. When an old spelling remains legal — or the path is
    a free string, where staleness can never be proven from the schema — the applier cannot tell a
    stale value from a deliberate choice, and the entry has to be `unsafe`.
    """
    if entry.safety is MigrationSafety.UNSAFE:
        return []

    issues: list[CoverageIssue] = []
    for remap in remaps:
        final_path = state.final_path_of_origin(origin=remap.origin_path)
        record = after.paths.get(final_path) if final_path is not None else None
        if record is None:
            # The path the remap targets does not survive into the new schema; the unaccounted-path
            # or over-deletion check above has already said so in terms the author can act on.
            continue
        member_set = set(record.enum_members or [])
        if not member_set:
            issues.append(
                CoverageIssue(
                    surface_id=surface_id,
                    kind=CoverageIssueKind.ILLEGAL_REMAP,
                    message=(
                        f"entry '{entry.id}': remap_value on '{final_path}' is 'safe', but that path is not enumerated at "
                        f"schema version {after.schema_version} — staleness cannot be proven from the schema, so the entry must be unsafe"
                    ),
                )
            )
            continue
        still_legal = sorted(set(remap.old_values) & member_set)
        if still_legal:
            issues.append(
                CoverageIssue(
                    surface_id=surface_id,
                    kind=CoverageIssueKind.ILLEGAL_REMAP,
                    message=(
                        f"entry '{entry.id}': remap_value on '{final_path}' is 'safe', but {still_legal} are still legal values at "
                        f"schema version {after.schema_version} — a user who chose one deliberately would have it rewritten"
                    ),
                )
            )
        unknown_new = sorted(set(remap.new_values) - member_set)
        if unknown_new:
            issues.append(
                CoverageIssue(
                    surface_id=surface_id,
                    kind=CoverageIssueKind.ILLEGAL_REMAP,
                    message=(
                        f"entry '{entry.id}': remap_value on '{final_path}' rewrites values to {unknown_new}, which schema version "
                        f"{after.schema_version} does not accept — every migrated file would be rejected, with the tool reporting success"
                    ),
                )
            )
    return issues


def check_defaults_layer(*, surface_id: str, fingerprint: SurfaceFingerprint) -> list[CoverageIssue]:
    """Every path a document must carry has to have a value beneath it.

    This is the standing form of the additive rule. A key we add is supplied by the defaults
    layer, so an old file that lacks it still validates — but only if the defaults layer really
    supplies it. A required path with no default is breaking on the day it lands, and the only
    remedy the vocabulary allows is to give it one: writing a value into the user's file is a
    semantic edit dressed up as a fix, which is why the materializing operations are excluded from
    the migration vocabulary outright.

    Wildcard paths are exempt by construction: the keys beneath an open node are the user's, so
    there is no single value for the defaults layer to supply.
    """
    issues: list[CoverageIssue] = []
    for path, record in fingerprint.paths.items():
        if WILDCARD_SEGMENT in path.split(PATH_SEPARATOR):
            continue
        if record.value_type == TABLE_TYPE or record.default is not None:
            continue
        if not fingerprint.is_effectively_required(path=path):
            continue
        issues.append(
            CoverageIssue(
                surface_id=surface_id,
                kind=CoverageIssueKind.REQUIRED_PATH_WITHOUT_DEFAULT,
                message=(
                    f"'{path}' is required but the defaults layer supplies no value for it, so a file written before it "
                    f"existed no longer validates — give it a default rather than writing one into the user's file"
                ),
            )
        )
    return issues


def check_surface(*, surface: Surface, migration_dir: Path) -> list[CoverageIssue]:
    """Run the whole coverage check over one surface."""
    surface_id = surface.surface_id
    ledger = load_ledger(migration_dir=migration_dir, surface_id=surface_id)
    issues = _check_ledger_agrees_with_registry(surface=surface, ledger=ledger)

    current_version = ledger.surface.current_schema_version
    live = compute_fingerprint(
        surface_id=surface_id,
        schema_version=current_version,
        config_model=surface.config_model,
        defaults_document=surface.read_defaults_document(),
    )
    issues.extend(check_defaults_layer(surface_id=surface_id, fingerprint=live))
    issues.extend(_check_stored_links(surface_id=surface_id, ledger=ledger, live=live, migration_dir=migration_dir))
    issues.extend(_check_head_link(surface_id=surface_id, current_version=current_version, live=live, migration_dir=migration_dir))
    issues.extend(_check_head_defaults_document(surface=surface, current_version=current_version, migration_dir=migration_dir))
    return issues


def _check_head_defaults_document(*, surface: Surface, current_version: int, migration_dir: Path) -> list[CoverageIssue]:
    """The head link's reference document must still be the document it is a copy of.

    `defaults@<current>.toml` is a checked-in copy of a live source — the packaged TOML, or the
    document the model's own defaults synthesize — and the fingerprint diff cannot see it drift:
    an edited comment or a flipped value inside an unchanged path moves the file and not the path
    set. Left unchecked, two checked-in copies of the same document quietly disagree, and the one
    a later phase applies migrations to is the stale one.
    """
    path = defaults_golden_path(migration_dir=migration_dir, surface_id=surface.surface_id, schema_version=current_version)
    if not path.exists():
        # The head fingerprint check already asks for the snapshot; saying it twice adds nothing.
        return []
    if path.read_text(encoding="utf-8") == surface.render_reference_document():
        return []
    return [
        CoverageIssue(
            surface_id=surface.surface_id,
            kind=CoverageIssueKind.FINGERPRINT_DRIFTED,
            message=(
                f"the reference document at {path.name} no longer matches the surface's defaults layer — "
                f"run `make umig` so the golden records the change"
            ),
        )
    ]


def _check_ledger_agrees_with_registry(*, surface: Surface, ledger: MigrationLedger) -> list[CoverageIssue]:
    """The ledger's own `[surface]` block must describe the surface the registry declares.

    Both halves are hand-written and both are consumed as truth — the ledger's when a migration
    walks a directory, the registry's when a gate fingerprints a model — so a disagreement between
    them is a silent mis-migration waiting for the day the two readers meet.
    """
    mismatches = [
        (label, declared, recorded)
        for label, declared, recorded in (
            ("id", surface.surface_id, ledger.surface.id),
            ("base_file", surface.base_file, ledger.surface.base_file),
            ("tier_glob", surface.tier_glob, ledger.surface.tier_glob),
        )
        if declared != recorded
    ]
    return [
        CoverageIssue(
            surface_id=surface.surface_id,
            kind=CoverageIssueKind.LEDGER_DISAGREES_WITH_REGISTRY,
            message=f"the ledger says {label} = {recorded!r} but the registry says {declared!r}",
        )
        for label, declared, recorded in mismatches
    ]


def _check_stored_links(*, surface_id: str, ledger: MigrationLedger, live: SurfaceFingerprint, migration_dir: Path) -> list[CoverageIssue]:
    """Check every entry against the fingerprint pair it claims to explain.

    Every link is re-checked on every run, not only the one being authored. An entry verified once
    at bump time and never again would silently stop matching its own diff the first time somebody
    edited it.
    """
    issues: list[CoverageIssue] = []
    for entry in ledger.migration:
        version = entry.to_schema_version
        before = read_fingerprint_golden(migration_dir=migration_dir, surface_id=surface_id, schema_version=version - 1)
        if before is None:
            issues.append(
                CoverageIssue(
                    surface_id=surface_id,
                    kind=CoverageIssueKind.GOLDEN_MISSING,
                    message=f"entry '{entry.id}' has nothing to be checked against: no fingerprint golden for schema version {version - 1}",
                )
            )
            continue
        after = _after_fingerprint_for_link(
            surface_id=surface_id,
            version=version,
            current_version=ledger.surface.current_schema_version,
            live=live,
            migration_dir=migration_dir,
        )
        if after is None:
            issues.append(
                CoverageIssue(
                    surface_id=surface_id,
                    kind=CoverageIssueKind.GOLDEN_MISSING,
                    message=(
                        f"entry '{entry.id}' cannot be checked: no fingerprint golden for schema version {version}, "
                        f"and it is not the current version, so nothing live can stand in for it"
                    ),
                )
            )
            continue
        issues.extend(check_entry_accounting(surface_id=surface_id, entry=entry, before=before, after=after))
    return issues


def _after_fingerprint_for_link(
    *,
    surface_id: str,
    version: int,
    current_version: int,
    live: SurfaceFingerprint,
    migration_dir: Path,
) -> SurfaceFingerprint | None:
    """The fingerprint an entry migrates *to*, stored or live.

    Only the head link may fall back to the live fingerprint, and only because it has no snapshot
    until `update-migration-schemas` runs — which is what makes the gate red *before* a bump is
    snapshotted rather than after. A missing golden anywhere below the head is a broken chain, and
    substituting the live fingerprint there would silently compare an old entry against today's
    models and call the mismatch the entry's fault.
    """
    stored = read_fingerprint_golden(migration_dir=migration_dir, surface_id=surface_id, schema_version=version)
    if stored is not None:
        return stored
    return live if version == current_version else None


def _check_head_link(*, surface_id: str, current_version: int, live: SurfaceFingerprint, migration_dir: Path) -> list[CoverageIssue]:
    golden = read_fingerprint_golden(migration_dir=migration_dir, surface_id=surface_id, schema_version=current_version)
    if golden is None:
        return [
            CoverageIssue(
                surface_id=surface_id,
                kind=CoverageIssueKind.SNAPSHOT_PENDING,
                message=(
                    f"schema version {current_version} has never been snapshotted — run `make umig` to write its fingerprint and defaults goldens"
                ),
            )
        ]

    diff = diff_fingerprints(before=golden, after=live)
    if diff.is_empty:
        return []
    if diff.has_removals:
        removed = diff.removed_paths + [f"{path}: {members}" for path, members in diff.removed_enum_members.items()]
        return [
            CoverageIssue(
                surface_id=surface_id,
                kind=CoverageIssueKind.REMOVAL_NEEDS_A_BUMP,
                message=(
                    f"the models no longer have {removed}, which breaks every file that carries them. Bump "
                    f"current_schema_version to {current_version + 1}, add the entry '{surface_id}@{current_version + 1}' "
                    f"accounting for each, then run `make umig`"
                ),
            )
        ]
    return [
        CoverageIssue(
            surface_id=surface_id,
            kind=CoverageIssueKind.FINGERPRINT_DRIFTED,
            message=(
                f"the fingerprint moved additively — added {diff.added_paths or '[]'}, changed {diff.changed_paths or '[]'}. "
                f"Nothing breaks and no entry is needed; run `make umig` so the golden records it"
            ),
        )
    ]


def check_registry(*, registry: SurfaceRegistry, migration_dir: Path) -> list[CoverageIssue]:
    """Run the coverage check over every surface in a registry."""
    issues: list[CoverageIssue] = []
    for surface in registry.surfaces:
        issues.extend(check_surface(surface=surface, migration_dir=migration_dir))
    return issues
