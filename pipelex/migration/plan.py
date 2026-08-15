"""What a migration run reports — one plan per file, one report per surface walk.

There is no `from_version` and no trusted-version concept anywhere in these models, and that is
the design rather than an omission: nothing skips on a version record, so nothing needs one. A
replay walks every entry while usually changing nothing, and the report renders what *this run*
observed and did — which it knows exactly — rather than what some earlier run claims to have done.

Two different things can be blocked and the models keep them apart. An **entry** is blocked when
it cannot be applied: it is `unsafe`, or one of its operations came back `CONFLICT`. It lands in
`blocked[]` with its guidance while the rest of the file's entries proceed. A **file** is blocked
when it cannot be processed at all — unparseable, unwritable, or changed on disk between the read
and the write — and that reason sits on the plan itself, where it never stops a sibling file.

> **No value read from a user's file is ever rendered.** Paths, operation kinds and
> ledger-supplied values carry everything these models need to say. That is a mechanical rule
> rather than a list of credential-shaped key names, because such a list is a guess that
> eventually misses one.

See `docs/migration-ledger.md` → "What the engine reports".
"""

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from pipelex.migration.ledger import MigrationSafety
from pipelex.suggested_fix import MigrationOp


class MigrationStep(BaseModel):
    """One ledger entry that changed this file, and the operations of it that fired."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    entry_id: str
    to_schema_version: int
    title: str
    description: str
    """The entry's release-note sentence — ledger text, never anything read from the file."""

    breaking: bool
    safety: MigrationSafety = Field(strict=False)
    applied_ops: list[MigrationOp]
    """Only the operations that actually applied. Under always-replay most operations skip, and
    listing the skipped ones would bury the change in noise."""


class BlockedEntryReason(StrEnum):
    """Why an entry could not be applied to this file."""

    UNSAFE = "unsafe"
    """The entry is `unsafe`: the applier cannot tell a stale value from a deliberate choice."""

    CONFLICT = "conflict"
    """An operation's destination is already occupied — typically because the user hand-fixed
    part of their file — so applying it would choose on their behalf."""


class BlockedEntry(BaseModel):
    """An entry that this file needs and the run would not apply."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    entry_id: str
    to_schema_version: int
    reason: BlockedEntryReason = Field(strict=False)
    detail: str
    """Why, in terms of paths and operation kinds only."""

    guidance: str | None = None
    """The entry's own agent-facing Markdown, when it carries any."""

    applied_ops: list[MigrationOp] = Field(default_factory=list[MigrationOp])
    """Operations of this entry that did apply before the conflict was found. Always empty for
    an `unsafe` entry, which is rehearsed on a copy and never written."""


class FileBlockedReason(StrEnum):
    """Why a file could not be processed at all."""

    UNPARSEABLE = "unparseable"
    UNWRITABLE = "unwritable"
    CHANGED_DURING_RUN = "changed_during_run"


class UnexplainedPath(BaseModel):
    """A path the current schema does not know and no ledger entry removes.

    Populated by the downgrade diagnosis, which lands with the commands: the file is either
    carrying a typo or was written by a newer pipelex than the one running.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str
    note: str


class MigrationPlan(BaseModel):
    """What one file needs, and what this run did to it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    surface_id: str
    file_path: Path

    blocked_reason: FileBlockedReason | None = Field(default=None, strict=False)
    """Set when the file itself could not be processed. A blocked file never stops its siblings."""

    blocked_detail: str | None = None

    steps: list[MigrationStep] = Field(default_factory=list[MigrationStep])
    blocked: list[BlockedEntry] = Field(default_factory=list[BlockedEntry])
    unexplained: list[UnexplainedPath] = Field(default_factory=list[UnexplainedPath])

    backup_path: Path | None = None
    """Where the pre-migration copy of this file was written, when the run wrote the file."""

    was_written: bool = False

    @property
    def is_clean(self) -> bool:
        """Whether the file needs nothing: nothing applied, nothing blocked, nothing unexplained."""
        return not (self.steps or self.blocked or self.unexplained or self.blocked_reason)


class MigrationReport(BaseModel):
    """Every file one run visited."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    plans: list[MigrationPlan] = Field(default_factory=list[MigrationPlan])

    @property
    def written_plans(self) -> list[MigrationPlan]:
        return [plan for plan in self.plans if plan.was_written]

    @property
    def blocked_plans(self) -> list[MigrationPlan]:
        return [plan for plan in self.plans if plan.blocked_reason is not None or plan.blocked]

    @property
    def is_clean(self) -> bool:
        return all(plan.is_clean for plan in self.plans)
