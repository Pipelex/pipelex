"""The cleanup of what a former release left: the `pipelex migrate` step that removes it, with a copy of every file.

`former_release.py` finds what a release that ran on the Pipelex Gateway or Pipelex Manifold left in the home and
project configuration directories, read as their boots merge them; this module removes exactly that, and nothing else.
Each finding becomes one change:

- a retired backend table, a retired routing profile and a route to a retired backend are deleted, the comment
  introducing each going with it;
- a retired `default` of a profile that stays — an override retargeting the user's own profile — is deleted alone,
  so the profile's routes stay;
- a `model_specs_section` key is deleted from the backend that carries it, and the backend stays;
- an `active` naming a profile the cleanup removes moves off it in every file that sets it, whichever directory the
  profile was defined in: a base moves to the profile the kit makes active (`all_enabled_backends`), which is added to
  the file as the kit ships it when the file does not define it, and an override stops naming one, so the file read
  before it decides;
- a file of its own — a retired backend's per-model file, the Gateway's model lists, `pipelex_service.toml` — is
  removed.

A file that is rewritten also loses the paragraphs of comments the former release shipped at the head of the
document, word for word: the Gateway's instructions. Every other comment, a user's note naming the Gateway included,
stays. A file whose shape the cleanup cannot rewrite safely — routing profiles written as one inline table, where the
kit's profile cannot be added, or a change the cleanup cannot express — is left as it is and reported, with what to
change by hand.

**After writing, the cleanup checks its own work.** It reads the files every boot of the machine merges, and anything
that still stops one — what a former release left, or an active routing profile no file defines — is reported as
needing attention rather than as a success.

Every file gets the backup the ledger replay gives the files it rewrites, through the same per-file transaction
(`runner.write_file_with_backup` and `runner.remove_file_with_backup`): one `.bak.<stamp>` copy, taken first and
kept, older ones pruned, and a file changed or unwritable mid-run left exactly as it was and reported. The
transaction is per file, not across the files: one that fails after others were written leaves those written, so a
boot the plan kept on its profile through a change in another file can start on another profile until that file is
edited. A dry run reads and reports the same changes and writes nothing.

See `docs/migration-ledger.md` → "A former release's configuration".
"""

import copy
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, NamedTuple, cast

import tomlkit
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from tomlkit import TOMLDocument
from tomlkit.container import OutOfOrderTableProxy
from tomlkit.exceptions import TOMLKitError
from tomlkit.items import Comment, Item, Null, Table, Whitespace

from pipelex.base_exceptions import PipelexUnexpectedError
from pipelex.cogt.model_routing.routing_profile_factory import RoutingProfileLibraryBlueprint
from pipelex.core.validation import MIGRATE_COMMAND
from pipelex.fix_ops.applier import apply_fix_ops, delete_literally
from pipelex.fix_ops.file_transaction import FileSnapshot, read_file_snapshot
from pipelex.migration.engine import apply_ops_over_text
from pipelex.migration.former_release import (
    ACTIVE_KEY,
    MODEL_SPECS_SECTION_KEY,
    ROUTE_TABLE_KEYS,
    ROUTING_PROFILES_KEY,
    FormerReleaseFinding,
    FormerReleaseFindingKind,
    detect_former_release_across,
    distinct_config_dirs,
    former_release_boot_blockers,
    inference_merge_sequences,
    kit_default_routing_profile_name,
    kit_routing_profile_library_path,
    routing_boots,
)
from pipelex.migration.gitignore import ensure_config_dir_gitignore
from pipelex.migration.plan import FileBlockedReason
from pipelex.migration.runner import FileWriteOutcome, remove_file_with_backup, write_file_with_backup
from pipelex.suggested_fix import RemapValueOp, SetKeyOp
from pipelex.system.configuration.config_loader import (
    BACKENDS_FILE_NAME,
    BACKENDS_OVERRIDE_FILE_NAME,
    ROUTING_PROFILES_FILE_NAME,
    ROUTING_PROFILES_OVERRIDE_FILE_NAME,
)
from pipelex.tools.misc.exceptions import TomlError
from pipelex.tools.misc.json_utils import deep_update
from pipelex.tools.misc.toml_utils import describe_toml_base_and_overrides, load_toml_from_content, load_toml_from_path
from pipelex.tools.typing.pydantic_utils import format_pydantic_validation_error

