"""The cleanup of what a former release left: the `pipelex migrate` step that removes it, with a copy of every file.

`former_release.py` finds what a release that ran on the Pipelex Gateway or Pipelex Manifold left in a configuration
directory; this module removes exactly that, and nothing else. Each finding becomes one change:

- a retired backend table, a retired routing profile and a route to a retired backend are deleted, the comment
  introducing each going with it;
- a `model_specs_section` key is deleted from the backend that carries it, and the backend stays;
- the active routing profile, when it is a retired one, moves to the profile the kit makes active
  (`all_enabled_backends`), which is added to the file as the kit ships it when the file does not define it; an
  override naming a retired profile stops naming one, so its base decides;
- a file of its own — a retired backend's per-model file, the Gateway's model lists, `pipelex_service.toml` — is
  removed.

A file that is rewritten also loses the comments at the head of the document that speak of the Pipelex Gateway or
Pipelex Manifold, the instructions that came with that release; a comment anywhere else is the user's and stays.

Every file gets the backup the ledger replay gives the files it rewrites, through the same per-file transaction
(`runner.write_file_with_backup` and `runner.remove_file_with_backup`): one `.bak.<stamp>` copy, taken first and
kept, older ones pruned, and a file changed or unwritable mid-run left exactly as it was and reported. A dry run
reads and reports the same changes and writes nothing.

See `docs/migration-ledger.md` → "A former release's configuration".
"""

import copy
import re
from collections.abc import Sequence
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, cast

import tomlkit
from pydantic import BaseModel, ConfigDict, Field
from tomlkit import TOMLDocument
from tomlkit.container import OutOfOrderTableProxy
from tomlkit.exceptions import TOMLKitError
from tomlkit.items import Comment, Item, Null, Table, Whitespace

from pipelex.base_exceptions import PipelexUnexpectedError
from pipelex.fix_ops.file_transaction import read_file_snapshot
from pipelex.migration.engine import apply_ops_over_text
from pipelex.migration.former_release import (
    ACTIVE_KEY,
    MODEL_SPECS_SECTION_KEY,
    ROUTE_TABLE_KEYS,
    ROUTING_PROFILES_KEY,
    FormerReleaseFinding,
    FormerReleaseFindingKind,
    detect_former_release,
    kit_default_routing_profile_name,
    kit_routing_profile_library_path,
)
from pipelex.migration.gitignore import ensure_config_dir_gitignore
from pipelex.migration.plan import FileBlockedReason
from pipelex.migration.runner import FileWriteOutcome, remove_file_with_backup, write_file_with_backup
from pipelex.suggested_fix import DeleteKeyOp, DeleteTableOp, MigrationOp, RemapValueOp
from pipelex.system.configuration.config_loader import BACKENDS_OVERRIDE_FILE_NAME, ROUTING_PROFILES_OVERRIDE_FILE_NAME

#: What marks a comment at the head of a document as one a former release wrote about its own backends.
_FORMER_RELEASE_COMMENT_PATTERN = re.compile(r"gateway|manifold", re.IGNORECASE)

_OVERRIDE_FILE_NAMES = frozenset({BACKENDS_OVERRIDE_FILE_NAME, ROUTING_PROFILES_OVERRIDE_FILE_NAME})


class FormerReleaseFileAction(StrEnum):
    """What the cleanup does to one file."""

    REWRITE = "rewrite"
    """The file stays, without what the former release left in it."""

    REMOVE = "remove"
    """The file is the former release's own, and goes."""


