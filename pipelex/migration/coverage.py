"""The coverage check — the forcing function that makes a schema change record what it did.

This is the half of the gate that needs no applier and no engine: it reads the checked-in ledgers
and golden chains, recomputes each surface's fingerprint, and refuses a change that would leave a
user's file broken with nothing written down about how to repair it.

The centrepiece is the **sequential path state** walk, which lives in `walk.py` because the ledger
check reads it too. An entry's operations chain — a parent is renamed and then keys inside it are
renamed — so the intermediate paths belong to neither the old fingerprint nor the new one, and no
ordering avoids that. The walk replays the entry symbolically over the previous fingerprint's path
set, and this module compares the end state with the new fingerprint. One walk answers every
question at once:

- an operation whose source is absent from the state — or a `delete_table` aimed at a key — is
  **dead**: it can never fire, and the applier's guarded skip would report success forever;
- a rename or move onto a path the state already has is a **destination collision**: the applier
  refuses to clobber, so a valid old-schema file carrying both keys conflicts on every run;
- a path surviving the walk that the new fingerprint does not have is either an **unaccounted
  removal** or a **misspelled destination**, which is the failure the destination cross-check
  exists for: without it a typo passes coverage *and* convergence, then migrates every user file
  to a key `extra="forbid"` rejects, with the tool reporting success;
- a path of the new fingerprint that the walk deleted is **over-deletion** — an entry that dropped
  a parent table where it meant to drop one child;
- an enumerated member lost between the two fingerprints is looked up at the path the walk carried
  it to, so a member lost by a path the same entry renamed still demands its remap;
- a path whose value domain **narrowed** — its type stopped accepting what it accepted, or a bound
  tightened — is looked up the same way and demands the same accounting, because a change that
  keeps every path and every spelling still breaks the file that carries an out-of-domain value;
- everything the new fingerprint has and the walk does not is a genuine addition, which needs no
  operation because the defaults layer absorbs it.

What this module deliberately does **not** check is what an operation may say in the first place —
that its source is removed material, that it does not reach into user key space, that a `safe`
remap cannot fire on a current file. Those are static properties of the ledger against the
checked-in chain, they need no live model, and they live in `ledger_check.py`, which is the half
of the apparatus that runs in `agent-check`.

See `docs/migration-ledger.md` → "Legality rules" and "The checks".
"""

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from pipelex.migration.fingerprint import PATH_SEPARATOR, TABLE_TYPE, SurfaceFingerprint, compute_fingerprint
from pipelex.migration.goldens import defaults_golden_path, read_fingerprint_golden
from pipelex.migration.ledger import MigrationEntry, MigrationLedger, MigrationSafety, load_ledger
from pipelex.migration.narrowing import describe_narrowing, lost_enumerated_spellings
from pipelex.migration.surfaces import Surface, SurfaceRegistry
from pipelex.migration.walk import EntryWalk, walk_entry
from pipelex.suggested_fix import WILDCARD_SEGMENT


class CoverageIssueKind(StrEnum):
    """Why a surface failed the gate. Distinct kinds so a red gate says which guarantee broke."""

    LEDGER_DISAGREES_WITH_REGISTRY = "ledger_disagrees_with_registry"
    GOLDEN_MISSING = "golden_missing"
    SNAPSHOT_PENDING = "snapshot_pending"
    FINGERPRINT_DRIFTED = "fingerprint_drifted"
    REMOVAL_NEEDS_A_BUMP = "removal_needs_a_bump"
    DEAD_OP = "dead_op"
    DESTINATION_OCCUPIED = "destination_occupied"
    UNACCOUNTED_PATH = "unaccounted_path"
    OVER_DELETION = "over_deletion"
    ENUM_MEMBER_NOT_REMAPPED = "enum_member_not_remapped"
    VALUE_DOMAIN_NARROWED = "value_domain_narrowed"
    REQUIRED_PATH_WITHOUT_DEFAULT = "required_path_without_default"
    PRE_HISTORY_HAS_A_DIFF = "pre_history_has_a_diff"


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
    narrowed_paths: dict[str, list[str]] = Field(default_factory=dict[str, list[str]])
    """Paths whose value domain shrank without losing the path or an enumerated member, mapped to
    the reasons. Every one is also in `changed_paths` — what this adds is the *direction*, which is
    what separates a change a user's file survives from one it does not."""

    @property
    def is_empty(self) -> bool:
        return not (self.added_paths or self.removed_paths or self.changed_paths or self.added_enum_members or self.removed_enum_members)

    @property
    def has_removals(self) -> bool:
        return bool(self.removed_paths or self.removed_enum_members)

    def render_removals(self) -> str:
        return str(self.removed_paths + [f"{path}: {members}" for path, members in self.removed_enum_members.items()])

    def render_narrowings(self) -> str:
        return "; ".join(f"'{path}' ({', '.join(reasons)})" for path, reasons in self.narrowed_paths.items())