#: The paragraphs of comments a former release shipped at the head of its documents about its own backends, line by
#: line, as v0.72 wrote them: the Gateway's instructions above the routing profiles. A paragraph at the head of a
#: document goes only when it is one of these exactly; any other, a user's note naming the Gateway included, stays.
_FORMER_RELEASE_HEAD_PARAGRAPHS: frozenset[tuple[str, ...]] = frozenset(
    {
        (
            '# We recommend using the "all_pipelex_gateway" profile to get a head start with all models.',
            "# To use the Pipelex Gateway backend:",
            "# 1. Get your API key at https://app.pipelex.com (free credits included)",
            "# 2. Add it to your .env file: PIPELEX_GATEWAY_API_KEY=your-key-here",
            "# 3. Run `pipelex init` and accept the Gateway terms of service",
        ),
    }
)

_DEFAULT_KEY = "default"

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
    still_blocking: list[str] = Field(default_factory=list[str])
    """What would still stop a boot of this machine once the cleanup is done, each in a sentence: read on every run, off
    the files as the write pass left them, or as a dry run would leave them, and empty when every boot can start."""

    @property
    def is_clean(self) -> bool:
        """Whether there was nothing to do and nothing to say: no file a former release left, and no boot still stopped."""
        return not self.files and not self.still_blocking

    @property
    def removed_paths(self) -> frozenset[Path]:
        """The files the cleanup removes, or would: the ledger replay leaves them out of its walk, written or not."""
        return frozenset(file.file_path for file in self.files if file.action is FormerReleaseFileAction.REMOVE)

    @property
    def applied_files(self) -> list[FormerReleaseFileCleanup]:
        return [file for file in self.files if file.was_applied]

    @property
    def blocked_files(self) -> list[FormerReleaseFileCleanup]:
        return [file for file in self.files if file.is_blocked]

    @property
    def needs_attention(self) -> bool:
        """Whether a file could not be cleaned, or the machine still cannot start once it was: the user has to look."""
        return bool(self.blocked_files) or bool(self.still_blocking)


def clean_former_release(*, config_dirs: Sequence[Path], dry_run: bool, moment: datetime | None = None) -> FormerReleaseCleanup:
    """Remove what a former release left in each configuration directory, keeping a copy of every file.

    The directories are read together, as their boots merge them, and the cleanup is planned per boot
    (`former_release._routing_plan`). Every file's new text is worked out before anything is written, and checked:
    files whose changes would stop a boot that starts today, or change the profile it starts on, are left as they are,
    for a hand edit (`_without_regressions`). That holds for the run's changes taken together: the files are written one
    by one, and one that fails after others were written is reported blocked while those stay written. Then, on every
    run, what would still stop a boot of the machine is read off the files as the cleanup leaves them — after writing,
    or as a dry run would write them — and reported in `still_blocking` rather than as a success.

    Args:
        config_dirs: The directories to clean in tier order, `~/.pipelex/` then a project's `.pipelex/`, as
            `ConfigLoader.existing_config_dirs` lists them; one named twice is cleaned once.
        dry_run: Report what would change and write nothing, not even the `.gitignore` that hides the backups.
        moment: The time the backups are stamped with, one for the whole run; now when not given.

    Returns:
        One entry per file that had something to clean, in the order the directories were given, and what would still
        stop a boot.
    """
    stamp_moment = moment or datetime.now(UTC)
    kit_default = kit_default_routing_profile_name()
    directories = distinct_config_dirs(config_dirs=config_dirs)
    all_findings = detect_former_release_across(config_dirs=directories)
    prepared: list[_PreparedFile] = []
    for findings in all_findings:
        for file_path in findings.file_paths:
            file_findings = [finding for finding in findings.findings if finding.file_path == file_path]
            prepared_file = _prepare_file(
                file_path=file_path, findings=file_findings, kit_default=kit_default, hand_edit=findings.hand_edits.get(file_path)
            )
            if prepared_file is not None:
                prepared.append(prepared_file)
    prepared = _without_regressions(prepared=prepared, config_dirs=directories)
    if dry_run:
        return FormerReleaseCleanup(
            dry_run=True,
            files=[prepared_file.report for prepared_file in prepared],
            still_blocking=what_stops_the_boot(config_dirs=directories, contents=_contents_after(prepared=prepared)),
        )
    for findings in all_findings:
        if not findings.is_clean:
            ensure_config_dir_gitignore(directory=findings.config_dir)
    files = [_write(prepared_file=prepared_file, moment=stamp_moment) for prepared_file in prepared]
    return FormerReleaseCleanup(dry_run=False, files=files, still_blocking=what_stops_the_boot(config_dirs=directories))


