"""The ledger check — is what the ledger *says* legal, and is replaying it harmless?

This is the half of the migration apparatus that reads nothing but checked-in files: the ledgers,
the golden chain, and the two reference documents. It never fingerprints a live model, and that
restraint is the whole reason it can live in `make agent-check`. A check that read the models
would go red on an ordinary configuration edit with "regenerate the golden" as its remedy — the
fail-regenerate-fail cycle that keeps the coverage gate out of the loop agents run constantly.
Here, every failure is a statement about files the author wrote, and every remedy is to fix one.

Four questions, each with its own failure kind:

- **Op legality.** An operation's source must be material some schema version *removed*. One
  addressing a live path would fire on a perfectly valid current file, and replay neutrality —
  the premise that lets us replay the whole ledger over every file forever — would be false.
- **Open-node addressing.** The keys beneath an open mapping belong to the user and are
  unbounded, so no operation may name one; `*` stands for "each of these" and is legal exactly
  at an open node, nowhere else.
- **Remap legality.** A `safe` remap must be provably unable to fire on a current-valid file:
  its target enumerated at the new schema, and every old spelling now outside the member set.
- **Convergence.** Replaying the whole ledger over each reference document must apply nothing
  and return the very bytes it was given.

Plus one refusal that outlives all four: a **reserved path** — anything a ledger entry ever
removed — may not come back, because that would make removed material legal again.

See `docs/migration-ledger.md` → "Legality rules" and "The checks".
"""

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from pipelex.migration.engine import replay_ledger_over_text
from pipelex.migration.fingerprint import PATH_SEPARATOR, SurfaceFingerprint
from pipelex.migration.goldens import read_fingerprint_golden
from pipelex.migration.ledger import INITIAL_SCHEMA_VERSION, MigrationEntry, MigrationLedger, MigrationSafety, load_ledger
from pipelex.migration.reserved import ReservedRegistry, derive_reserved_registry
from pipelex.migration.surfaces import Surface, SurfaceRegistry
from pipelex.migration.walk import EntryWalk, WalkedOp, walk_entry
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
    PRE_HISTORY_UNVERIFIED = "pre_history_unverified"
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
        if entry.pre_history:
            issues.append(_pre_history_is_not_verified_yet(surface_id=surface_id, entry=entry))
            continue
        before = chain.get(entry.to_schema_version - 1)
        after = chain.get(entry.to_schema_version)
        if before is None or after is None:
            # The chain check above already named the missing link and its remedy. Checking the
            # entry against a shape nobody snapshotted would blame the entry for that gap.
            continue
        walk = walk_entry(entry=entry, before=before)
        issues.extend(_check_op_legality(surface_id=surface_id, entry=entry, before=before, walk=walk, reserved=reserved))
        issues.extend(_check_remap_legality(surface_id=surface_id, entry=entry, after=after, walk=walk))
    return issues


def _pre_history_is_not_verified_yet(*, surface_id: str, entry: MigrationEntry) -> LedgerIssue:
    """A pre-history entry is refused until the check that verifies one exists.

    The flag exempts an entry from the coverage gate, on the grounds that no fingerprint pair
    describes a change that predates the first fingerprint. The contract's answer is that this
    check verifies such an entry against its own `declared_removed_paths` and a hand-authored
    `before` document instead — and that verification does not exist yet. Until it does, the flag
    would be precisely the escape hatch the contract says must not exist, so an entry carrying it
    is refused rather than waved through by two gates in a row.
    """
    return LedgerIssue(
        surface_id=surface_id,
        kind=LedgerIssueKind.PRE_HISTORY_UNVERIFIED,
        message=(
            f"entry '{entry.id}' is marked pre_history, which exempts it from the coverage gate — and the check that verifies "
            f"such an entry against its declared_removed_paths and its hand-authored `before` document is not built yet. "
            f"A pre-history entry no gate verifies is the escape hatch the contract refuses, so it cannot be merged until "
            f"that verification lands with it"
        ),
    )


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
        issues.extend(_check_open_node_addressing(surface_id=surface_id, entry=entry, op=op, walked=walked, before=before))
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
    walked: WalkedOp,
    before: SurfaceFingerprint,
) -> list[LedgerIssue]:
    """`*` exactly at an open node, and never a concrete key beneath one.

    The check runs on the source traced back to the previous fingerprint's spelling, so that an
    operation acting inside a table an earlier operation in the same entry renamed is judged
    against the node it really addresses.

    Sources only, as the contract states them. A *destination* landing in user key space needs no
    rule of its own: a concrete key beneath an open node is never a path of any fingerprint, so
    the coverage gate's containment check reports it as a destination the new schema does not
    have — the same defect, named where the author is already looking.
    """
    issues: list[LedgerIssue] = []
    segments = walked.origin_path.split(PATH_SEPARATOR)
    for index, segment in enumerate(segments):
        parent_path = PATH_SEPARATOR.join(segments[:index])
        parent_record = before.paths.get(parent_path) if index else None
        parent_is_open = parent_record is not None and parent_record.open_node
        if segment == WILDCARD_SEGMENT and not parent_is_open:
            parent_label = f"'{parent_path}'" if parent_path else "the document root"
            issues.append(
                LedgerIssue(
                    surface_id=surface_id,
                    kind=LedgerIssueKind.WILDCARD_NOT_AT_OPEN_NODE,
                    message=(
                        f"entry '{entry.id}': {op.kind} addresses '{walked.origin_path}', but {parent_label} is not an open "
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
                        f"entry '{entry.id}': {op.kind} addresses '{walked.origin_path}', but the keys under '{parent_path}' are "
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
        record = after.paths.get(final_path) if final_path is not None else None
        if record is None:
            # The path the remap targets does not survive into the new schema; the coverage gate's
            # unaccounted-path or over-deletion check says so in terms the author can act on.
            continue
        member_set = set(record.enum_members or [])
        if not member_set:
            issues.append(
                LedgerIssue(
                    surface_id=surface_id,
                    kind=LedgerIssueKind.ILLEGAL_REMAP,
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
                LedgerIssue(
                    surface_id=surface_id,
                    kind=LedgerIssueKind.ILLEGAL_REMAP,
                    message=(
                        f"entry '{entry.id}': remap_value on '{final_path}' is 'safe', but {still_legal} are still legal values at "
                        f"schema version {after.schema_version} — a user who chose one deliberately would have it rewritten"
                    ),
                )
            )
        unknown_new = sorted(set(remap.new_values) - member_set)
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
        blocked = [blocked_entry.entry_id for blocked_entry in replay.blocked]
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
