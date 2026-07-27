"""Fix convergence loop — validate → collect SAFE fixes → apply per file → re-validate.

Reuses ``validate_bundle`` wholesale (THE validator — no parallel validation pipeline).
Cascades are expected: fixing one pipe can surface the next mismatch, so the loop runs to a
fixed point bounded by ``max_iterations``. Non-convergence is a first-class, loudly-reported
outcome: a fix fingerprint proposed twice (e.g. its ops target a synthetic pipe the applier
skips) ends the loop with a ``bail_reason`` instead of spinning.

Multi-file targeting: each fix carries the declaring file as ``source`` (backfilled at the
``validate_bundle`` catch boundary from the library manager's pipe-source map), and the loop
applies it to that file — grouping the iteration's fixes per target, one tomlkit DOM per file.
Two scoping rules bound what gets touched:

- **Single-file gate** (source-less fixes): derived from the RESOLVED library dirs
  (``resolve_library_dirs``), not the raw argument — an explicit ``[]`` is genuinely
  single-file, while a ``None`` that falls through to ambient dirs (hub defaults,
  ``PIPELEXPATH``) is multi-file, where a source-less fix could patch the wrong same-named
  table and is conservatively dropped.
- **Write scope**: only files the user passed to THIS command are ever written — the entry
  file plus ``.mthds`` files under the per-call ``library_dirs``. Fixes sourced at files
  loaded via ambient resolution are excluded; when every fix is out of scope the loop bails
  loudly, naming the files and the ``-L`` remedy.
"""

import os
import stat
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any, NamedTuple, cast

import tomlkit
from pydantic import BaseModel, ConfigDict, Field

from pipelex.base_exceptions import ValidationErrorItem
from pipelex.config import get_config
from pipelex.core.pipes.pipe_blueprint import SIGNATURE_ONLY_KEYS
from pipelex.interpreter_hub import resolve_library_dirs
from pipelex.libraries.library_utils import get_pipelex_mthds_files_from_dirs
from pipelex.pipeline.exceptions import FixTransactionError, FixWriteConflictError, ValidateBundleError
from pipelex.pipeline.fixes.applicability import is_safe_fix_for_load_scope, is_target_in_write_scope
from pipelex.pipeline.fixes.applier import apply_fix_ops, serialize_and_format
from pipelex.pipeline.validate_bundle import validate_bundle
from pipelex.pipeline.validation_errors import build_validation_error_items
from pipelex.suggested_fix import FixOp, FixOpKind, SuggestedFix
from pipelex.tools.misc.exceptions import TomlError
from pipelex.tools.misc.toml_utils import load_toml_from_path

_MAIN_PIPE_KEY = "main_pipe"


class _FileSnapshot(NamedTuple):
    """Bytes and permission bits read from one target before fixes are applied."""

    path: Path
    content: bytes
    mode: int
    device: int
    inode: int


class _PendingFileUpdate(NamedTuple):
    """A fully rendered replacement paired with the snapshot it was derived from."""

    snapshot: _FileSnapshot
    new_content: str


class _StagedFileUpdate(NamedTuple):
    """Same-directory temp files for one replacement and its rollback copy."""

    snapshot: _FileSnapshot
    replacement_snapshot: _FileSnapshot
    rollback_path: Path


class _BoundFix(NamedTuple):
    """A suggested fix pinned to the source identity snapshotted before validation."""

    fix: SuggestedFix
    snapshot: _FileSnapshot

    @property
    def target_path(self) -> Path:
        return self.snapshot.path


def _read_file_snapshot(path: Path) -> _FileSnapshot:
    """Read bytes and mode from one open file descriptor, avoiding split stat/read state."""
    with path.open("rb") as file:
        content = file.read()
        file_stat = os.fstat(file.fileno())
    return _FileSnapshot(
        path=path,
        content=content,
        mode=stat.S_IMODE(file_stat.st_mode),
        device=file_stat.st_dev,
        inode=file_stat.st_ino,
    )


