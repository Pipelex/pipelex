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

This module is deliberately low-level — stdlib, pydantic, and the two sibling modules that are
themselves low-level (`safety`, `suggested_fix`) — so that `pipelex.base_exceptions` can import it
without creating a cycle. That is what lets a configuration validation error carry a real
`MigrationPlan` rather than a second projection of one that would drift from this one. Nothing
here may reach `migration.exceptions`, `migration.ledger` or anything that imports them.

See `docs/migration-ledger.md` → "What the engine reports".
"""

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from pipelex.migration.safety import MigrationSafety
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

    VALUE_DOMAIN_NARROWED = "value_domain_narrowed"
    """The file sets a path whose accepted values the entry narrowed, and no operation can repair
    a value. Weaker than `UNSAFE`, and deliberately so: this says *check this key*, not *this file
    has the old shape*. The engine is model-free, so it knows the file sets the path and not
    whether the value it holds is one the new schema refuses."""


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

    narrowed_paths: list[str] = Field(default_factory=list[str])
    """The entry's declared narrowed paths that this file has something at, as the *ledger*
    spells them — `levels.*` rather than the user's own `levels.my_package`, so that no key a user
    chose is rendered any more than a value is — and at the spelling the file this run wrote
    carries, since that is the file being sent back to be checked.

    Keys to check by hand, never a list of errors: telling one from the other needs the model, and
    the engine has none by design."""


class FileBlockedReason(StrEnum):
    """Why a file could not be processed at all.

    One member per *state the file is in*, because that is what decides what the user does next —
    not one per exception the run happened to catch. Four of the five leave the file exactly as it
    was found; the fifth is the one that does not, and it says so.
    """

    UNREADABLE = "unreadable"
    """The file is there and its bytes could not be read. Nothing was written."""

    UNPARSEABLE = "unparseable"
    """The file was read and is not valid UTF-8, or not valid TOML. Nothing was written."""

    UNSUPPORTED_SCHEMA_VERSION = "unsupported_schema_version"
    """The file declares a `[meta] schema_version` below its ledger's floor, so the entries that
    would carry it forward are no longer in the ledger. Nothing was written.

    This is the one state a replay cannot detect for itself, and the reason the floor exists: the
    applier skips an operation whose target is absent, so a squashed ledger run over a file older
    than the squash would report success over a file it under-migrated. Refusing by name is the
    alternative to that silence."""

    UNWRITABLE = "unwritable"
    """The file needed a change and the run could not make it — the backup would not go down, or
    the replacement would not. The file is exactly as it was found."""

    CHANGED_DURING_RUN = "changed_during_run"
    """The file was removed or edited between the read and the write, so the run refused to write
    over work it had not seen. The file is whatever that other writer left."""

    STATE_UNCERTAIN = "state_uncertain"
    """The write could not be confirmed: the transaction could not describe what it left behind,
    and the file does not hold what this run wrote. The one reason that cannot promise the file is
    as it was found, which is why it is not folded into `UNWRITABLE` — the user's next move is to
    compare the file against the rescue copy the plan names, not to fix a permission and re-run.

    For the single-file commit the runner performs it is also the *only* transaction failure that
    reaches the plan at all: a replacement that fails re-raises its own `OSError`, because rolling
    back nothing is trivially complete."""

    @property
    def leaves_the_write_unconfirmed(self) -> bool:
        """Whether this reason means the file may hold something other than what it was found with.

        Every other reason confirms this migration did not write — including `CHANGED_DURING_RUN`,
        under which somebody else did; a summary that says "nothing was written" is true of them
        and false of this one.
        """
        return self is FileBlockedReason.STATE_UNCERTAIN


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
    """Where the pre-migration copy of this file was written — when the run wrote the file, and also
    when a write failed leaving the file's state uncertain, because then the copy is kept for the user."""

    was_written: bool = False

    @property
    def is_clean(self) -> bool:
        """Whether the file needs nothing: nothing applied, nothing blocked, nothing unexplained."""
        return not (self.steps or self.blocked or self.unexplained or self.blocked_reason)

    @property
    def did_change(self) -> bool:
        """Whether anything applied to this file — a whole entry, or the part of a conflicting one
        that landed before the conflict was found.

        The plan-level twin of `DocumentReplay.did_change_document`, which is what the runner writes
        on; the two must agree or a dry run stops predicting the write. A file can therefore be both
        changed and blocked: the entry that conflicted is reported once, under `blocked`, carrying
        the operations of it that did apply.
        """
        return bool(self.steps) or any(entry.applied_ops for entry in self.blocked)


class MigrationReport(BaseModel):
    """Every file one run visited."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    plans: list[MigrationPlan] = Field(default_factory=list[MigrationPlan])

    @property
    def written_plans(self) -> list[MigrationPlan]:
        """The files this run rewrote. Always empty on a dry run, which writes nothing."""
        return [plan for plan in self.plans if plan.was_written]

    @property
    def changed_plans(self) -> list[MigrationPlan]:
        """The files something applied to — whether or not this run was allowed to write them.

        The difference from `written_plans` is exactly what a dry run is for: these are the files
        a write pass would rewrite — including a file whose only change is the part of a
        conflicting entry that applied before the conflict.
        """
        return [plan for plan in self.plans if plan.did_change]

    @property
    def blocked_plans(self) -> list[MigrationPlan]:
        """The files carrying something this run would not do — a blocked file, or a blocked entry."""
        return [plan for plan in self.plans if plan.blocked_reason is not None or plan.blocked]

    @property
    def unexplained_plans(self) -> list[MigrationPlan]:
        """The files carrying a path the current schema does not know and no entry removes."""
        return [plan for plan in self.plans if plan.unexplained]

    @property
    def needs_attention(self) -> bool:
        """Whether anything here is a human's to resolve rather than the tool's.

        This is the verdict a machine consumer branches on. It is deliberately *not* "did this run
        write anything": a run that migrated every file it found and left nothing blocked has
        succeeded, and a dry run that found nothing blocked has too.
        """
        return bool(self.blocked_plans or self.unexplained_plans)

    @property
    def is_clean(self) -> bool:
        return all(plan.is_clean for plan in self.plans)