def what_stops_the_boot(*, config_dirs: Sequence[Path], contents: Mapping[Path, str | None] | None = None) -> list[str]:
    """What stops a boot of this machine, read off the files each boot merges: the home's alone, and the project's.

    The check the cleanup runs on every run. It names what a former release left that a boot refuses, and a routing
    profile library the boot cannot load — above all an `active` naming a profile no file of the sequence defines,
    which is what a cleanup that removed a profile and missed a file activating it would leave, or one run from another
    project. A sequence without its base file, or with a file that does not parse, is not judged here: those are the
    boot's and `pipelex init`'s to name.

    Args:
        config_dirs: The home directory, then the project's.
        contents: The files as a cleanup would leave them, read in place of the ones at their paths, `None` for a file
            it would remove: what a dry run checks.

    Returns:
        Each problem in a sentence, each once; empty when every boot of the machine can start on these files.
    """
    backends_sequences = inference_merge_sequences(
        config_dirs=config_dirs, file_name=BACKENDS_FILE_NAME, override_file_name=BACKENDS_OVERRIDE_FILE_NAME
    )
    routing_sequences = inference_merge_sequences(
        config_dirs=config_dirs, file_name=ROUTING_PROFILES_FILE_NAME, override_file_name=ROUTING_PROFILES_OVERRIDE_FILE_NAME
    )
    problems: list[str] = []
    for backends_paths, routing_paths in zip(backends_sequences, routing_sequences, strict=True):
        blockers = former_release_boot_blockers(backends_library_paths=backends_paths, routing_profile_library_paths=routing_paths, contents=contents)
        problems.extend(finding.description for finding in blockers)
        if (problem := _routing_library_problem(paths=routing_paths, contents=contents)) is not None:
            problems.append(problem)
    return list(dict.fromkeys(problems))


def _routing_library_problem(*, paths: Sequence[Path], contents: Mapping[Path, str | None] | None) -> str | None:
    """Why the boot could not load this routing profile library, or `None` when it could, or when that is not ours to say."""
    library = _merged_library(paths=paths, contents=contents)
    if library is None:
        return None
    description = describe_toml_base_and_overrides(paths=paths)
    try:
        blueprint = RoutingProfileLibraryBlueprint.model_validate(library)
    except ValidationError as exc:
        return f"the routing profile library {description} is not valid: {format_pydantic_validation_error(exc)}"
    if blueprint.active not in blueprint.profiles:
        return f"the routing profile library {description} makes '{blueprint.active}' the active routing profile, and none of its files defines it"
    return None


def _merged_library(*, paths: Sequence[Path], contents: Mapping[Path, str | None] | None) -> dict[str, Any] | None:
    """The base and its overrides merged as the boot merges them, `contents` standing in for the files it names; `None`
    without a base, or with a file that does not parse.
    """
    merged: dict[str, Any] = {}
    for index, path in enumerate(paths):
        if contents is not None and path in contents:
            text = contents[path]
            if text is None:
                if index == 0:
                    return None
                continue
            try:
                document = load_toml_from_content(text)
            except TomlError:
                return None
        elif path.is_file():
            try:
                document = load_toml_from_path(path)
            except (OSError, TomlError, UnicodeDecodeError):
                return None
        elif index == 0:
            return None
        else:
            continue
        deep_update(merged, updates=document)
    return merged


class _PreparedFile(NamedTuple):
    """One file's cleanup, worked out and not yet written: its report, and what the write pass does with it."""

    report: FormerReleaseFileCleanup
    snapshot: FileSnapshot | None = None
    """The file as read, which the write compares against; `None` for a file already blocked."""

    new_text: str | None = None
    """The text a rewrite writes; `None` for a removal, or a file already blocked."""

    @property
    def is_blocked(self) -> bool:
        return self.report.is_blocked