def _write_staged_file(*, snapshot: _FileSnapshot, content: bytes, label: str) -> Path:
    """Write and fsync a same-directory temp file ready for atomic replacement."""
    temp_file = tempfile.NamedTemporaryFile(  # noqa: SIM115 - closed before the atomic replace
        mode="wb",
        dir=str(snapshot.path.parent),
        prefix=f".{snapshot.path.name}.pipelex-fix-{label}.",
        suffix=".tmp",
        delete=False,
    )
    temp_path = Path(temp_file.name)
    try:
        try:
            temp_file.write(content)
            os.fchmod(temp_file.fileno(), snapshot.mode)
            temp_file.flush()
            os.fsync(temp_file.fileno())
        finally:
            temp_file.close()
    except OSError:
        temp_path.unlink(missing_ok=True)
        raise
    return temp_path


def _stage_file_update(update: _PendingFileUpdate) -> _StagedFileUpdate:
    replacement_path = _write_staged_file(snapshot=update.snapshot, content=update.new_content.encode("utf-8"), label="new")
    try:
        replacement_snapshot = _read_file_snapshot(replacement_path)
        rollback_path = _write_staged_file(snapshot=update.snapshot, content=update.snapshot.content, label="rollback")
    except OSError:
        replacement_path.unlink(missing_ok=True)
        raise
    return _StagedFileUpdate(snapshot=update.snapshot, replacement_snapshot=replacement_snapshot, rollback_path=rollback_path)


def _file_state_matches(*, current_snapshot: _FileSnapshot, expected_snapshot: _FileSnapshot) -> bool:
    """Whether content, permissions, and filesystem identity still match an observed file."""
    return (
        current_snapshot.content == expected_snapshot.content
        and current_snapshot.mode == expected_snapshot.mode
        and current_snapshot.device == expected_snapshot.device
        and current_snapshot.inode == expected_snapshot.inode
    )


def _assert_snapshot_unchanged(snapshot: _FileSnapshot) -> None:
    """Verify that a path still names the exact file state previously observed."""
    try:
        current_snapshot = _read_file_snapshot(snapshot.path)
    except FileNotFoundError as exc:
        msg = f"refusing to overwrite '{snapshot.path}': the file was removed while fixes were being prepared"
        raise FixWriteConflictError(msg) from exc
    if not _file_state_matches(current_snapshot=current_snapshot, expected_snapshot=snapshot):
        msg = f"refusing to overwrite '{snapshot.path}': the file changed while fixes were being prepared"
        raise FixWriteConflictError(msg)


def _rollback_committed_updates(committed_updates: list[_StagedFileUpdate]) -> list[str]:
    """Restore targets still owned by this transaction, returning rollback failures."""
    failures: list[str] = []
    for staged_update in reversed(committed_updates):
        target_path = staged_update.snapshot.path
        try:
            current_snapshot = _read_file_snapshot(target_path)
            if not _file_state_matches(current_snapshot=current_snapshot, expected_snapshot=staged_update.replacement_snapshot):
                failures.append(f"{target_path}: file changed after the autofix replacement was committed")
                continue
            staged_update.rollback_path.replace(target_path)
        except OSError as exc:
            failures.append(f"{target_path}: {exc}")
    return failures


def _commit_staged_updates(staged_updates: list[_StagedFileUpdate]) -> None:
    committed_updates: list[_StagedFileUpdate] = []
    try:
        for staged_update in staged_updates:
            # Accepted portability tradeoff: this check and Path.replace() are not one compare-and-swap operation.
            # An edit in the tiny gap can be overwritten; keep this portable unless real-world evidence justifies serialization.
            _assert_snapshot_unchanged(staged_update.snapshot)
            staged_update.replacement_snapshot.path.replace(staged_update.snapshot.path)
            committed_updates.append(staged_update)
    except (FixWriteConflictError, OSError) as exc:
        rollback_failures = _rollback_committed_updates(committed_updates)
        if rollback_failures:
            failures = "; ".join(rollback_failures)
            msg = f"autofix commit failed and rollback was incomplete ({failures}); inspect the named files before retrying"
            raise FixTransactionError(msg) from exc
        raise


def _cleanup_staged_updates(staged_updates: list[_StagedFileUpdate]) -> list[str]:
    """Remove transaction temps and record cleanup failures for the caller to report."""
    failures: list[str] = []
    for staged_update in staged_updates:
        for temp_path in (staged_update.replacement_snapshot.path, staged_update.rollback_path):
            try:
                temp_path.unlink(missing_ok=True)
            except OSError as exc:
                failures.append(f"{temp_path}: {exc}")
    return failures