def diff_fingerprints(*, before: SurfaceFingerprint, after: SurfaceFingerprint) -> FingerprintDiff:
    before_paths = before.path_names()
    after_paths = after.path_names()
    shared = sorted(before_paths & after_paths)

    added_enum_members: dict[str, list[str]] = {}
    removed_enum_members: dict[str, list[str]] = {}
    narrowed_paths: dict[str, list[str]] = {}
    changed_paths: list[str] = []
    for path in shared:
        before_record = before.paths[path]
        after_record = after.paths[path]
        if before_record != after_record:
            changed_paths.append(path)
        if added := sorted(set(after_record.enum_members or []) - set(before_record.enum_members or [])):
            added_enum_members[path] = added
        if removed := lost_enumerated_spellings(before=before_record, after=after_record):
            removed_enum_members[path] = removed
        if narrowing := describe_narrowing(before=before_record, after=after_record):
            narrowed_paths[path] = narrowing

    return FingerprintDiff(
        added_paths=sorted(after_paths - before_paths),
        removed_paths=sorted(before_paths - after_paths),
        changed_paths=changed_paths,
        added_enum_members=added_enum_members,
        removed_enum_members=removed_enum_members,
        narrowed_paths=narrowed_paths,
    )


def check_entry_accounting(*, surface_id: str, entry: MigrationEntry, before: SurfaceFingerprint, after: SurfaceFingerprint) -> list[CoverageIssue]:
    """Verify that one entry says exactly what the fingerprint diff shows happened."""
    if entry.pre_history:
        return _check_the_pre_history_claim(surface_id=surface_id, entry=entry, before=before, after=after)

    issues: list[CoverageIssue] = []
    walk = walk_entry(entry=entry, before=before)

    for description in walk.dead_ops:
        issues.append(CoverageIssue(surface_id=surface_id, kind=CoverageIssueKind.DEAD_OP, message=f"entry '{entry.id}': {description}"))
    if entry.safety is MigrationSafety.SAFE:
        # An unsafe entry is reported and never applied, so its operations never conflict.
        for description in walk.occupied_destinations:
            issues.append(
                CoverageIssue(surface_id=surface_id, kind=CoverageIssueKind.DESTINATION_OCCUPIED, message=f"entry '{entry.id}': {description}")
            )

    after_paths = after.path_names()
    before_paths = before.path_names()
    end_paths = walk.state.current_paths()

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

    for origin, landing in sorted(_over_deleted_landings(before_paths=before_paths, walk=walk).items()):
        if landing not in after_paths or landing in end_paths:
            continue
        where = f"'{origin}'" if landing == origin else f"'{origin}' (which is '{landing}' at schema version {after.schema_version})"
        issues.append(
            CoverageIssue(
                surface_id=surface_id,
                kind=CoverageIssueKind.OVER_DELETION,
                message=(
                    f"entry '{entry.id}': its operations remove {where}, but schema version {after.schema_version} still has it — "
                    f"an operation targets a parent where it meant to target one child"
                ),
            )
        )

    issues.extend(_check_enum_accounting(surface_id=surface_id, entry=entry, before=before, after=after, walk=walk))
    issues.extend(_check_narrowing_accounting(surface_id=surface_id, entry=entry, before=before, after=after, walk=walk))
    return issues