def _prepare_file(*, file_path: Path, findings: list[FormerReleaseFinding], kit_default: str, hand_edit: str | None) -> _PreparedFile | None:
    """Work one file's cleanup out, or say why it cannot be made; `None` when its findings call for no change of its own."""
    if any(finding.kind.is_a_file_of_its_own for finding in findings):
        return _prepare_removal(file_path=file_path, findings=findings)
    if hand_edit is not None:
        return _PreparedFile(
            report=_blocked(
                file_path=file_path,
                action=FormerReleaseFileAction.REWRITE,
                changes=[finding.description for finding in findings],
                reason=FileBlockedReason.NEEDS_A_HAND_EDIT,
                detail=hand_edit,
            )
        )
    return _prepare_rewrite(file_path=file_path, findings=findings, kit_default=kit_default)


def _prepare_removal(*, file_path: Path, findings: list[FormerReleaseFinding]) -> _PreparedFile:
    changes = [_removal_in_words(finding=finding) for finding in findings]
    try:
        # The path itself, not what a symbolic link names: removing the link is the cleanup, and the file it points
        # at belongs to wherever it lives.
        snapshot = read_file_snapshot(file_path)
    except FileNotFoundError:
        return _PreparedFile(
            report=_blocked(
                file_path=file_path,
                action=FormerReleaseFileAction.REMOVE,
                changes=changes,
                reason=FileBlockedReason.CHANGED_DURING_RUN,
                detail="the file was removed while the cleanup was being prepared",
            )
        )
    except OSError as exc:
        return _PreparedFile(
            report=_blocked(
                file_path=file_path,
                action=FormerReleaseFileAction.REMOVE,
                changes=changes,
                reason=FileBlockedReason.UNREADABLE,
                detail=f"the file could not be read: {exc.strerror or exc}",
            )
        )
    return _PreparedFile(
        report=FormerReleaseFileCleanup(file_path=file_path, action=FormerReleaseFileAction.REMOVE, changes=changes), snapshot=snapshot
    )


def _prepare_rewrite(*, file_path: Path, findings: list[FormerReleaseFinding], kit_default: str) -> _PreparedFile | None:
    descriptions = [finding.description for finding in findings]
    try:
        # Through a symbolic link to the file it names, as the ledger replay rewrites one: replacing the link path
        # would delete the link and leave the real file as it was.
        snapshot = read_file_snapshot(file_path.resolve())
    except FileNotFoundError:
        return _blocked_rewrite(
            file_path=file_path,
            changes=descriptions,
            reason=FileBlockedReason.CHANGED_DURING_RUN,
            detail="the file was removed while the cleanup was being prepared",
        )
    except OSError as exc:
        return _blocked_rewrite(
            file_path=file_path,
            changes=descriptions,
            reason=FileBlockedReason.UNREADABLE,
            detail=f"the file could not be read: {exc.strerror or exc}",
        )
    try:
        text = snapshot.content.decode("utf-8")
        cleaned = cleaned_text(text=text, findings=findings, kit_default=kit_default, is_override=file_path.name in _OVERRIDE_FILE_NAMES)
    except (UnicodeDecodeError, TOMLKitError) as exc:
        # It parsed when it was read for the findings, so this is a file changed since or an operation failing on
        # valid TOML. Either way it is this file's to report, never a reason to stop the run.
        return _blocked_rewrite(
            file_path=file_path, changes=descriptions, reason=FileBlockedReason.UNPARSEABLE, detail=f"the file could not be cleaned: {exc}"
        )
    except ValueError as exc:
        # A change the cleanup could not express on this document — an operation refusing a key, above all. One odd
        # file is left for a hand edit; it never stops the run, the other files, or the doctor reading a dry run.
        reason = format_pydantic_validation_error(exc) if isinstance(exc, ValidationError) else str(exc)
        return _blocked_rewrite(
            file_path=file_path,
            changes=descriptions,
            reason=FileBlockedReason.NEEDS_A_HAND_EDIT,
            detail=(
                f"the cleanup could not express its changes to this file ({reason}). By hand, remove what a former release "
                f"left in it, then run '{MIGRATE_COMMAND}' again"
            ),
        )
    if cleaned.hand_edit is not None:
        return _blocked_rewrite(file_path=file_path, changes=descriptions, reason=FileBlockedReason.NEEDS_A_HAND_EDIT, detail=cleaned.hand_edit)
    if cleaned.text == text:
        return None
    return _PreparedFile(
        report=FormerReleaseFileCleanup(file_path=file_path, action=FormerReleaseFileAction.REWRITE, changes=cleaned.changes),
        snapshot=snapshot,
        new_text=cleaned.text,
    )


