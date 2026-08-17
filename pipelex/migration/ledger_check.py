"""The ledger check — is what the ledger *says* legal, and is replaying it harmless?

This is the half of the migration apparatus that reads nothing but checked-in files: the ledgers,
the golden chain, and the two reference documents. It never fingerprints a live model, and that
restraint is the whole reason it can live in `make agent-check`. A check that read the models
would go red on an ordinary configuration edit with "regenerate the golden" as its remedy — the
fail-regenerate-fail cycle that keeps the coverage gate out of the loop agents run constantly.
Here, every failure is a statement about files the author wrote, and every remedy is to fix one.

The questions, each with its own failure kind:

- **Op legality.** An operation's source must be material some schema version *removed*. One
  addressing a live path would fire on a perfectly valid current file, and replay neutrality —
  the premise that lets us replay the whole ledger over every file forever — would be false.
- **Open-node addressing.** The keys beneath an open mapping belong to the user and are
  unbounded, so no operation may name one; `*` stands for "each of these" and is legal exactly
  at an open node, nowhere else.
- **Remap legality.** A `safe` remap must be provably unable to fire on a current-valid file:
  its target enumerated at the new schema, and every old spelling now outside the member set.
- **Pre-history declarations.** An entry claiming its change predates the first fingerprint must
  declare material no fingerprint records, and may address nothing outside that declaration —
  otherwise the flag, which exempts an entry from being accounted against a diff, would be a way
  to opt out of accounting for a change that has one.
- **Narrowing declarations.** An `unsafe` entry's `declared_narrowed_paths` is what the engine
  questions a document about, so every declared path must be one the fingerprint at the entry's
  own version records. A path that version does not have is questioned of every file and found in
  none — the entry would be, once more, reported to nobody.
- **Convergence.** Replaying the whole ledger over each reference document must apply nothing
  and return the very bytes it was given.

Plus one refusal that outlives them all: a **reserved path** — anything a ledger entry ever
removed — may not come back, because that would make removed material legal again.

See `docs/migration-ledger.md` → "Legality rules" and "The checks".
"""

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from pipelex.migration.engine import replay_ledger_over_text
from pipelex.migration.fingerprint import PATH_SEPARATOR, SurfaceFingerprint
from pipelex.migration.goldens import read_fingerprint_golden
from pipelex.migration.ledger import INITIAL_SCHEMA_VERSION, MigrationEntry, MigrationLedger, load_ledger
from pipelex.migration.plan import BlockedEntryReason
from pipelex.migration.reserved import ReservedRegistry, derive_reserved_registry
from pipelex.migration.safety import MigrationSafety
from pipelex.migration.surfaces import Surface, SurfaceRegistry
from pipelex.migration.walk import EntryWalk, WalkedOp, op_source_path, walk_entry
from pipelex.suggested_fix import WILDCARD_SEGMENT, MigrationOp, RemapValueOp


class LedgerIssueKind(StrEnum):
    """Why a ledger failed the check. Distinct kinds so a red gate says which guarantee broke."""

    CHAIN_INCOMPLETE = "chain_incomplete"
    OP_ACTS_ON_LIVE_MATERIAL = "op_acts_on_live_material"
    CONCRETE_KEY_UNDER_OPEN_NODE = "concrete_key_under_open_node"
    WILDCARD_NOT_AT_OPEN_NODE = "wildcard_not_at_open_node"
    ILLEGAL_REMAP = "illegal_remap"
    RESERVED_PATH_REUSED = "reserved_path_reused"
    RESERVED_VALUE_REUSED = "reserved_value_reused"
    PRE_HISTORY_PATH_IS_RECORDED = "pre_history_path_is_recorded"
    DECLARED_NARROWED_PATH_IS_ABSENT = "declared_narrowed_path_is_absent"
    CONVERGENCE_BROKEN = "convergence_broken"