def _over_deleted_landings(*, before_paths: set[str], walk: EntryWalk) -> dict[str, str]:
    """For every path the entry's operations remove, the path it *would* have had at the new schema.

    Compared by origin, like every other accounting here: a child deleted beneath a table the same
    entry renamed is spelled one way in the previous fingerprint and another in the next, and a
    comparison by current spelling never lines the two up — the deletion of a path the new schema
    still has would pass as the disappearance of one path and the appearance of an unrelated
    other. So each removed origin is carried through its nearest surviving ancestor's rename, and
    it is that landing the caller looks for in the new schema.
    """
    landings: dict[str, str] = {}
    for origin in before_paths:
        if walk.state.final_path_of_origin(origin=origin) is not None:
            continue
        segments = origin.split(PATH_SEPARATOR)
        landing = origin
        for depth in range(len(segments) - 1, 0, -1):
            ancestor = PATH_SEPARATOR.join(segments[:depth])
            ancestor_landing = walk.state.final_path_of_origin(origin=ancestor)
            if ancestor_landing is not None:
                landing = PATH_SEPARATOR.join([ancestor_landing, *segments[depth:]])
                break
        landings[origin] = landing
    return landings


def _check_the_pre_history_claim(
    *,
    surface_id: str,
    entry: MigrationEntry,
    before: SurfaceFingerprint,
    after: SurfaceFingerprint,
) -> list[CoverageIssue]:
    """A pre-history entry claims its change is invisible here, and that claim is checkable.

    The flag says the change predates the first fingerprint, so there is no diff to account the
    entry against — which is precisely why the accounting above cannot run and precisely why the
    flag must not be taken on trust. What replaces the accounting is the claim itself: **the
    fingerprint pair must show no removal at all.** A removal between these two snapshots is a
    change that *does* have an observed diff, and the flag would be exempting it from the only
    gate that would have demanded an operation for it.

    Additions are not the flag's business, here as everywhere: the defaults layer absorbs them.

    A narrowed value domain is the same defect reached from the other side and is refused the same
    way: the paths all survive, so nothing is *removed*, but a file valid at the previous version
    stops validating at this one — which is a change with an observed diff, and the flag would
    exempt it from the accounting that would have demanded a remap or an `unsafe` marking for it.

    What the declaration itself says, and whether the operations stay inside it, is `check-ledger`'s
    to verify against the checked-in chain; what the entry does to the hand-authored `before`
    document is the transform check's, inside `check-migration-schemas`. Neither needs the diff
    this function reads, and this function exists to look at that diff.
    """
    diff = diff_fingerprints(before=before, after=after)
    if not diff.has_removals and not diff.narrowed_paths:
        return []
    observed = diff.render_removals() if diff.has_removals else diff.render_narrowings()
    return [
        CoverageIssue(
            surface_id=surface_id,
            kind=CoverageIssueKind.PRE_HISTORY_HAS_A_DIFF,
            message=(
                f"entry '{entry.id}' is marked pre_history, but between schema versions {before.schema_version} and "
                f"{after.schema_version} a file already valid at the older one stops validating: {observed}. That change is "
                f"observable here, so the flag would exempt it from the accounting it needs. Drop the flag and account for it; "
                f"the flag is for material that predates the first fingerprint, which by definition no snapshot shows going away"
            ),
        )
    ]


def _check_enum_accounting(
    *,
    surface_id: str,
    entry: MigrationEntry,
    before: SurfaceFingerprint,
    after: SurfaceFingerprint,
    walk: EntryWalk,
) -> list[CoverageIssue]:
    """Every enumerated spelling the entry loses must be remapped, following the path through the entry's own renames.

    Members are compared by *origin*: an enumerated path of the previous schema is looked up at
    the path the walk carried it to. A comparison over shared names would never look at a path
    the same entry renamed, and would let a lost member ride into the new schema unremapped.
    """
    if entry.safety is MigrationSafety.UNSAFE:
        # An unsafe entry is reported and never applied, so it is allowed to describe a change no
        # operation can make. That is what `unsafe` is for.
        return []
    remapped_by_origin: dict[str, set[str]] = {}
    for remap in walk.remaps:
        remapped_by_origin.setdefault(remap.origin_path, set()).update(remap.old_values)

    issues: list[CoverageIssue] = []
    for origin, before_record in before.paths.items():
        if not before_record.enum_members:
            continue
        final_path = walk.state.final_path_of_origin(origin=origin)
        after_record = after.paths.get(final_path) if final_path is not None else None
        if after_record is None:
            # The path does not survive into the new schema; the unaccounted-path or over-deletion
            # check has already said so in terms the author can act on.
            continue
        removed_members = set(lost_enumerated_spellings(before=before_record, after=after_record))
        unaccounted = sorted(removed_members - remapped_by_origin.get(origin, set()))
        if unaccounted:
            issues.append(
                CoverageIssue(
                    surface_id=surface_id,
                    kind=CoverageIssueKind.ENUM_MEMBER_NOT_REMAPPED,
                    message=(
                        f"entry '{entry.id}': '{final_path}' no longer accepts {unaccounted} — a file carrying one of those "
                        f"values no longer validates, so the entry needs a remap_value for each, or must be marked unsafe"
                    ),
                )
            )
    return issues