def _blocked_rewrite(*, file_path: Path, changes: list[str], reason: FileBlockedReason, detail: str) -> _PreparedFile:
    return _PreparedFile(report=_blocked(file_path=file_path, action=FormerReleaseFileAction.REWRITE, changes=changes, reason=reason, detail=detail))


def _without_regressions(*, prepared: list[_PreparedFile], config_dirs: Sequence[Path]) -> list[_PreparedFile]:
    """The prepared files, less the routing profile rewrites that would stop a boot that starts today.

    The plan already keeps every boot that starts as it is; this reads the texts the cleanup is about to write, as the
    boot would, so that nothing the plan did not foresee — a file whose shape left one of its changes undone — is ever
    written into a state that stops a boot. A boot that started and would not start the same way, on the same profile,
    has the rewrites of the files it reads left for a hand edit, and the texts are read again.
    """
    routing_sequences = inference_merge_sequences(
        config_dirs=config_dirs, file_name=ROUTING_PROFILES_FILE_NAME, override_file_name=ROUTING_PROFILES_OVERRIDE_FILE_NAME
    )
    before = routing_boots(sequences=routing_sequences)
    while True:
        after = routing_boots(sequences=routing_sequences, contents=_contents_after(prepared=prepared))
        stopped = [index for index, (boot, boot_after) in enumerate(zip(before, after, strict=True)) if boot.regresses_to(after=boot_after)]
        culprits = {path: index for index in stopped for path in routing_sequences[index]}
        to_block = [prepared_file for prepared_file in prepared if not prepared_file.is_blocked and prepared_file.report.file_path in culprits]
        if not to_block:
            return prepared
        prepared = [
            _PreparedFile(
                report=_blocked(
                    file_path=prepared_file.report.file_path,
                    action=prepared_file.report.action,
                    changes=prepared_file.report.changes,
                    reason=FileBlockedReason.NEEDS_A_HAND_EDIT,
                    detail=(
                        f"cleaning this file would stop {_boot_name(index=culprits[prepared_file.report.file_path], count=len(routing_sequences))} "
                        f"from starting as it does now, so it is left as it is. By hand, remove what a former release left in it, keeping "
                        f"each routing profile you start on whole, then run '{MIGRATE_COMMAND}' again"
                    ),
                )
            )
            if prepared_file in to_block
            else prepared_file
            for prepared_file in prepared
        ]


def _boot_name(*, index: int, count: int) -> str:
    if count < 2:
        return "Pipelex"
    return ("the boot outside the project", "the project's boot")[index]


def _contents_after(*, prepared: Sequence[_PreparedFile]) -> dict[Path, str | None]:
    """Each file the cleanup writes, as it will be: its new text, or nothing for a file it removes."""
    contents: dict[Path, str | None] = {}
    for prepared_file in prepared:
        if prepared_file.is_blocked:
            continue
        if prepared_file.report.action is FormerReleaseFileAction.REMOVE:
            contents[prepared_file.report.file_path] = None
        elif prepared_file.new_text is not None:
            contents[prepared_file.report.file_path] = prepared_file.new_text
    return contents


def _write(*, prepared_file: _PreparedFile, moment: datetime) -> FormerReleaseFileCleanup:
    """Make one prepared change, with its backup, through the per-file transaction; a blocked file is reported as it is."""
    report = prepared_file.report
    if prepared_file.is_blocked or prepared_file.snapshot is None:
        return report
    if report.action is FormerReleaseFileAction.REMOVE:
        outcome = remove_file_with_backup(snapshot=prepared_file.snapshot, moment=moment)
    elif prepared_file.new_text is not None:
        outcome = write_file_with_backup(snapshot=prepared_file.snapshot, new_content=prepared_file.new_text, moment=moment)
    else:
        return report
    return _with_outcome(file_path=report.file_path, action=report.action, changes=report.changes, outcome=outcome)