class FormerReleaseFileCleanup(BaseModel):
    """The cleanup of one file: what it changes, and what became of the write.

    Like every migration report, it carries paths, keys and the names of retired backends and profiles, and never a
    value read from the file.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    file_path: Path
    action: FormerReleaseFileAction = Field(strict=False)
    changes: list[str]
    """Each change in words, in the order it is made."""

    backup_path: Path | None = None
    """Where the copy of the file as it was found is, once the cleanup ran."""

    was_applied: bool = False
    blocked_reason: FileBlockedReason | None = Field(default=None, strict=False)
    blocked_detail: str | None = None

    @property
    def is_blocked(self) -> bool:
        return self.blocked_reason is not None


class FormerReleaseCleanup(BaseModel):
    """The cleanup of every directory one run was pointed at."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    dry_run: bool
    files: list[FormerReleaseFileCleanup] = Field(default_factory=list[FormerReleaseFileCleanup])

    @property
    def is_clean(self) -> bool:
        """Whether the directories held nothing a former release left, so there was nothing to do."""
        return not self.files

    @property
    def applied_files(self) -> list[FormerReleaseFileCleanup]:
        return [file for file in self.files if file.was_applied]

    @property
    def blocked_files(self) -> list[FormerReleaseFileCleanup]:
        return [file for file in self.files if file.is_blocked]

    @property
    def needs_attention(self) -> bool:
        """Whether a file could not be cleaned and is left as it was found, which the user has to look at."""
        return bool(self.blocked_files)


def clean_former_release(*, config_dirs: Sequence[Path], dry_run: bool, moment: datetime | None = None) -> FormerReleaseCleanup:
    """Remove what a former release left in each configuration directory, keeping a copy of every file.

    Args:
        config_dirs: The directories to clean, `~/.pipelex/` and a project's `.pipelex/`; one named twice is
            cleaned once.
        dry_run: Report what would change and write nothing, not even the `.gitignore` that hides the backups.
        moment: The time the backups are stamped with, one for the whole run; now when not given.

    Returns:
        One entry per file that had something to clean, in the order the directories were given.
    """
    stamp_moment = moment or datetime.now(UTC)
    kit_default = kit_default_routing_profile_name()
    files: list[FormerReleaseFileCleanup] = []
    seen: set[Path] = set()
    for config_dir in config_dirs:
        resolved_dir = config_dir.resolve()
        if resolved_dir in seen:
            continue
        seen.add(resolved_dir)
        findings = detect_former_release(config_dir=config_dir)
        if findings.is_clean:
            continue
        if not dry_run:
            ensure_config_dir_gitignore(directory=config_dir)
        for file_path in findings.file_paths:
            file_findings = [finding for finding in findings.findings if finding.file_path == file_path]
            file_cleanup = _clean_file(file_path=file_path, findings=file_findings, kit_default=kit_default, dry_run=dry_run, moment=stamp_moment)
            if file_cleanup is not None:
                files.append(file_cleanup)
    return FormerReleaseCleanup(dry_run=dry_run, files=files)


def _clean_file(
    *, file_path: Path, findings: list[FormerReleaseFinding], kit_default: str, dry_run: bool, moment: datetime
) -> FormerReleaseFileCleanup | None:
    """Clean one file, or say why it could not be; `None` when its findings call for no change of its own."""
    if any(finding.kind.is_a_file_of_its_own for finding in findings):
        return _remove_file(file_path=file_path, findings=findings, dry_run=dry_run, moment=moment)
    return _rewrite_file(file_path=file_path, findings=findings, kit_default=kit_default, dry_run=dry_run, moment=moment)


def _remove_file(*, file_path: Path, findings: list[FormerReleaseFinding], dry_run: bool, moment: datetime) -> FormerReleaseFileCleanup:
    changes = [_removal_in_words(finding=finding) for finding in findings]
    if dry_run:
        return FormerReleaseFileCleanup(file_path=file_path, action=FormerReleaseFileAction.REMOVE, changes=changes)
    try:
        # The path itself, not what a symbolic link names: removing the link is the cleanup, and the file it points
        # at belongs to wherever it lives.
        snapshot = read_file_snapshot(file_path)
    except FileNotFoundError:
        return _blocked(
            file_path=file_path,
            action=FormerReleaseFileAction.REMOVE,
            changes=changes,
            reason=FileBlockedReason.CHANGED_DURING_RUN,
            detail="the file was removed while the cleanup was being prepared",
        )
    except OSError as exc:
        return _blocked(
            file_path=file_path,
            action=FormerReleaseFileAction.REMOVE,
            changes=changes,
            reason=FileBlockedReason.UNREADABLE,
            detail=f"the file could not be read: {exc.strerror or exc}",
        )
    outcome = remove_file_with_backup(snapshot=snapshot, moment=moment)
    return _with_outcome(file_path=file_path, action=FormerReleaseFileAction.REMOVE, changes=changes, outcome=outcome)