def _commit_file_updates(updates: list[_PendingFileUpdate]) -> None:
    """Stage a round completely, then atomically replace targets with rollback on failure."""
    staged_updates: list[_StagedFileUpdate] = []
    try:
        for update in updates:
            staged_updates.append(_stage_file_update(update))
        _commit_staged_updates(staged_updates)
    finally:
        cleanup_failures = _cleanup_staged_updates(staged_updates)
        active_exception = sys.exception()
        if cleanup_failures and active_exception is not None:
            active_exception.add_note(f"autofix temporary-file cleanup also failed ({'; '.join(cleanup_failures)})")
        elif cleanup_failures:
            failures = "; ".join(cleanup_failures)
            msg = f"autofix target changes were committed, but temporary-file cleanup failed ({failures})"
            raise FixTransactionError(msg)


class FixBundleResult(BaseModel):
    """Outcome of one fix run: the final verdict, the work done, and what remains."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    is_valid: bool
    iterations: int
    """Number of apply rounds performed (0 when the bundle was already valid)."""
    fixes_applied: list[SuggestedFix]
    """Fixes with at least one op actually applied, in application order."""
    files_written: list[str] = Field(default_factory=list)
    """Distinct files written, in first-write order across iterations (resolved paths)."""
    remaining_errors: list[ValidationErrorItem]
    """The last failed validation's structured errors; empty when ``is_valid``."""
    pending_signatures: list[str] | None = None
    """Qualified refs still declared as ``PipeSignature`` after a successful validation."""
    is_runnable: bool | None = None
    """Whether the fixed bundle has no pending ``PipeSignature`` placeholders."""
    bail_reason: str | None = None
    """Why the loop stopped early (no-progress repeat, out-of-scope targets, cross-file
    collision, max_iterations), if it did."""


def _fix_fingerprint(fix: SuggestedFix) -> str:
    """Stable identity of a fix attempt: fix_code + source + each op's (kind, path, key, value, new_key).

    ``new_key`` participates so two ``rename_table_key`` ops that differ only in their target name
    are distinct fingerprints (they would otherwise collide and trip the no-progress bail).
    """
    op_parts = [f"{op.kind}:{'.'.join(op.table_path)}:{op.key}:{op.value!r}:{op.new_key}" for op in fix.ops]
    return f"{fix.fix_code}|{fix.source}|{'|'.join(op_parts)}"


def _validation_error_items(exc: ValidateBundleError) -> list[ValidationErrorItem]:
    """Project the error's categorized lists into wire items — same channels as ``to_error_report``."""
    return build_validation_error_items(
        blueprint_errors=exc.pipelex_bundle_blueprint_validation_errors,
        factory_errors=exc.pipe_factory_errors,
        pipe_validation_errors=exc.pipe_validation_error_data,
        dry_run_error_message=exc.dry_run_error_message,
        fallback_message=exc.message,
    )


def _pending_signatures_from_validation_result(validation_result: Any) -> list[str]:
    """Pending signatures reported by validation, defaulting to none for success-only mocks."""
    pending_signatures = getattr(validation_result, "pending_signatures", None)
    if not isinstance(pending_signatures, list):
        return []
    typed_pending_signatures = cast("list[Any]", pending_signatures)
    validated_pending_signatures: list[str] = []
    for pipe_ref in typed_pending_signatures:
        if not isinstance(pipe_ref, str):
            return []
        validated_pending_signatures.append(pipe_ref)
    return validated_pending_signatures


def _absolute_source_path(path: Path) -> Path:
    """Normalize a source pathname without following symlinks."""
    return Path(os.path.abspath(path))


def _snapshot_loaded_sources(*, entry_source_path: Path, effective_dirs: Sequence[Path]) -> dict[Path, _FileSnapshot]:
    """Snapshot every source identity validation is about to load.

    Keys are lexical absolute source names, while each snapshot is pinned to the destination
    resolved at the same time. The resolved destination is also an alias when unambiguous, which
    accommodates injected managers that already report canonical source paths.
    """
    source_paths: set[Path] = {_absolute_source_path(entry_source_path)}
    source_paths.update(
        _absolute_source_path(mthds_path)
        for mthds_path in get_pipelex_mthds_files_from_dirs(dirs={_absolute_source_path(directory) for directory in effective_dirs})
    )
    snapshots_by_source: dict[Path, _FileSnapshot] = {}
    for source_path in sorted(source_paths, key=str):
        target_path = source_path.resolve()
        snapshot = _read_file_snapshot(target_path)
        snapshots_by_source[source_path] = snapshot
        snapshots_by_source.setdefault(target_path, snapshot)
    return snapshots_by_source


