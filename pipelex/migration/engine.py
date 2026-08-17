"""The engine — replaying a surface's ledger over one document's text.

This module is deliberately filesystem-free: it takes the text of a file and a parsed ledger and
returns the text the file should now have, plus what happened. Everything about reading, backing
up and writing files lives in `runner.py`, so that the checks — which replay over reference
documents that are never written anywhere — reuse exactly the code a user's migration runs.

**Text in, text out, and one operation at a time.** The document is re-read between operations
that applied, rather than carried as a single long-lived DOM. That is not caution, it is a
measured requirement: tomlkit's position-preserving rename leaves the node's raw `dict` storage
out of step with the body it renders from, so a later operation addressing the renamed key raises
`KeyError` from deep inside the library (see
`tests/unit/pipelex/pipeline/fixes/test_fix_applier_rename_dom_consistency.py`, which pins the
behaviour). Re-reading is exact — serialization is byte-faithful — and it costs a parse of a few
hundred lines per *applied* operation, which under always-replay is almost never.

Three properties this module is responsible for:

- **Every run replays everything.** There is no version resolution step and no state stamp to
  read: each entry is replayed in order and the applier skips whatever is already gone or already
  done. Any side record of "what has been applied" would eventually report "nothing to do" beside
  a broken boot, which is the worst failure this tool can have.
- **Serialization adds nothing.** When no operation applies, the text returned is the text that
  came in — the same string, untouched — so byte-level replay neutrality is a property of this
  function rather than a property of the TOML library we happen to use. When something does
  apply, the output is `tomlkit.dumps` of the mutated document and nothing else: no canonical
  reflow, because a one-key rename must not rewrite a user's spacing.
- **An `unsafe` entry is never written, and is only *reported* when the file still carries the
  material it is about.** Its operations are rehearsed against the text and the result discarded,
  and the paths it declares narrowed are looked up — at every spelling later entries have given
  them, and reported at the one this replay leaves behind, because the file the user is sent to
  check is the file this run wrote. On a file the entry has nothing to say to, it stays silent
  instead of warning at every boot. Where that material lives is `material.py`'s question.

See `docs/migration-ledger.md` → "Schema versions, and why every run replays everything",
"Applying", "What an `unsafe` entry promises", and "What the engine reports".
"""

from collections.abc import Sequence

import tomlkit
from pydantic import BaseModel, ConfigDict, Field

from pipelex.migration.documents import document_carries_path, document_paths
from pipelex.migration.ledger import MigrationEntry, MigrationLedger
from pipelex.migration.material import declared_path_spellings, spelling_after_replay, unsafe_op_variants
from pipelex.migration.plan import BlockedEntry, BlockedEntryReason, MigrationStep
from pipelex.migration.safety import MigrationSafety
from pipelex.pipeline.fixes.applier import FixOpApplication, apply_fix_ops
from pipelex.suggested_fix import MigrationOp


class OpsApplication(BaseModel):
    """The result of applying a run of operations to one document's text."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str
    applications: list[FixOpApplication]

    @property
    def applied_count(self) -> int:
        return sum(1 for application in self.applications if application.outcome.did_apply)

    @property
    def conflicts(self) -> list[FixOpApplication]:
        return [application for application in self.applications if application.outcome.is_conflict]


class DocumentReplay(BaseModel):
    """What replaying a whole ledger over one document did to it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str
    """The document as it should now be. Identical to the input when nothing applied."""

    steps: list[MigrationStep] = Field(default_factory=list[MigrationStep])
    blocked: list[BlockedEntry] = Field(default_factory=list[BlockedEntry])

    @property
    def did_change_document(self) -> bool:
        return any(step.applied_ops for step in self.steps) or any(entry.applied_ops for entry in self.blocked)


def apply_ops_over_text(*, text: str, ops: Sequence[MigrationOp]) -> OpsApplication:
    """Apply operations in order to a document's text, re-reading it between applied ones.

    The returned text is the *same string* when no operation applied, which is what makes replay
    neutrality a property of this code. Operation-level atomicity is the applier's own: a
    conflicting operation writes nothing, including a wildcard one whose conflict sits in the last
    matched entry, so a conflict leaves the text exactly as it found it too.
    """
    current_text = text
    toml_doc = tomlkit.loads(current_text)
    applications: list[FixOpApplication] = []
    for op in ops:
        applied_now = apply_fix_ops(toml_doc=toml_doc, ops=[op])
        applications.extend(applied_now)
        if not any(application.outcome.did_apply for application in applied_now):
            continue
        current_text = tomlkit.dumps(toml_doc)  # pyright: ignore[reportUnknownMemberType]
        toml_doc = tomlkit.loads(current_text)
    return OpsApplication(text=current_text, applications=applications)


def replay_ledger_over_text(*, ledger: MigrationLedger, text: str) -> DocumentReplay:
    """Replay every entry of a surface's ledger over one document, in order.

    Entries compose in sequence, which is what lets a file coming from schema version 1 land
    correctly when a key was renamed at 2 and moved at 4.
    """
    current_text = text
    steps: list[MigrationStep] = []
    blocked: list[BlockedEntry] = []
    for entry in ledger.migration:
        match entry.safety:
            case MigrationSafety.UNSAFE:
                _rehearse_unsafe_entry(entry=entry, ledger=ledger, text=current_text, blocked=blocked)
            case MigrationSafety.SAFE:
                current_text = _apply_safe_entry(entry=entry, text=current_text, steps=steps, blocked=blocked)
    return DocumentReplay(text=current_text, steps=steps, blocked=blocked)