def _rewrite_file(
    *, file_path: Path, findings: list[FormerReleaseFinding], kit_default: str, dry_run: bool, moment: datetime
) -> FormerReleaseFileCleanup | None:
    try:
        # Through a symbolic link to the file it names, as the ledger replay rewrites one: replacing the link path
        # would delete the link and leave the real file as it was.
        snapshot = read_file_snapshot(file_path.resolve())
    except FileNotFoundError:
        return _blocked(
            file_path=file_path,
            action=FormerReleaseFileAction.REWRITE,
            changes=[finding.description for finding in findings],
            reason=FileBlockedReason.CHANGED_DURING_RUN,
            detail="the file was removed while the cleanup was being prepared",
        )
    except OSError as exc:
        return _blocked(
            file_path=file_path,
            action=FormerReleaseFileAction.REWRITE,
            changes=[finding.description for finding in findings],
            reason=FileBlockedReason.UNREADABLE,
            detail=f"the file could not be read: {exc.strerror or exc}",
        )
    try:
        text = snapshot.content.decode("utf-8")
        new_text, changes = cleaned_text(text=text, findings=findings, kit_default=kit_default, is_override=file_path.name in _OVERRIDE_FILE_NAMES)
    except (UnicodeDecodeError, TOMLKitError) as exc:
        # It parsed when it was read for the findings, so this is a file changed since or an operation failing on
        # valid TOML. Either way it is this file's to report, never a reason to stop the run.
        return _blocked(
            file_path=file_path,
            action=FormerReleaseFileAction.REWRITE,
            changes=[finding.description for finding in findings],
            reason=FileBlockedReason.UNPARSEABLE,
            detail=f"the file could not be cleaned: {exc}",
        )
    if new_text == text:
        return None
    if dry_run:
        return FormerReleaseFileCleanup(file_path=file_path, action=FormerReleaseFileAction.REWRITE, changes=changes)
    outcome = write_file_with_backup(snapshot=snapshot, new_content=new_text, moment=moment)
    return _with_outcome(file_path=file_path, action=FormerReleaseFileAction.REWRITE, changes=changes, outcome=outcome)


def cleaned_text(*, text: str, findings: Sequence[FormerReleaseFinding], kit_default: str, is_override: bool) -> tuple[str, list[str]]:
    """One document without what a former release left in it, and each change in words.

    The kit's default profile goes in first, ahead of the deletions, so that the banner heading the profiles stays at
    the head of them instead of leaving with the first profile it introduced. The comments at the head of the
    document go last, and only from a document something else changed.

    Args:
        text: The document as read.
        findings: What `detect_former_release` found in this document.
        kit_default: The routing profile the kit makes active.
        is_override: Whether the document is a personal override, whose retired `active` is deleted rather than moved.

    Returns:
        The cleaned text, the same string when nothing changed, and the changes made, in order.
    """
    changes: list[str] = []
    current_text = text
    ops: list[tuple[MigrationOp, str]] = []
    for finding in findings:
        ops.extend(_ops_for(finding=finding, kit_default=kit_default, is_override=is_override))

    moves_active = any(isinstance(op, RemapValueOp) for op, _ in ops)
    if moves_active:
        document = tomlkit.loads(current_text)
        if _add_kit_profile(document=document, kit_default=kit_default):
            current_text = tomlkit.dumps(document)  # pyright: ignore[reportUnknownMemberType]
            changes.append(f"added the routing profile '{kit_default}', as this release ships it")

    application = apply_ops_over_text(text=current_text, ops=[op for op, _ in ops])
    current_text = application.text
    changes.extend(change for (_, change), applied in zip(ops, application.applications, strict=True) if applied.outcome.did_apply)
    if current_text == text:
        return text, []

    document = tomlkit.loads(current_text)
    if _drop_former_release_comments(document=document):
        current_text = tomlkit.dumps(document)  # pyright: ignore[reportUnknownMemberType]
        changes.append("removed a comment about the Pipelex Gateway")
    return current_text, _deduplicated(changes=changes)