def _bind_fixes_to_snapshots(
    fixes: list[SuggestedFix],
    *,
    entry_source_path: Path,
    snapshots_by_source: dict[Path, _FileSnapshot],
) -> list[_BoundFix]:
    """Bind each fix once to the pre-validation file identity that supplied its source."""
    bound_fixes: list[_BoundFix] = []
    for fix in fixes:
        source_path = entry_source_path if fix.source is None else Path(fix.source)
        absolute_source = _absolute_source_path(source_path)
        snapshot = snapshots_by_source.get(absolute_source)
        if snapshot is None:
            msg = f"refusing to apply fix from '{absolute_source}': its source identity changed during validation"
            raise FixWriteConflictError(msg)
        try:
            current_target = absolute_source.resolve(strict=True)
        except FileNotFoundError as exc:
            msg = f"refusing to apply fix from '{absolute_source}': its source was removed during validation"
            raise FixWriteConflictError(msg) from exc
        if current_target != snapshot.path:
            msg = f"refusing to apply fix from '{absolute_source}': its source was retargeted during validation"
            raise FixWriteConflictError(msg)
        _assert_snapshot_unchanged(snapshot)
        bound_fixes.append(_BoundFix(fix=fix, snapshot=snapshot))
    return bound_fixes


def _safe_fixes(
    items: list[ValidationErrorItem],
    *,
    is_single_file: bool,
    select_codes: Sequence[str] | None,
    ignore_codes: Sequence[str] | None,
) -> list[SuggestedFix]:
    """SAFE fixes whose target file is provable, filtered by the caller's rule selection.

    A source-less fix is only trustworthy under single-file validation: with library files
    merged in, a same-named pipe from another domain could resolve to this file's table
    (pipe codes are only unique per domain), so source-less fixes are dropped rather than
    risk patching an unrelated pipe.

    ``select_codes`` keeps only the named rules; ``ignore_codes`` drops them. Code validation
    (unknown code → loud rejection) belongs to the CLI layer, not here — the loop just filters.
    """
    fixes: list[SuggestedFix] = []
    for item in items:
        suggested_fix = item.suggested_fix
        if suggested_fix is None or not is_safe_fix_for_load_scope(suggested_fix, is_single_file=is_single_file):
            continue
        if select_codes is not None and suggested_fix.fix_code not in select_codes:
            continue
        if ignore_codes is not None and suggested_fix.fix_code in ignore_codes:
            continue
        fixes.append(suggested_fix)
    return fixes


def _partition_by_write_scope(
    fixes: list[_BoundFix],
    *,
    entry_path: Path,
    writable_dirs: Sequence[Path],
) -> tuple[list[_BoundFix], list[Path]]:
    """Split fixes into (writable, out-of-scope target paths).

    Writable = the entry file, plus anything under a per-call ``library_dirs`` directory.
    Files loaded via ambient resolution (hub defaults, ``PIPELEXPATH``) are read-only: the
    user did not pass them to THIS command, so their fixes are excluded rather than applied.
    """
    in_scope: list[_BoundFix] = []
    out_of_scope_paths: list[Path] = []
    for fix in fixes:
        target_path = fix.target_path
        if is_target_in_write_scope(target_path, entry_path=entry_path, writable_dirs=writable_dirs):
            in_scope.append(fix)
        else:
            out_of_scope_paths.append(target_path)
    return in_scope, out_of_scope_paths


def _is_signature_pipe_section(pipe_section: Any) -> bool:
    """Whether a raw ``[pipe.<code>]`` section is a typeless contract-only signature."""
    if not isinstance(pipe_section, dict):
        return False
    typed_section = cast("dict[Any, Any]", pipe_section)
    return "type" not in typed_section and all(key in SIGNATURE_ONLY_KEYS for key in typed_section)


