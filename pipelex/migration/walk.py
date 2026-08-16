"""The sequential path-state walk — replaying an entry's operations symbolically.

An entry's operations chain: a parent is renamed and then keys inside it are renamed, so the
intermediate paths belong to neither the old fingerprint nor the new one, and no ordering avoids
that. Every static check about an entry therefore starts by replaying the entry over the previous
fingerprint's path set, carrying each surviving path together with the path it *originated from*.

The walk lives here rather than inside either gate because both read it, for different questions:
the coverage gate asks what the end state looks like against the new fingerprint, and the ledger
check asks what each individual operation was addressing when it ran. One walk answers both, and
one walk is what keeps the two gates from disagreeing about what an entry does.

See `docs/migration-ledger.md` → "Sequential path state".
"""

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field

from pipelex.migration.fingerprint import PATH_SEPARATOR, TABLE_TYPE, PathFingerprint, SurfaceFingerprint
from pipelex.migration.ledger import MigrationEntry
from pipelex.suggested_fix import DeleteKeyOp, DeleteTableOp, MigrationOp, MoveKeyOp, RemapValueOp, RenameTableKeyOp


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

    def trace_to_origin(self, *, path: str) -> str:
        """A path as the previous fingerprint would have spelled it, on a best-effort basis.

        The exact lookup only answers for paths the fingerprint records, and an operation may
        legitimately address one it does not — a concrete key beneath an open node is the user's
        and is nowhere in any fingerprint. So the longest recorded prefix is traced back and the
        remaining segments are carried along unchanged, which is enough for the ledger check to
        ask whether the operation is addressing user key space.
        """
        segments = path.split(PATH_SEPARATOR)
        for depth in range(len(segments), 0, -1):
            prefix = PATH_SEPARATOR.join(segments[:depth])
            origin = self.origin_by_current.get(prefix)
            if origin is not None:
                return PATH_SEPARATOR.join([origin, *segments[depth:]])
        return path


class RecordedRemap(BaseModel):
    """A remap that fired during the walk, attributed to the schema path it originated from."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    origin_path: str
    old_values: list[str]
    new_values: list[str]


class WalkedOp(BaseModel):
    """One operation, as the walk saw it: what it addressed, and where that came from."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    op_index: int
    source_path: str
    """The path the operation addresses at the moment it runs, after any earlier rename in the
    same entry has moved it."""

    origin_path: str
    """That path traced back to the previous fingerprint's spelling — exact when the fingerprint
    records it, best effort otherwise (see `PathState.trace_to_origin`)."""

    source_was_recorded: bool
    """Whether the fingerprint records the exact source path. False means either a genuinely dead
    operation — which the coverage gate reports — or an operation reaching into user key space,
    which the ledger check reports."""


class EntryWalk(BaseModel):
    """What replaying one entry over the previous fingerprint's path set found out."""

    model_config = ConfigDict(extra="forbid")

    state: PathState
    """The end state."""

    walked_ops: list[WalkedOp] = Field(default_factory=list[WalkedOp])
    """One record per operation, in order, whether or not the operation could fire."""

    dead_ops: list[str] = Field(default_factory=list[str])
    """Descriptions of operations that can never fire: the source is absent, or the operation
    kind cannot act on what the source is."""

    occupied_destinations: list[str] = Field(default_factory=list[str])
    """Descriptions of renames or moves onto a path the state already had. The applier refuses
    to clobber an occupied destination, so a file carrying both keys — a valid file at the old
    schema — would come back CONFLICT on every run."""

    remaps: list[RecordedRemap] = Field(default_factory=list[RecordedRemap])
    """The remaps that fired, attributed to the schema path they originated from."""


def joined(*, segments: Sequence[str]) -> str:
    return PATH_SEPARATOR.join(segments)


def op_source_path(*, op: MigrationOp) -> str:
    """The path an operation acts on. `delete_table`'s `table_path` *is* its target."""
    match op:
        case DeleteTableOp():
            return joined(segments=op.table_path)
        case DeleteKeyOp() | RenameTableKeyOp() | MoveKeyOp() | RemapValueOp():
            return joined(segments=[*op.table_path, op.key])


def walk_entry(*, entry: MigrationEntry, before: SurfaceFingerprint) -> EntryWalk:
    """Replay an entry's operations symbolically over the previous fingerprint's path set."""
    walk = EntryWalk(state=PathState.make_from_fingerprint(fingerprint=before))

    for op_index, op in enumerate(entry.ops):
        source = op_source_path(op=op)
        recorded_origin = walk.state.origin_by_current.get(source)
        walk.walked_ops.append(
            WalkedOp(
                op_index=op_index,
                source_path=source,
                origin_path=recorded_origin if recorded_origin is not None else walk.state.trace_to_origin(path=source),
                source_was_recorded=recorded_origin is not None,
            )
        )
        if recorded_origin is None:
            walk.dead_ops.append(f"{op.kind} on '{source}' — no such path at schema version {before.schema_version}, so it can never fire")
            continue
        origin_record = before.paths[recorded_origin]
        if isinstance(op, DeleteTableOp) and not _is_table_like(record=origin_record):
            walk.dead_ops.append(f"{op.kind} on '{source}' — that path is a key, not a table, so the applier would skip it forever; use delete_key")
            continue
        _apply_op_to_state(op=op, source=source, walk=walk)

    return walk


def _is_table_like(*, record: PathFingerprint) -> bool:
    """Whether the applier's `delete_table` finds a table at this path.

    An open node counts: `dict[str, X]` is a `[table]` in a file, whatever the fingerprint calls
    its value type.
    """
    return record.value_type == TABLE_TYPE or record.open_node


def _apply_op_to_state(*, op: MigrationOp, source: str, walk: EntryWalk) -> None:
    match op:
        case DeleteKeyOp() | DeleteTableOp():
            walk.state.drop_subtree(path=source)
        case RenameTableKeyOp():
            _move_in_state(op=op, source=source, destination=joined(segments=[*op.table_path, op.new_key]), walk=walk)
        case MoveKeyOp():
            _move_in_state(op=op, source=source, destination=joined(segments=[*op.new_table_path, op.new_key]), walk=walk)
        case RemapValueOp():
            walk.remaps.append(
                RecordedRemap(
                    origin_path=walk.state.origin_by_current[source],
                    old_values=sorted(op.mapping),
                    new_values=sorted(set(op.mapping.values())),
                )
            )


def _move_in_state(*, op: MigrationOp, source: str, destination: str, walk: EntryWalk) -> None:
    """Move a subtree, recording a collision when the destination is already occupied.

    The move is performed either way, so that the end-state comparison stays meaningful and the
    collision is reported once rather than echoed as an unaccounted source.
    """
    if walk.state.subtree_of(path=destination):
        walk.occupied_destinations.append(
            f"{op.kind} moves '{source}' onto '{destination}', which the previous schema already has — "
            f"a file carrying both is refused as a conflict on every run, so a safe entry cannot do this"
        )
    walk.state.move_subtree(source=source, destination=destination)