def _ops_for(*, finding: FormerReleaseFinding, kit_default: str, is_override: bool) -> list[tuple[MigrationOp, str]]:
    """The operations that remove one finding from its document, each with its change in words."""
    match finding.kind:
        case FormerReleaseFindingKind.RETIRED_BACKEND_TABLE:
            return [(DeleteTableOp(table_path=[_subject_of(finding=finding)]), f"removed the '{finding.subject}' backend")]
        case FormerReleaseFindingKind.MODEL_SPECS_SECTION_KEY:
            return [
                (
                    DeleteKeyOp(table_path=[_subject_of(finding=finding)], key=MODEL_SPECS_SECTION_KEY),
                    f"removed '{MODEL_SPECS_SECTION_KEY}' from the '{finding.subject}' backend",
                )
            ]
        case FormerReleaseFindingKind.RETIRED_ROUTING_PROFILE:
            return [
                (DeleteTableOp(table_path=[ROUTING_PROFILES_KEY, _subject_of(finding=finding)]), f"removed the routing profile '{finding.subject}'")
            ]
        case FormerReleaseFindingKind.ROUTE_TO_RETIRED_BACKEND:
            route_table = finding.route_table or ROUTE_TABLE_KEYS[0]
            route_pattern = finding.route_pattern or ""
            return [
                (
                    DeleteKeyOp(table_path=[ROUTING_PROFILES_KEY, _subject_of(finding=finding), route_table], key=route_pattern),
                    f"removed the route of '{route_pattern}' to '{finding.retired_backend}' from the routing profile '{finding.subject}'",
                )
            ]
        case FormerReleaseFindingKind.ACTIVE_ROUTING_PROFILE:
            if finding.route_pattern is not None:
                # The active profile stays; the route that made it retired is a finding of its own, in the file that
                # holds the profile, and goes there.
                return []
            if is_override:
                return [
                    (
                        DeleteKeyOp(table_path=[], key=ACTIVE_KEY),
                        f"removed '{ACTIVE_KEY}', which named the routing profile '{finding.subject}', so the base file's applies",
                    )
                ]
            return [
                (
                    RemapValueOp(table_path=[], key=ACTIVE_KEY, mapping={_subject_of(finding=finding): kit_default}),
                    f"moved the active routing profile from '{finding.subject}' to '{kit_default}'",
                )
            ]
        case (
            FormerReleaseFindingKind.RETIRED_BACKEND_FILE | FormerReleaseFindingKind.GATEWAY_MODELS_REFERENCE | FormerReleaseFindingKind.SERVICE_FILE
        ):
            return []


def _removal_in_words(*, finding: FormerReleaseFinding) -> str:
    match finding.kind:
        case FormerReleaseFindingKind.RETIRED_BACKEND_FILE:
            return f"removed the model settings of the '{finding.subject}' backend"
        case FormerReleaseFindingKind.GATEWAY_MODELS_REFERENCE:
            return "removed the list of the models the Pipelex Gateway served"
        case FormerReleaseFindingKind.SERVICE_FILE:
            return "removed the record of the Pipelex Gateway's terms acceptance"
        case (
            FormerReleaseFindingKind.RETIRED_BACKEND_TABLE
            | FormerReleaseFindingKind.MODEL_SPECS_SECTION_KEY
            | FormerReleaseFindingKind.RETIRED_ROUTING_PROFILE
            | FormerReleaseFindingKind.ROUTE_TO_RETIRED_BACKEND
            | FormerReleaseFindingKind.ACTIVE_ROUTING_PROFILE
        ):
            return finding.description