def _check_narrowing_accounting(
    *,
    surface_id: str,
    entry: MigrationEntry,
    before: SurfaceFingerprint,
    after: SurfaceFingerprint,
    walk: EntryWalk,
) -> list[CoverageIssue]:
    """Every path whose value domain the entry narrows must carry a remap, or the entry must be unsafe.

    Paths are compared by *origin*, exactly as enumerated members are: a path the same entry
    renamed is looked up where the walk carried it, so a narrowing hidden behind a rename still
    demands its accounting instead of slipping through as an unrelated addition and removal.

    Only two remedies exist, because no structural operation can repair a value the new schema
    refuses. A `remap_value` is the real fix where the old spellings can be enumerated and the
    remap legality rule accepts it — a free string becoming enum-typed is the case that fits.
    Everywhere else, a tightened numeric bound above all, the entry has to say `unsafe`: the
    migration is then reported to the user and never applied, which is the honest answer when the
    tool cannot tell a stale value from a deliberate one.
    """
    if entry.safety is MigrationSafety.UNSAFE:
        # An unsafe entry is reported and never applied, so it is allowed to describe a change no
        # operation can make. That is what `unsafe` is for.
        return []
    remapped_origins = {remap.origin_path for remap in walk.remaps}

    issues: list[CoverageIssue] = []
    for origin, before_record in before.paths.items():
        final_path = walk.state.final_path_of_origin(origin=origin)
        after_record = after.paths.get(final_path) if final_path is not None else None
        if after_record is None:
            # The path does not survive into the new schema; the unaccounted-path or over-deletion
            # check has already said so in terms the author can act on.
            continue
        # A remap rewrites spellings, so it answers for a string-typed member the type stopped
        # accepting — and for nothing else. A lost numeric member, or a bound tightened on the same
        # path, is still a value no mapping can repair, and must not ride under the remap into a
        # `safe` entry.
        reasons = describe_narrowing(before=before_record, after=after_record, remapped=origin in remapped_origins)
        if not reasons:
            continue
        issues.append(
            CoverageIssue(
                surface_id=surface_id,
                kind=CoverageIssueKind.VALUE_DOMAIN_NARROWED,
                message=(
                    f"entry '{entry.id}': '{final_path}' accepts fewer values than it did — {', '.join(reasons)}. A file "
                    f"carrying one of the values it has stopped accepting no longer validates, and no structural operation "
                    f"can repair a value, so the entry needs a remap_value for that path, or must be marked unsafe"
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

    breaking: list[CoverageIssue] = []
    if diff.has_removals:
        breaking.append(
            CoverageIssue(
                surface_id=surface_id,
                kind=CoverageIssueKind.REMOVAL_NEEDS_A_BUMP,
                message=(
                    f"the models no longer have {diff.render_removals()}, which breaks every file that carries them. Bump "
                    f"current_schema_version to {current_version + 1}, add the entry '{surface_id}@{current_version + 1}' "
                    f"accounting for each, then run `make umig`"
                ),
            )
        )
    if diff.narrowed_paths:
        # A narrowing keeps every path and every enumerated spelling, so the diff looks additive
        # and would otherwise be answered with "regenerate the golden" — while a value a user's
        # file legitimately carries has stopped validating.
        breaking.append(
            CoverageIssue(
                surface_id=surface_id,
                kind=CoverageIssueKind.REMOVAL_NEEDS_A_BUMP,
                message=(
                    f"the models still have every path, but they accept fewer values than the golden records: "
                    f"{diff.render_narrowings()}. A file valid before this change is not valid after it, so this is a "
                    f"removal like any other. Bump current_schema_version to {current_version + 1}, add the entry "
                    f"'{surface_id}@{current_version + 1}' carrying a remap_value for each narrowed path — or marked "
                    f"unsafe, where no remap can express it — then run `make umig`"
                ),
            )
        )
    if breaking:
        return breaking
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