class CleanedText(NamedTuple):
    """One document's cleanup: the text, the changes in words, or why it is left for a person to edit."""

    text: str
    changes: list[str]
    hand_edit: str | None = None
    """What the user has to change by hand, when the cleanup cannot rewrite this document safely; the text is then
    the document as read."""


class _Deletion(NamedTuple):
    """One key or table deleted where the document spells it: a `*` in the path or the key is a key spelled so."""

    table_path: tuple[str, ...]
    key: str


#: One edit of a document: a deletion, or a migration op writing a value — the moved `active`, or the project's own one.
_Edit = _Deletion | RemapValueOp | SetKeyOp


def _apply_edit(*, text: str, edit: _Edit) -> tuple[str, bool]:
    """The document with one edit made, re-read from its text, and whether the edit changed anything."""
    match edit:
        case _Deletion():
            document = tomlkit.loads(text)
            if not delete_literally(toml_doc=document, table_path=edit.table_path, key=edit.key):
                return text, False
            return tomlkit.dumps(document), True  # pyright: ignore[reportUnknownMemberType]
        case RemapValueOp():
            application = apply_ops_over_text(text=text, ops=[edit])
            return application.text, application.applied_count > 0
        case SetKeyOp():
            # Not a migration op, which never writes a value of its own: applied to the document directly.
            document = tomlkit.loads(text)
            applications = apply_fix_ops(toml_doc=document, ops=[edit])
            new_text = tomlkit.dumps(document)  # pyright: ignore[reportUnknownMemberType]
            return new_text, applications[0].outcome.did_apply and new_text != text


class _KitProfilePlacement(StrEnum):
    ADDED = "added"
    ALREADY_THERE = "already_there"
    IMPOSSIBLE = "impossible"


def cleaned_text(*, text: str, findings: Sequence[FormerReleaseFinding], kit_default: str, is_override: bool) -> CleanedText:
    """One document without what a former release left in it, and each change in words.

    The kit's default profile goes in first, ahead of the deletions, so that the banner heading the profiles stays at
    the head of them instead of leaving with the first profile it introduced. When it cannot go in — the profiles are
    one inline table — the active profile is not moved to it either, and nothing is changed: an `active` naming a
    profile the file lacks would stop the boot as surely, so the document is left for a hand edit. The comments at
    the head of the document go last, and only from a document something else changed.

    Args:
        text: The document as read.
        findings: What `detect_former_release_across` found in this document.
        kit_default: The routing profile the kit makes active.
        is_override: Whether the document is a personal override, whose retired `active` is deleted rather than moved.

    Returns:
        The cleaned text, the same string when nothing changed, and the changes made, in order; or the document as
        read and what to edit by hand.
    """
    changes: list[str] = []
    current_text = text
    edits: list[tuple[_Edit, str]] = []
    for finding in findings:
        edits.extend(_ops_for(finding=finding, kit_default=kit_default, is_override=is_override))

    moves_active = any(isinstance(edit, RemapValueOp) for edit, _ in edits)
    if moves_active:
        document = tomlkit.loads(current_text)
        match _add_kit_profile(document=document, kit_default=kit_default):
            case _KitProfilePlacement.ADDED:
                current_text = tomlkit.dumps(document)  # pyright: ignore[reportUnknownMemberType]
                changes.append(f"added the routing profile '{kit_default}', as this release ships it")
            case _KitProfilePlacement.ALREADY_THERE:
                pass
            case _KitProfilePlacement.IMPOSSIBLE:
                return CleanedText(text=text, changes=[], hand_edit=_inline_profiles_hand_edit(kit_default=kit_default))

    for edit, change in edits:
        current_text, applied = _apply_edit(text=current_text, edit=edit)
        if applied:
            changes.append(change)
    current_text = _without_emptied_profiles(text=current_text, findings=findings)
    if current_text == text:
        return CleanedText(text=text, changes=[])

    document = tomlkit.loads(current_text)
    if _drop_former_release_comments(document=document):
        current_text = tomlkit.dumps(document)  # pyright: ignore[reportUnknownMemberType]
        changes.append("removed a comment about the Pipelex Gateway")
    return CleanedText(text=current_text, changes=_deduplicated(changes=changes))


