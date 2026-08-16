"""The reserved-path registry — every path and enumerated spelling a ledger has ever removed.

**The registry is derived, not stored.** Every path a schema version removed is `fingerprint@N-1`
minus `fingerprint@N`, so the whole registry is a walk of the golden chain, plus the declarations
of any pre-history entry. A stored copy would be a second source of truth that could disagree with
the chain it summarizes, and the only way to check it would be to recompute it — at which point
the stored copy has no reader left.

Reuse is refused outright, with no escape-hatch marker: reintroducing a removed path would make it
legal again on a current file, and premise one of replay neutrality — *every operation's
precondition mentions only removed material* — would be false. An author who hits the rule picks
another name.

The registry is diagnostic as much as preventive: when a convergence check or a transform golden
fails, it is what turns the failure into a sentence naming the path and the schema version that
reserved it.

See `docs/migration-ledger.md` → "Reserved paths and names".
"""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from pipelex.migration.goldens import read_fingerprint_golden
from pipelex.migration.ledger import MigrationLedger
from pipelex.migration.walk import op_source_path
from pipelex.suggested_fix import RemapValueOp


class ReservedRegistry(BaseModel):
    """What a surface's ledger has retired, and at which schema version."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    surface_id: str

    version_by_path: dict[str, int] = Field(default_factory=dict[str, int])
    """Every removed path, mapped to the schema version that removed it."""

    version_by_value: dict[str, int] = Field(default_factory=dict[str, int])
    """Every remapped-away enumerated spelling, keyed as `<path>=<value>`."""

    def reserved_at(self, *, path: str) -> int | None:
        return self.version_by_path.get(path)

    def is_reserved(self, *, path: str) -> bool:
        return path in self.version_by_path

    def value_reserved_at(self, *, path: str, value: str) -> int | None:
        return self.version_by_value.get(_value_key(path=path, value=value))


def _value_key(*, path: str, value: str) -> str:
    return f"{path}={value}"


def derive_reserved_registry(*, surface_id: str, ledger: MigrationLedger, migration_dir: Path) -> ReservedRegistry:
    """Walk the golden chain and the ledger, and record what each version retired.

    A link whose `before` golden is missing contributes nothing rather than raising: a broken chain
    is the coverage check's finding to report, in the terms an author can act on, and this function
    exists to *describe* the ledger rather than to judge it.
    """
    version_by_path: dict[str, int] = {}
    version_by_value: dict[str, int] = {}

    for entry in ledger.migration:
        version = entry.to_schema_version
        if entry.pre_history:
            # No fingerprint pair describes a pre-history diff — that is what the flag means — so
            # the entry's own declaration is the record: `check-ledger` verifies the operations stay
            # inside it, and the transform check migrates the hand-authored `before` document.
            for path in entry.declared_removed_paths:
                version_by_path.setdefault(path, version)
        else:
            before = read_fingerprint_golden(migration_dir=migration_dir, surface_id=surface_id, schema_version=version - 1)
            after = read_fingerprint_golden(migration_dir=migration_dir, surface_id=surface_id, schema_version=version)
            if before is not None and after is not None:
                for path in sorted(before.path_names() - after.path_names()):
                    version_by_path.setdefault(path, version)

        for op in entry.ops:
            if isinstance(op, RemapValueOp):
                path = op_source_path(op=op)
                for old_value in sorted(op.mapping):
                    version_by_value.setdefault(_value_key(path=path, value=old_value), version)

    return ReservedRegistry(surface_id=surface_id, version_by_path=version_by_path, version_by_value=version_by_value)