def _rehearse_unsafe_entry(*, entry: MigrationEntry, ledger: MigrationLedger, text: str, blocked: list[BlockedEntry]) -> None:
    """Find out whether an `unsafe` entry has anything to say about this file, writing nothing.

    Every rehearsal's text is discarded, so the file is untouched whatever the outcome. An entry
    with nothing to say stays silent: reporting it regardless would warn every user with a
    perfectly current file, at every boot, forever.
    """
    operations_would_fire = _operations_would_fire(entry=entry, ledger=ledger, text=text)
    narrowed_paths = _declared_paths_this_file_carries(entry=entry, ledger=ledger, text=text)
    if not operations_would_fire and not narrowed_paths:
        return
    if operations_would_fire:
        reason = BlockedEntryReason.UNSAFE
        detail = (
            f"this file needs the changes of '{entry.id}', but the entry is marked unsafe: the applier cannot "
            f"tell a stale value from a deliberate choice, so it is reported and never applied"
        )
    else:
        reason = BlockedEntryReason.VALUE_DOMAIN_NARROWED
        detail = (
            f"'{entry.id}' narrowed what {', '.join(narrowed_paths)} may hold, and this file sets a value there. No "
            f"operation can repair a value, so the entry is reported and never applied — check those keys by hand"
        )
    blocked.append(
        BlockedEntry(
            entry_id=entry.id,
            to_schema_version=entry.to_schema_version,
            reason=reason,
            detail=detail,
            guidance=entry.guidance,
            narrowed_paths=narrowed_paths,
        )
    )


def _operations_would_fire(*, entry: MigrationEntry, ledger: MigrationLedger, text: str) -> bool:
    """Whether rehearsing the entry's operations against this file would do anything.

    Value-sensitive by construction, because a remap is about a stale *spelling* rather than about
    a path: reporting on the path alone would warn a user whose value was never stale. Asked at
    every spelling `material.py` says the material can have, so that an entry which reported on
    the first run does not go silent on the second because a later `safe` entry renamed the table
    around it.
    """
    for ops in unsafe_op_variants(ledger=ledger, entry=entry):
        rehearsal = apply_ops_over_text(text=text, ops=ops)
        if rehearsal.applied_count or rehearsal.conflicts:
            return True
    return False


def _declared_paths_this_file_carries(*, entry: MigrationEntry, ledger: MigrationLedger, text: str) -> list[str]:
    """The entry's declared narrowed paths that this file has a value at, as the migrated file spells them.

    Presence is the whole predicate. No operation can express a value the new schema refuses, so
    there is nothing to rehearse — and the engine is deliberately model-free, so it cannot tell a
    value the narrowed domain rejects from one it accepts. What comes back is a list of keys for a
    human to check, and it is reported as the *ledger* spells it, `*` included, so that a key the
    user chose beneath an open mapping is no more rendered than a value would be.

    Looked up at every spelling the material has ever had, and reported at the one the *end of this
    replay* leaves: the entry is questioned against the text as it stands here, and the later `safe`
    entries then rename the material before the file is written. The file the user is sent to check
    is the one the run wrote, so naming the spelling that matched would name a key it no longer has.
    """
    spellings = declared_path_spellings(ledger=ledger, entry=entry)
    if not spellings:
        return []
    present = document_paths(document=tomlkit.loads(text))
    carried: list[str] = []
    for spelling in spellings:
        if not document_carries_path(paths=present, pattern=spelling):
            continue
        after_replay = spelling_after_replay(ledger=ledger, entry=entry, spelling=spelling)
        if after_replay not in carried:
            carried.append(after_replay)
    return carried


def _apply_safe_entry(*, entry: MigrationEntry, text: str, steps: list[MigrationStep], blocked: list[BlockedEntry]) -> str:
    """Apply a `safe` entry and fold its operation outcomes into the plan, returning the new text.

    What is decided here is how the *entry* is reported: a conflict anywhere routes the whole
    entry into `blocked[]`, carrying whichever of its operations did apply, so the report never
    claims an entry landed whole when part of it could not.
    """
    application = apply_ops_over_text(text=text, ops=entry.ops)
    applied_ops = [op for op, outcome in zip(entry.ops, application.applications, strict=True) if outcome.outcome.did_apply]
    conflicts = application.conflicts
    if conflicts:
        details = "; ".join(str(conflict.detail) for conflict in conflicts)
        blocked.append(
            BlockedEntry(
                entry_id=entry.id,
                to_schema_version=entry.to_schema_version,
                reason=BlockedEntryReason.CONFLICT,
                detail=f"{len(conflicts)} of {len(application.applications)} operations conflict: {details}",
                guidance=entry.guidance,
                applied_ops=applied_ops,
            )
        )
        return application.text
    if applied_ops:
        steps.append(
            MigrationStep(
                entry_id=entry.id,
                to_schema_version=entry.to_schema_version,
                title=entry.title,
                description=entry.description,
                breaking=entry.breaking,
                safety=entry.safety,
                applied_ops=applied_ops,
            )
        )
    # Skipping is the overwhelmingly common outcome under always-replay and is entirely benign —
    # the target is gone, or the change is already there. Reports suppress it.
    return application.text