def _without_emptied_profiles(*, text: str, findings: Sequence[FormerReleaseFinding]) -> str:
    """The document without a profile table that losing its retired `default` left empty.

    An override that only retargeted a profile is a `[profiles.<name>]` table holding that one key: once the key goes,
    the header overrides nothing, and it goes too, with no change line of its own, since the key's says what happened.
    """
    retargeted = {finding.subject for finding in findings if finding.kind is FormerReleaseFindingKind.RETIRED_PROFILE_DEFAULT}
    if not retargeted:
        return text
    profiles = load_toml_from_content(text).get(ROUTING_PROFILES_KEY)
    if not isinstance(profiles, dict):
        return text
    emptied = [
        name
        for name, profile in cast("dict[str, Any]", profiles).items()
        if name in retargeted and isinstance(profile, dict) and not cast("dict[str, Any]", profile)
    ]
    for name in emptied:
        text, _ = _apply_edit(text=text, edit=_Deletion(table_path=(ROUTING_PROFILES_KEY,), key=name))
    return text


def _inline_profiles_hand_edit(*, kit_default: str) -> str:
    return (
        f"the routing profiles are written as one inline table, where the cleanup cannot add the profile '{kit_default}' to make it "
        f"active in place of the former release's. By hand, either write each profile as a [profiles.<name>] table, or make one of "
        f"your own profiles active, then run '{MIGRATE_COMMAND}' again"
    )