def _pipe_codes_by_file(*, entry_path: Path, effective_dirs: Sequence[Path]) -> dict[Path, set[str]]:
    """Concrete pipe declaration keys of every loaded bundle file, keyed by resolved path.

    Cross-domain on purpose: a bare pipe code must resolve unambiguously across the loaded
    library — ``PipeLibrary.get_optional_pipe`` raises on a bare code declared by two domains —
    so a rename target colliding with a same-named declaration in ANY other loaded file would
    leave the library unloadable. Signature-only headers are excluded: a matching concrete
    definition is allowed to replace a ``PipeSignature`` during crate merge, so treating the
    header as a hard collision would block a valid fix. Rebuilt each iteration: multiple files
    can now mutate per round. A file that fails to parse contributes nothing here — its own
    problems surface through validation, not this scan.
    """
    all_paths: set[Path] = {entry_path}
    all_paths.update(mthds_path.resolve() for mthds_path in get_pipelex_mthds_files_from_dirs(dirs=set(effective_dirs)))
    codes_by_file: dict[Path, set[str]] = {}
    for mthds_path in all_paths:
        try:
            toml_doc = load_toml_from_path(mthds_path)
        except TomlError:
            continue
        pipe_section = toml_doc.get("pipe")
        if isinstance(pipe_section, dict):
            codes_by_file[mthds_path] = {
                key
                for key, section in cast("dict[Any, Any]", pipe_section).items()
                if isinstance(key, str) and not _is_signature_pipe_section(section)
            }
        else:
            codes_by_file[mthds_path] = set()
    return codes_by_file


def _colliding_op_name(
    fix_op: FixOp,
    *,
    target_file_pipe_codes: set[str],
    other_file_pipe_codes: set[str],
) -> str | None:
    """The pipe code this op would collide with across files, or ``None`` when it cannot.

    Two op shapes can write a bare pipe code that another loaded file already declares:

    - a ``[pipe]`` ``rename_table_key`` whose ``new_key`` is declared elsewhere — applying it
      would create a duplicate declaration (same domain) or a bare-code ambiguity (another
      domain) that the loop can never repair;
    - a root ``main_pipe`` ``set_key`` whose value is declared elsewhere while the target file
      does NOT declare that value — its paired declaration rename is exactly the case above
      (dropped), so applying the ``set_key`` alone would write an orphaned ``main_pipe``
      pointing at a pipe this file will never declare. If the target file already declares the
      value, the ``main_pipe`` remains bundle-local and safe despite same-named sibling pipes.
      The categorizer cannot see cross-file state, so this suppression lives here.
    """
    match fix_op.kind:
        case FixOpKind.RENAME_TABLE_KEY:
            if fix_op.table_path == ["pipe"] and fix_op.new_key is not None and fix_op.new_key in other_file_pipe_codes:
                return fix_op.new_key
            return None
        case FixOpKind.SET_KEY:
            if (
                not fix_op.table_path
                and fix_op.key == _MAIN_PIPE_KEY
                and isinstance(fix_op.value, str)
                and fix_op.value in other_file_pipe_codes
                and fix_op.value not in target_file_pipe_codes
            ):
                return fix_op.value
            return None
        case FixOpKind.ENSURE_TABLE | FixOpKind.DELETE_KEY | FixOpKind.DELETE_TABLE:
            return None


def _split_cross_file_collisions(
    fixes: list[_BoundFix],
    *,
    codes_by_file: dict[Path, set[str]],
) -> tuple[list[_BoundFix], list[str]]:
    """Split ``fixes`` into (kept, colliding pipe codes of the dropped ones).

    The raise-site collision gate only sees the one file being validated; in a multi-file run a
    bare pipe of the same name may live in another loaded file, where writing it (as a ``[pipe]``
    key rename or a ``main_pipe`` value) would create a state the loop can never repair. Each
    fix is checked against the pipe codes of every loaded file OTHER than its own target.
    Dropped fixes simply leave their error unfixed (still reported in ``remaining_errors``).
    """
    kept: list[_BoundFix] = []
    colliding_names: list[str] = []
    other_codes_cache: dict[Path, set[str]] = {}
    for fix in fixes:
        target_path = fix.target_path
        target_codes = codes_by_file.get(target_path, set())
        other_codes = other_codes_cache.get(target_path)
        if other_codes is None:
            other_codes = set[str]()
            for file_path, file_codes in codes_by_file.items():
                if file_path != target_path:
                    other_codes.update(file_codes)
            other_codes_cache[target_path] = other_codes
        fix_collisions = [
            name
            for fix_op in fix.fix.ops
            if (
                name := _colliding_op_name(
                    fix_op,
                    target_file_pipe_codes=target_codes,
                    other_file_pipe_codes=other_codes,
                )
            )
            is not None
        ]
        if fix_collisions:
            colliding_names.extend(fix_collisions)
        else:
            kept.append(fix)
    return kept, colliding_names