class LedgerIssue(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    surface_id: str
    kind: LedgerIssueKind = Field(strict=False)
    message: str


def check_ledgers(*, registry: SurfaceRegistry, migration_dir: Path) -> list[LedgerIssue]:
    """Run the ledger check over every surface in a registry."""
    issues: list[LedgerIssue] = []
    for surface in registry.surfaces:
        issues.extend(check_ledger(surface=surface, migration_dir=migration_dir))
    return issues


def check_ledger(*, surface: Surface, migration_dir: Path) -> list[LedgerIssue]:
    """Run the whole ledger check over one surface.

    Raises:
        MigrationLedgerError: the ledger is missing, unparseable, or internally inconsistent —
            which covers the contract's *parses into migration operations* and *versions are
            contiguous and match ids*, both enforced when the file is read.
        MigrationGoldenError: a golden in the chain cannot be read as the link its name claims.
    """
    surface_id = surface.surface_id
    ledger = load_ledger(migration_dir=migration_dir, surface_id=surface_id)
    chain = _read_chain(surface_id=surface_id, ledger=ledger, migration_dir=migration_dir)
    reserved = derive_reserved_registry(surface_id=surface_id, ledger=ledger, migration_dir=migration_dir)

    issues = _check_chain_is_complete(surface_id=surface_id, ledger=ledger, chain=chain)
    issues.extend(_check_entries(surface_id=surface_id, ledger=ledger, chain=chain, reserved=reserved))
    issues.extend(_check_reserved_paths_stay_retired(surface_id=surface_id, ledger=ledger, chain=chain, reserved=reserved))
    issues.extend(_check_convergence(surface=surface, ledger=ledger))
    return issues


def _read_chain(*, surface_id: str, ledger: MigrationLedger, migration_dir: Path) -> dict[int, SurfaceFingerprint]:
    """Every stored link of the surface's golden chain, keyed by schema version.

    Only what is on disk: a missing link is absent from the mapping rather than substituted, so
    that no check ever compares an entry against a shape nobody snapshotted.
    """
    chain: dict[int, SurfaceFingerprint] = {}
    for schema_version in range(INITIAL_SCHEMA_VERSION, ledger.surface.current_schema_version + 1):
        stored = read_fingerprint_golden(migration_dir=migration_dir, surface_id=surface_id, schema_version=schema_version)
        if stored is not None:
            chain[schema_version] = stored
    return chain


def _check_chain_is_complete(*, surface_id: str, ledger: MigrationLedger, chain: dict[int, SurfaceFingerprint]) -> list[LedgerIssue]:
    """Say once, loudly, which links are missing — every entry check below needs a pair of them."""
    current_version = ledger.surface.current_schema_version
    missing = [schema_version for schema_version in range(INITIAL_SCHEMA_VERSION, current_version + 1) if schema_version not in chain]
    if not missing:
        return []
    versions = ", ".join(str(schema_version) for schema_version in missing)
    plural = len(missing) > 1
    return [
        LedgerIssue(
            surface_id=surface_id,
            kind=LedgerIssueKind.CHAIN_INCOMPLETE,
            message=(
                f"no fingerprint golden for schema {'versions' if plural else 'version'} {versions}, so the entries that change "
                f"{'those shapes' if plural else 'that shape'} cannot be checked against them — run `make umig` if the current "
                f"version was just bumped; a gap below version {current_version} is a broken chain and the missing link has to "
                f"be restored"
            ),
        )
    ]


def _check_entries(
    *,
    surface_id: str,
    ledger: MigrationLedger,
    chain: dict[int, SurfaceFingerprint],
    reserved: ReservedRegistry,
) -> list[LedgerIssue]:
    issues: list[LedgerIssue] = []
    for entry in ledger.migration:
        before = chain.get(entry.to_schema_version - 1)
        after = chain.get(entry.to_schema_version)
        if before is None or after is None:
            # The chain check above already named the missing link and its remedy. Checking the
            # entry against a shape nobody snapshotted would blame the entry for that gap.
            continue
        issues.extend(_check_narrowing_declaration(surface_id=surface_id, entry=entry, after=after))
        if entry.pre_history:
            issues.extend(_check_pre_history_entry(surface_id=surface_id, entry=entry, chain=chain, before=before, after=after, reserved=reserved))
            continue
        walk = walk_entry(entry=entry, before=before)
        issues.extend(_check_op_legality(surface_id=surface_id, entry=entry, before=before, walk=walk, reserved=reserved))
        issues.extend(_check_remap_legality(surface_id=surface_id, entry=entry, after=after, walk=walk))
    return issues


def _check_narrowing_declaration(*, surface_id: str, entry: MigrationEntry, after: SurfaceFingerprint) -> list[LedgerIssue]:
    """Every declared narrowed path is one the entry's own version records.

    A narrowing is a path that *survives* with a smaller value domain, so the fingerprint at the
    entry's own version has it — that is what distinguishes a narrowing from a removal, which the
    coverage gate accounts against the diff and which no declaration may stand in for. It is also
    what makes the declaration answerable: the engine looks these paths up in the user's document,
    and one no version records is looked for in every file and found in none, which puts the entry
    right back where R9 found it — accepted by the accounting, reported to nobody.
    """
    issues: list[LedgerIssue] = []
    for path in entry.declared_narrowed_paths:
        if path in after.paths:
            continue
        issues.append(
            LedgerIssue(
                surface_id=surface_id,
                kind=LedgerIssueKind.DECLARED_NARROWED_PATH_IS_ABSENT,
                message=(
                    f"entry '{entry.id}' declares '{path}' as narrowed, but schema version {after.schema_version} has no such "
                    f"path — a narrowing keeps its path and shrinks what it accepts, so this is either a misspelling or a "
                    f"removal, and a removal is accounted for by the operation that removes it. Spell the path as the "
                    f"fingerprint at version {after.schema_version} records it, '{WILDCARD_SEGMENT}' segments included"
                ),
            )
        )
    return issues


def _check_pre_history_entry(
    *,
    surface_id: str,
    entry: MigrationEntry,
    chain: dict[int, SurfaceFingerprint],
    before: SurfaceFingerprint,
    after: SurfaceFingerprint,
    reserved: ReservedRegistry,
) -> list[LedgerIssue]:
    """What a pre-history entry is verified against, since no fingerprint pair describes it.

    The flag says the change predates the first fingerprint, so the entry's own declaration stands
    in for the diff and the checks are stated over that declaration instead:

    - **Every declared path really is invisible to the chain.** A path some fingerprint records is
      material a snapshot describes, so the change that removed it has an ordinary diff and must be
      accounted against it. Were the declaration allowed to name a recorded path, the flag would be
      a way to opt out of accounting entirely — the escape hatch this contract refuses.
    - **Every operation acts on declared material.** The ordinary rule is that a source must be a
      path some version removed, read from the reserved registry; for a pre-history source the
      registry is fed by the declaration, so the same rule holds and the same failure is reported.
      Without it the entry could reach for a live path, and replay neutrality would be false.

    Remap legality is unchanged and is checked against the literal path: a `remap_value` retires a
    *spelling*, so its path survives into the new schema, and none of this entry's renames can have
    moved it — they act on material no fingerprint records.

    The walk is not run at all. It replays an entry over the previous fingerprint's path set, and a
    pre-history entry addresses paths that set never had, so every operation would be reported dead.
    """
    issues = _check_declared_paths_are_invisible_to_the_chain(surface_id=surface_id, entry=entry, chain=chain)
    for op in entry.ops:
        issues.extend(_check_open_node_addressing(surface_id=surface_id, entry=entry, op=op, origin_path=op_source_path(op=op), before=before))
        issues.extend(_check_pre_history_source_is_declared_material(surface_id=surface_id, entry=entry, op=op, reserved=reserved))
    if entry.safety is MigrationSafety.SAFE:
        for op in entry.ops:
            if isinstance(op, RemapValueOp):
                issues.extend(
                    _check_one_remap(
                        surface_id=surface_id,
                        entry=entry,
                        after=after,
                        final_path=op_source_path(op=op),
                        old_values=sorted(op.mapping),
                        new_values=sorted(set(op.mapping.values())),
                    )
                )
    return issues


def _check_declared_paths_are_invisible_to_the_chain(
    *,
    surface_id: str,
    entry: MigrationEntry,
    chain: dict[int, SurfaceFingerprint],
) -> list[LedgerIssue]:
    """No declared path may appear in a fingerprint at or below the entry's own version.

    A later version bringing one back is a different failure with a different remedy, and the
    reserved-path check reports it in those terms.
    """
    issues: list[LedgerIssue] = []
    for path in entry.declared_removed_paths:
        recorded_at = sorted(version for version, fingerprint in chain.items() if version <= entry.to_schema_version and path in fingerprint.paths)
        if recorded_at:
            issues.append(
                LedgerIssue(
                    surface_id=surface_id,
                    kind=LedgerIssueKind.PRE_HISTORY_PATH_IS_RECORDED,
                    message=(
                        f"entry '{entry.id}' declares '{path}' as removed before the first fingerprint, but schema "
                        f"{'versions' if len(recorded_at) > 1 else 'version'} {', '.join(str(version) for version in recorded_at)} "
                        f"records it. A pre-history declaration stands in for a diff nobody can observe, so material a snapshot "
                        f"does describe has to be accounted against that snapshot like any other change"
                    ),
                )
            )
    return issues


def _check_pre_history_source_is_declared_material(
    *,
    surface_id: str,
    entry: MigrationEntry,
    op: MigrationOp,
    reserved: ReservedRegistry,
) -> list[LedgerIssue]:
    """A pre-history operation's source must be declared material, or lie beneath some.

    Beneath, because a declaration names the shape that retired and an operation may address one
    key inside it — declaring the parent is the honest record of what went away, and enumerating
    every leaf under it would add nothing a reader could act on.
    """
    if isinstance(op, RemapValueOp):
        return []
    source = op_source_path(op=op)
    removed_at = _reserved_at_or_above(reserved=reserved, path=source)
    if removed_at is not None and removed_at <= entry.to_schema_version:
        return []
    return [
        LedgerIssue(
            surface_id=surface_id,
            kind=LedgerIssueKind.OP_ACTS_ON_LIVE_MATERIAL,
            message=(
                f"entry '{entry.id}': {op.kind} acts on '{source}', which no schema version up to {entry.to_schema_version} "
                f"removes and this entry does not declare either — a pre-history entry's declaration is the only record of "
                f"what it may address, so an operation outside it would fire on material nothing retired"
            ),
        )
    ]


def _reserved_at_or_above(*, reserved: ReservedRegistry, path: str) -> int | None:
    """The version that retired this path, or the nearest ancestor of it that a version retired."""
    segments = path.split(PATH_SEPARATOR)
    for depth in range(len(segments), 0, -1):
        removed_at = reserved.reserved_at(path=PATH_SEPARATOR.join(segments[:depth]))
        if removed_at is not None:
            return removed_at
    return None


def _check_op_legality(
    *,
    surface_id: str,
    entry: MigrationEntry,
    before: SurfaceFingerprint,
    walk: EntryWalk,
    reserved: ReservedRegistry,
) -> list[LedgerIssue]:
    """What an operation may address: removed material, and never a user's own key."""
    issues: list[LedgerIssue] = []
    for walked, op in zip(walk.walked_ops, entry.ops, strict=True):
        issues.extend(_check_open_node_addressing(surface_id=surface_id, entry=entry, op=op, origin_path=walked.origin_path, before=before))
        issues.extend(_check_source_is_removed_material(surface_id=surface_id, entry=entry, op=op, walked=walked, reserved=reserved))
    return issues


def _check_source_is_removed_material(
    *,
    surface_id: str,
    entry: MigrationEntry,
    op: MigrationOp,
    walked: WalkedOp,
    reserved: ReservedRegistry,
) -> list[LedgerIssue]:
    """Every structural operation acts on a path some schema version removed, or it is illegal.

    A `remap_value` is exempt by construction: what it retires is an enumerated *spelling*, not
    the path, which survives into the new schema and must — remap legality is what governs it.

    An operation whose source the fingerprint does not record at all is left alone here: it is
    either dead, which the coverage gate reports against the diff it belongs to, or it reaches
    into user key space, which the open-node check above reports in the terms that matter.
    """
    if isinstance(op, RemapValueOp) or not walked.source_was_recorded:
        return []
    removed_at = reserved.reserved_at(path=walked.origin_path)
    if removed_at is not None and removed_at <= entry.to_schema_version:
        return []
    return [
        LedgerIssue(
            surface_id=surface_id,
            kind=LedgerIssueKind.OP_ACTS_ON_LIVE_MATERIAL,
            message=(
                f"entry '{entry.id}': {op.kind} acts on '{walked.origin_path}', which no schema version up to "
                f"{entry.to_schema_version} removes — so it would fire on a valid current file and rewrite material the "
                f"schema still has. An operation may only act on what a schema version retired"
            ),
        )
    ]


def _check_open_node_addressing(
    *,
    surface_id: str,
    entry: MigrationEntry,
    op: MigrationOp,
    origin_path: str,
    before: SurfaceFingerprint,
) -> list[LedgerIssue]:
    """`*` exactly at an open node, and never a concrete key beneath one.

    **The document root is one of the nodes this rule reads.** For most surfaces it is closed: the
    root keys of `pipelex.toml` are ours and enumerable, so a `*` there addresses nothing. For a
    backend definition file the root keys are model names the user chose, and then `*` at the root is
    the only legal address for the whole file — while naming one of those tables is the same defect
    as reaching inside an open mapping, and is reported as one.

    The check runs on the source traced back to the previous fingerprint's spelling, so that an
    operation acting inside a table an earlier operation in the same entry renamed is judged
    against the node it really addresses. A pre-history source has no such spelling to trace back
    to and is judged as written, which is the right answer for both halves: no fingerprint records
    the node, so nothing can confirm that a `*` stands at an open one, and nothing claims the keys
    beneath it are the user's either.

    Sources only, as the contract states them. A *destination* landing in user key space needs no
    rule of its own: a concrete key beneath an open node is never a path of any fingerprint, so
    the coverage gate's containment check reports it as a destination the new schema does not
    have — the same defect, named where the author is already looking.
    """
    issues: list[LedgerIssue] = []
    segments = origin_path.split(PATH_SEPARATOR)
    for index, segment in enumerate(segments):
        parent_path = PATH_SEPARATOR.join(segments[:index])
        if index:
            parent_record = before.paths.get(parent_path)
            parent_is_open = parent_record is not None and parent_record.open_node
        else:
            # The first segment's parent is the document itself, which has no record of its own — its
            # openness is a property of the whole fingerprint. Both halves of the rule then hold at
            # the root for free: `*` is legal there for a backend definition file, and naming one
            # root table of one is a concrete key under an open node, which is exactly right — those
            # keys are the model names that machine chose.
            parent_is_open = before.document_root_is_open
        if segment == WILDCARD_SEGMENT and not parent_is_open:
            parent_label = f"'{parent_path}'" if parent_path else "the document root"
            issues.append(
                LedgerIssue(
                    surface_id=surface_id,
                    kind=LedgerIssueKind.WILDCARD_NOT_AT_OPEN_NODE,
                    message=(
                        f"entry '{entry.id}': {op.kind} addresses '{origin_path}', but {parent_label} is not an open "
                        f"mapping at schema version {before.schema_version} — '{WILDCARD_SEGMENT}' stands for every key of an "
                        f"open node and means nothing anywhere else"
                    ),
                )
            )
        elif segment != WILDCARD_SEGMENT and parent_is_open:
            issues.append(
                LedgerIssue(
                    surface_id=surface_id,
                    kind=LedgerIssueKind.CONCRETE_KEY_UNDER_OPEN_NODE,
                    message=(
                        f"entry '{entry.id}': {op.kind} addresses '{origin_path}', but the keys under '{parent_path}' are "
                        f"the user's and unbounded, so no schema change can remove one — address every entry with "
                        f"'{WILDCARD_SEGMENT}' instead of naming '{segment}'"
                    ),
                )
            )
    return issues


def _check_remap_legality(
    *,
    surface_id: str,
    entry: MigrationEntry,
    after: SurfaceFingerprint,
    walk: EntryWalk,
) -> list[LedgerIssue]:
    """A `safe` remap must be provably unable to fire on a current-valid file.

    That holds when the target is enumerated at the new schema and every old spelling in the
    mapping now falls outside its member set. When an old spelling remains legal — or the path is
    a free string, where staleness can never be proven from the schema — the applier cannot tell a
    stale value from a deliberate choice, and the entry has to be `unsafe`.
    """
    if entry.safety is MigrationSafety.UNSAFE:
        return []

    issues: list[LedgerIssue] = []
    for remap in walk.remaps:
        final_path = walk.state.final_path_of_origin(origin=remap.origin_path)
        if final_path is None:
            continue
        issues.extend(
            _check_one_remap(
                surface_id=surface_id,
                entry=entry,
                after=after,
                final_path=final_path,
                old_values=remap.old_values,
                new_values=remap.new_values,
            )
        )
    return issues


def _check_one_remap(
    *,
    surface_id: str,
    entry: MigrationEntry,
    after: SurfaceFingerprint,
    final_path: str,
    old_values: list[str],
    new_values: list[str],
) -> list[LedgerIssue]:
    """The rule itself, over one remap whose destination path is already resolved.

    Resolved differently by each caller and for the same reason: an ordinary entry's remap may sit
    on a path that entry renamed, so the walk says where it ended up, while a pre-history entry's
    renames act on material no fingerprint records and therefore cannot have moved it.
    """
    record = after.paths.get(final_path)
    if record is None:
        # The path the remap targets does not survive into the new schema; the coverage gate's
        # unaccounted-path or over-deletion check says so in terms the author can act on.
        return []
    member_set = set(record.enum_members or [])
    if not member_set:
        return [
            LedgerIssue(
                surface_id=surface_id,
                kind=LedgerIssueKind.ILLEGAL_REMAP,
                message=(
                    f"entry '{entry.id}': remap_value on '{final_path}' is 'safe', but that path is not enumerated at "
                    f"schema version {after.schema_version} — staleness cannot be proven from the schema, so the entry must be unsafe"
                ),
            )
        ]

    issues: list[LedgerIssue] = []
    still_legal = sorted(set(old_values) & member_set)
    if still_legal:
        issues.append(
            LedgerIssue(
                surface_id=surface_id,
                kind=LedgerIssueKind.ILLEGAL_REMAP,
                message=(
                    f"entry '{entry.id}': remap_value on '{final_path}' is 'safe', but {still_legal} are still legal values at "
                    f"schema version {after.schema_version} — a user who chose one deliberately would have it rewritten"
                ),
            )
        )
    unknown_new = sorted(set(new_values) - member_set)
    if unknown_new:
        issues.append(
            LedgerIssue(
                surface_id=surface_id,
                kind=LedgerIssueKind.ILLEGAL_REMAP,
                message=(
                    f"entry '{entry.id}': remap_value on '{final_path}' rewrites values to {unknown_new}, which schema version "
                    f"{after.schema_version} does not accept — every migrated file would be rejected, with the tool reporting success"
                ),
            )
        )
    return issues


def _check_reserved_paths_stay_retired(
    *,
    surface_id: str,
    ledger: MigrationLedger,
    chain: dict[int, SurfaceFingerprint],
    reserved: ReservedRegistry,
) -> list[LedgerIssue]:
    """A retired path, and a remapped-away spelling, may never come back.

    Reuse would make removed material legal again on a current file, and every operation that
    retired it would start firing on files that are not stale at all. There is no escape-hatch
    marker: an author who hits the rule picks another name.
    """
    issues: list[LedgerIssue] = []
    for entry in ledger.migration:
        schema_version = entry.to_schema_version
        fingerprint = chain.get(schema_version)
        if fingerprint is None:
            continue
        for path, record in fingerprint.paths.items():
            reserved_at = reserved.reserved_at(path=path)
            if reserved_at is not None and reserved_at < schema_version:
                issues.append(
                    LedgerIssue(
                        surface_id=surface_id,
                        kind=LedgerIssueKind.RESERVED_PATH_REUSED,
                        message=(
                            f"schema version {schema_version} has '{path}' again, but schema version {reserved_at} retired it — "
                            f"a retired path stays retired, because reusing the name makes removed material legal again. "
                            f"Pick another name"
                        ),
                    )
                )
            for member in record.enum_members or []:
                value_reserved_at = reserved.value_reserved_at(path=path, value=member)
                if value_reserved_at is not None and value_reserved_at < schema_version:
                    issues.append(
                        LedgerIssue(
                            surface_id=surface_id,
                            kind=LedgerIssueKind.RESERVED_VALUE_REUSED,
                            message=(
                                f"schema version {schema_version} accepts '{member}' at '{path}' again, but schema version "
                                f"{value_reserved_at} remapped that spelling away — every file still carrying it would be "
                                f"rewritten on every run. Pick another spelling"
                            ),
                        )
                    )
    return issues


def _check_convergence(*, surface: Surface, ledger: MigrationLedger) -> list[LedgerIssue]:
    """Replaying the whole ledger over a current document must do nothing, and say nothing.

    Two witnesses of deliberately different shape: the complete reference document, where every
    key is set, and the sparse kit template, where almost none are. An operation that misbehaves
    on an absent key passes over one and fails over the other.

    Byte identity is asserted as well as emptiness, but only for a replay that reported nothing:
    the engine returns the very string it was given when nothing applies, so a document that came
    back merely equal would mean something applied and was not reported — which is the one failure
    a report cannot describe. Where the replay *did* report something, the changed bytes are that
    finding's consequence and saying it twice adds nothing.

    **One exemption, and it is the narrowest one that leaves R9's shape usable.** An entry reported
    as `VALUE_DOMAIN_NARROWED` is reported because the document *sets* a path whose accepted values
    the entry narrowed — presence, not violation, because the engine is model-free by design and
    the ruling that put the declaration in the ledger is the same ruling that refused to thread a
    model into the engine. A witness at the current schema sets the path like any healthy file
    does, so without the exemption every op-free `unsafe` entry would fail this check and the only
    remedy the coverage gate offers for a tightened bound could never be written. An `unsafe`
    entry whose *operations* fire on a witness is a different matter and still fails: that says the
    checked-in reference document carries retired material.
    """
    issues: list[LedgerIssue] = []
    for label, text in surface.reference_documents():
        replay = replay_ledger_over_text(ledger=ledger, text=text)
        applied = [step.entry_id for step in replay.steps]
        if applied:
            issues.append(
                LedgerIssue(
                    surface_id=surface.surface_id,
                    kind=LedgerIssueKind.CONVERGENCE_BROKEN,
                    message=(
                        f"replaying the ledger over the {label} applies {applied} — a document already at schema version "
                        f"{ledger.surface.current_schema_version} must come through untouched, or every user's current file "
                        f"is rewritten on every run"
                    ),
                )
            )
        blocked = [blocked_entry.entry_id for blocked_entry in replay.blocked if blocked_entry.reason is not BlockedEntryReason.VALUE_DOMAIN_NARROWED]
        if blocked:
            issues.append(
                LedgerIssue(
                    surface_id=surface.surface_id,
                    kind=LedgerIssueKind.CONVERGENCE_BROKEN,
                    message=(
                        f"replaying the ledger over the {label} reports {blocked} as blocked — a document already at the "
                        f"current schema version must give an entry nothing to say, or every user is warned about a file "
                        f"that is perfectly current"
                    ),
                )
            )
        if not applied and not blocked and replay.text is not text:
            issues.append(
                LedgerIssue(
                    surface_id=surface.surface_id,
                    kind=LedgerIssueKind.CONVERGENCE_BROKEN,
                    message=(
                        f"replaying the ledger over the {label} returned a re-serialized document rather than the bytes it was "
                        f"given — something applied without being reported, which is the one failure the plan cannot describe"
                    ),
                )
            )
    return issues