def _ops_for(*, finding: FormerReleaseFinding, kit_default: str, is_override: bool) -> list[tuple[_Edit, str]]:
    """The edits that remove one finding from its document, each with its change in words.

    Every key and table is deleted where the document spells it (`_Deletion`), so a route or a profile spelled `*` is
    that one key, never the "every key" a migration op reads `*` as.
    """
    match finding.kind:
        case FormerReleaseFindingKind.RETIRED_BACKEND_TABLE:
            return [(_Deletion(table_path=(), key=_subject_of(finding=finding)), f"removed the '{finding.subject}' backend")]
        case FormerReleaseFindingKind.MODEL_SPECS_SECTION_KEY:
            return [
                (
                    _Deletion(table_path=(_subject_of(finding=finding),), key=MODEL_SPECS_SECTION_KEY),
                    f"removed '{MODEL_SPECS_SECTION_KEY}' from the '{finding.subject}' backend",
                )
            ]
        case FormerReleaseFindingKind.RETIRED_ROUTING_PROFILE:
            return [
                (_Deletion(table_path=(ROUTING_PROFILES_KEY,), key=_subject_of(finding=finding)), f"removed the routing profile '{finding.subject}'")
            ]
        case FormerReleaseFindingKind.RETIRED_PROFILE_DEFAULT:
            return [
                (
                    _Deletion(table_path=(ROUTING_PROFILES_KEY, _subject_of(finding=finding)), key=_DEFAULT_KEY),
                    f"removed '{_DEFAULT_KEY}', which named '{finding.retired_backend}', from the routing profile '{finding.subject}'",
                )
            ]
        case FormerReleaseFindingKind.ROUTE_TO_RETIRED_BACKEND:
            route_table = finding.route_table or ROUTE_TABLE_KEYS[0]
            route_pattern = finding.route_pattern or ""
            return [
                (
                    _Deletion(table_path=(ROUTING_PROFILES_KEY, _subject_of(finding=finding), route_table), key=route_pattern),
                    f"removed the route of '{route_pattern}' to '{finding.retired_backend}' from the routing profile '{finding.subject}'",
                )
            ]
        case FormerReleaseFindingKind.ACTIVE_ROUTING_PROFILE:
            if not finding.profile_is_removed:
                # The plan keeps this `active`: what made its profile retired — a route, or a retired `default` another
                # file overrides — is a finding of its own, in the file that holds it, and goes there; or moving it would
                # change the profile another boot starts on, and the project's override makes up the difference.
                return []
            if is_override:
                return [
                    (
                        _Deletion(table_path=(), key=ACTIVE_KEY),
                        f"removed '{ACTIVE_KEY}', which named the routing profile '{finding.subject}', so the file read before this one decides",
                    )
                ]
            return [
                (
                    RemapValueOp(table_path=[], key=ACTIVE_KEY, mapping={_subject_of(finding=finding): kit_default}),
                    f"moved the active routing profile from '{finding.subject}' to '{kit_default}'",
                )
            ]
        case FormerReleaseFindingKind.PROJECT_ACTIVE_ROUTING_PROFILE:
            return [
                (
                    SetKeyOp(table_path=[], key=ACTIVE_KEY, value=_subject_of(finding=finding)),
                    (
                        f"set '{ACTIVE_KEY}' to the routing profile '{finding.subject}' for this project's boot alone, since the file it "
                        f"read '{ACTIVE_KEY}' from changes for the boot outside the project"
                    ),
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
            | FormerReleaseFindingKind.RETIRED_PROFILE_DEFAULT
            | FormerReleaseFindingKind.ROUTE_TO_RETIRED_BACKEND
            | FormerReleaseFindingKind.ACTIVE_ROUTING_PROFILE
            | FormerReleaseFindingKind.PROJECT_ACTIVE_ROUTING_PROFILE
        ):
            return finding.description


def _add_kit_profile(*, document: TOMLDocument, kit_default: str) -> _KitProfilePlacement:
    """Put the kit's default profile first among the document's profiles, as the kit ships it, unless it is there.

    Copied from the kit's own document, so its comments come with it and it lands as `pipelex init` would write it.
    An inline `profiles` table, which no release wrote, cannot take it without being restructured, and is not.
    """
    profiles: Table | None = None
    if ROUTING_PROFILES_KEY in document:
        existing = document.item(ROUTING_PROFILES_KEY)
        if isinstance(existing, OutOfOrderTableProxy):
            if kit_default in existing:
                return _KitProfilePlacement.ALREADY_THERE
            # Profiles spread across the file between other tables: the profile joins them where tomlkit puts it.
            existing[kit_default] = _kit_profile(kit_default=kit_default)
            return _KitProfilePlacement.ADDED
        if not isinstance(existing, Table):
            if isinstance(existing, dict) and kit_default in existing:
                return _KitProfilePlacement.ALREADY_THERE
            return _KitProfilePlacement.IMPOSSIBLE
        if kit_default in existing:
            return _KitProfilePlacement.ALREADY_THERE
        profiles = existing
    if profiles is None:
        profiles = tomlkit.table(is_super_table=True)
        document.append(ROUTING_PROFILES_KEY, profiles)
    if len(profiles.value) == 0:
        profiles.append(kit_default, _kit_profile(kit_default=kit_default))
    else:
        profiles.value._insert_at(0, kit_default, _kit_profile(kit_default=kit_default))  # ruff: ignore[private-member-access] # pyright: ignore[reportPrivateUsage]
    return _KitProfilePlacement.ADDED


def _kit_profile(*, kit_default: str) -> Item:
    kit_path = kit_routing_profile_library_path()
    kit_profiles = tomlkit.loads(kit_path.read_text(encoding="utf-8")).item(ROUTING_PROFILES_KEY)
    if not isinstance(kit_profiles, Table) or kit_default not in kit_profiles:
        msg = f"the kit's routing profile library '{kit_path}' does not define its active profile '{kit_default}' — packaging bug"
        raise PipelexUnexpectedError(msg)
    return copy.deepcopy(kit_profiles.value.item(kit_default))


def _drop_former_release_comments(*, document: TOMLDocument) -> bool:
    """Drop each paragraph of comments at the document's head that a former release shipped about its backends.

    The head is the root of the document, ahead of its first table: where a release wrote the instructions for the
    file, and where a user's notes sit too, above the first table or between `active` and it. So a paragraph goes
    only when it is, line for line, one the release shipped (`_FORMER_RELEASE_HEAD_PARAGRAPHS`); one that merely
    names the Gateway is the user's. A paragraph is a run of comment lines between blank ones; it goes whole, with
    the blank line after it. The items are blanked in place rather than removed, which keeps the container's indexes
    valid; they render as nothing.
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
        paragraph = tuple(item.as_string().strip() for _, item in body[index:end])
        if paragraph in _FORMER_RELEASE_HEAD_PARAGRAPHS:
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