async def fix_bundle_file(
    mthds_file_path: Path,
    *,
    library_dirs: Sequence[Path] | None = None,
    writable_library_dirs: Sequence[Path] | None = None,
    allow_signatures: bool = False,
    max_iterations: int | None = None,
    select_codes: Sequence[str] | None = None,
    ignore_codes: Sequence[str] | None = None,
) -> FixBundleResult:
    """Fix a bundle in place until valid, out of fixes, no progress, or max_iterations.

    Each iteration: validate; on failure collect the SAFE suggested fixes riding the
    structured errors; group the unseen ones by the file they target (declaring file via
    ``source``, entry file for source-less); apply each group to its file's tomlkit DOM
    (style-preserving) and write the changed files; re-validate. Only fixes with at least one
    applied op count in ``fixes_applied``. ``allow_signatures`` mirrors ``validate bundle``:
    signature placeholders are tolerated for the exit gate only, while the success result still
    reports ``pending_signatures`` and ``is_runnable``. ``max_iterations=None`` resolves to the
    ``fix_loop_max_attempts`` builder config. ``select_codes`` / ``ignore_codes`` filter which fix
    rules may apply (see ``_safe_fixes``); the CLI validates the codes before calling.
    """
    if max_iterations is None:
        max_iterations = get_config().pipelex.builder_config.fix_loop_max_attempts
    entry_source_path = _absolute_source_path(mthds_file_path)
    entry_path = entry_source_path.resolve()
    effective_dirs, _ = resolve_library_dirs(library_dirs)
    is_single_file = not effective_dirs
    write_scope_dirs = library_dirs if writable_library_dirs is None else writable_library_dirs
    writable_dirs: list[Path] = [Path(writable_dir).resolve() for writable_dir in write_scope_dirs] if write_scope_dirs is not None else []

    seen_fingerprints: set[str] = set()
    fixes_applied: list[SuggestedFix] = []
    files_written: list[str] = []
    written_paths: set[Path] = set()
    apply_rounds = 0
    last_error_items: list[ValidationErrorItem] = []

    for _ in range(max_iterations):
        snapshots_by_source = _snapshot_loaded_sources(entry_source_path=entry_source_path, effective_dirs=effective_dirs)
        try:
            validation_result = await validate_bundle(
                mthds_file_path=mthds_file_path,
                library_dirs=library_dirs,
                allow_signatures=allow_signatures,
            )
            pending_signatures = _pending_signatures_from_validation_result(validation_result)
            return FixBundleResult(
                is_valid=True,
                iterations=apply_rounds,
                fixes_applied=fixes_applied,
                files_written=files_written,
                remaining_errors=[],
                pending_signatures=pending_signatures,
                is_runnable=not pending_signatures,
            )
        except ValidateBundleError as exc:
            last_error_items = _validation_error_items(exc)

        safe_fixes = _safe_fixes(last_error_items, is_single_file=is_single_file, select_codes=select_codes, ignore_codes=ignore_codes)
        if not safe_fixes:
            return FixBundleResult(
                is_valid=False,
                iterations=apply_rounds,
                fixes_applied=fixes_applied,
                files_written=files_written,
                remaining_errors=last_error_items,
            )

        bound_fixes = _bind_fixes_to_snapshots(
            safe_fixes,
            entry_source_path=entry_source_path,
            snapshots_by_source=snapshots_by_source,
        )
        in_scope_fixes, out_of_scope_paths = _partition_by_write_scope(bound_fixes, entry_path=entry_path, writable_dirs=writable_dirs)
        if not in_scope_fixes:
            out_of_scope_names = ", ".join(sorted({str(out_path) for out_path in out_of_scope_paths}))
            bail_reason = (
                f"fixes target files outside write scope: {out_of_scope_names} — pass their directory with -L/--library-dir to allow writing"
            )
            return FixBundleResult(
                is_valid=False,
                iterations=apply_rounds,
                fixes_applied=fixes_applied,
                files_written=files_written,
                remaining_errors=last_error_items,
                bail_reason=bail_reason,
            )

        if not is_single_file:
            codes_by_file = _pipe_codes_by_file(entry_path=entry_path, effective_dirs=effective_dirs)
            in_scope_fixes, colliding_names = _split_cross_file_collisions(in_scope_fixes, codes_by_file=codes_by_file)
            if not in_scope_fixes:
                colliding = ", ".join(f"'{name}'" for name in sorted(set(colliding_names)))
                bail_reason = f"cross-file collision: every remaining fix would write a pipe code ({colliding}) already declared in a sibling bundle"
                return FixBundleResult(
                    is_valid=False,
                    iterations=apply_rounds,
                    fixes_applied=fixes_applied,
                    files_written=files_written,
                    remaining_errors=last_error_items,
                    bail_reason=bail_reason,
                )

        new_fixes = [fix for fix in in_scope_fixes if _fix_fingerprint(fix.fix) not in seen_fingerprints]
        if not new_fixes:
            # Author-facing: name the fixes that kept being re-proposed (their descriptions), not the
            # internal fingerprints — a re-proposal that changed nothing means the fix's target could
            # not be applied as written. The remaining errors (with their 💡 lines) print right below.
            repeated_descriptions = ", ".join(sorted({fix.fix.description for fix in in_scope_fixes}))
            bail_reason = (
                f"no progress: the same fix was re-proposed without changing the bundle ({repeated_descriptions}); "
                "its target could not be applied as written — fix the remaining errors manually"
            )
            return FixBundleResult(
                is_valid=False,
                iterations=apply_rounds,
                fixes_applied=fixes_applied,
                files_written=files_written,
                remaining_errors=last_error_items,
                bail_reason=bail_reason,
            )

        fixes_by_target: dict[Path, tuple[_FileSnapshot, list[SuggestedFix]]] = {}
        for bound_fix in new_fixes:
            target_group = fixes_by_target.setdefault(bound_fix.target_path, (bound_fix.snapshot, []))
            target_group[1].append(bound_fix.fix)

        pending_updates: list[_PendingFileUpdate] = []
        round_fixes_applied: list[SuggestedFix] = []
        round_written_paths: list[Path] = []
        for target_path, (snapshot, target_fixes) in fixes_by_target.items():
            toml_doc = tomlkit.loads(snapshot.content.decode("utf-8"))
            any_op_applied = False
            for target_fix in target_fixes:
                applications = apply_fix_ops(toml_doc=toml_doc, ops=target_fix.ops)
                if any(application.outcome.did_apply for application in applications):
                    round_fixes_applied.append(target_fix)
                    any_op_applied = True
            if any_op_applied:
                pending_updates.append(_PendingFileUpdate(snapshot=snapshot, new_content=serialize_and_format(toml_doc)))
                round_written_paths.append(target_path)

        _commit_file_updates(pending_updates)
        seen_fingerprints.update(_fix_fingerprint(fix.fix) for fix in new_fixes)
        fixes_applied.extend(round_fixes_applied)
        for target_path in round_written_paths:
            if target_path not in written_paths:
                written_paths.add(target_path)
                files_written.append(str(target_path))
        apply_rounds += 1

    # max_iterations apply rounds done — the final verdict comes from one last validation.
    try:
        validation_result = await validate_bundle(
            mthds_file_path=mthds_file_path,
            library_dirs=library_dirs,
            allow_signatures=allow_signatures,
        )
        pending_signatures = _pending_signatures_from_validation_result(validation_result)
        return FixBundleResult(
            is_valid=True,
            iterations=apply_rounds,
            fixes_applied=fixes_applied,
            files_written=files_written,
            remaining_errors=[],
            pending_signatures=pending_signatures,
            is_runnable=not pending_signatures,
        )
    except ValidateBundleError as exc:
        return FixBundleResult(
            is_valid=False,
            iterations=apply_rounds,
            fixes_applied=fixes_applied,
            files_written=files_written,
            remaining_errors=_validation_error_items(exc),
            bail_reason=f"max_iterations ({max_iterations}) reached without convergence",
        )