def _add_kit_profile(*, document: TOMLDocument, kit_default: str) -> bool:
    """Put the kit's default profile first among the document's profiles, as the kit ships it, unless it is there.

    Copied from the kit's own document, so its comments come with it and it lands as `pipelex init` would write it.
    """
    profiles: Table | None = None
    if ROUTING_PROFILES_KEY in document:
        existing = document.item(ROUTING_PROFILES_KEY)
        if kit_default in cast("dict[str, Any]", existing):
            return False
        if isinstance(existing, OutOfOrderTableProxy):
            # Profiles spread across the file between other tables: the profile joins them where tomlkit puts it.
            existing[kit_default] = _kit_profile(kit_default=kit_default)
            return True
        if not isinstance(existing, Table):
            # An inline `profiles` table, which no release wrote: left as it is rather than restructured.
            return False
        profiles = existing
    if profiles is None:
        profiles = tomlkit.table(is_super_table=True)
        document.append(ROUTING_PROFILES_KEY, profiles)
    if len(profiles.value) == 0:
        profiles.append(kit_default, _kit_profile(kit_default=kit_default))
    else:
        profiles.value._insert_at(0, kit_default, _kit_profile(kit_default=kit_default))  # ruff: ignore[private-member-access] # pyright: ignore[reportPrivateUsage]
    return True


def _kit_profile(*, kit_default: str) -> Item:
    kit_path = kit_routing_profile_library_path()
    kit_profiles = tomlkit.loads(kit_path.read_text(encoding="utf-8")).item(ROUTING_PROFILES_KEY)
    if not isinstance(kit_profiles, Table) or kit_default not in kit_profiles:
        msg = f"the kit's routing profile library '{kit_path}' does not define its active profile '{kit_default}' — packaging bug"
        raise PipelexUnexpectedError(msg)
    return copy.deepcopy(kit_profiles.value.item(kit_default))


def _drop_former_release_comments(*, document: TOMLDocument) -> bool:
    """Drop each paragraph of comments at the document's head that speaks of the Pipelex Gateway or Manifold.

    The head is the root of the document, ahead of its first table: where a release wrote the instructions for the
    file, and where a user's notes about a table never sit, since those sit above the table they are about. A
    paragraph is a run of comment lines between blank ones; it goes whole, with the blank line after it. The items are
    blanked in place rather than removed, which keeps the container's indexes valid; they render as nothing.
    """
    body = document.body
    dropped = False
    index = 0
    while index < len(body):
        if not isinstance(body[index][1], Comment):
            index += 1
            continue
        end = index
        while end < len(body) and isinstance(body[end][1], Comment):
            end += 1
        paragraph = body[index:end]
        if any(_FORMER_RELEASE_COMMENT_PATTERN.search(item.as_string()) for _, item in paragraph):
            for position in range(index, end):
                body[position] = (None, Null())
            if end < len(body) and isinstance(body[end][1], Whitespace):
                body[end] = (None, Null())
                end += 1
            dropped = True
        index = end
    return dropped


def _deduplicated(*, changes: list[str]) -> list[str]:
    """The changes, each once, in order: a profile defined in two halves of a file is one profile removed."""
    return list(dict.fromkeys(changes))


def _subject_of(*, finding: FormerReleaseFinding) -> str:
    if finding.subject is None:
        msg = f"a former-release finding of kind '{finding.kind}' names no subject — detector bug"
        raise PipelexUnexpectedError(msg)
    return finding.subject


def _with_outcome(*, file_path: Path, action: FormerReleaseFileAction, changes: list[str], outcome: FileWriteOutcome) -> FormerReleaseFileCleanup:
    return FormerReleaseFileCleanup(
        file_path=file_path,
        action=action,
        changes=changes,
        backup_path=outcome.backup_path,
        was_applied=outcome.was_written,
        blocked_reason=outcome.blocked_reason,
        blocked_detail=outcome.blocked_detail,
    )


def _blocked(
    *, file_path: Path, action: FormerReleaseFileAction, changes: list[str], reason: FileBlockedReason, detail: str
) -> FormerReleaseFileCleanup:
    return FormerReleaseFileCleanup(file_path=file_path, action=action, changes=changes, blocked_reason=reason, blocked_detail=detail)
