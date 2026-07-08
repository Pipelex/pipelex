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

from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field

from pipelex.base_exceptions import ValidationErrorItem
from pipelex.config import get_config
from pipelex.hub import resolve_library_dirs
from pipelex.libraries.library_utils import get_pipelex_mthds_files_from_dirs
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.fixes.applier import apply_fix_ops, serialize_and_format
from pipelex.pipeline.validate_bundle import validate_bundle
from pipelex.pipeline.validation_errors import build_validation_error_items
from pipelex.suggested_fix import FixOp, FixOpKind, SuggestedFix
from pipelex.tools.misc.exceptions import TomlError
from pipelex.tools.misc.toml_utils import load_toml_from_path, load_toml_with_tomlkit

_MAIN_PIPE_KEY = "main_pipe"


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


def _fix_target_path(fix: SuggestedFix, *, entry_path: Path) -> Path:
    """The file this fix's ops address: its ``source`` when known, else the entry file."""
    if fix.source is None:
        return entry_path
    return Path(fix.source).resolve()


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
        if suggested_fix is None or not suggested_fix.safety.is_safe:
            continue
        if suggested_fix.source is None and not is_single_file:
            continue
        if select_codes is not None and suggested_fix.fix_code not in select_codes:
            continue
        if ignore_codes is not None and suggested_fix.fix_code in ignore_codes:
            continue
        fixes.append(suggested_fix)
    return fixes


def _partition_by_write_scope(
    fixes: list[SuggestedFix],
    *,
    entry_path: Path,
    writable_dirs: Sequence[Path],
) -> tuple[list[SuggestedFix], list[Path]]:
    """Split fixes into (writable, out-of-scope target paths).

    Writable = the entry file, plus anything under a per-call ``library_dirs`` directory.
    Files loaded via ambient resolution (hub defaults, ``PIPELEXPATH``) are read-only: the
    user did not pass them to THIS command, so their fixes are excluded rather than applied.
    """
    in_scope: list[SuggestedFix] = []
    out_of_scope_paths: list[Path] = []
    for fix in fixes:
        target_path = _fix_target_path(fix, entry_path=entry_path)
        if target_path == entry_path or any(target_path.is_relative_to(writable_dir) for writable_dir in writable_dirs):
            in_scope.append(fix)
        else:
            out_of_scope_paths.append(target_path)
    return in_scope, out_of_scope_paths


def _pipe_codes_by_file(*, entry_path: Path, effective_dirs: Sequence[Path]) -> dict[Path, set[str]]:
    """Pipe declaration keys of every loaded bundle file, across ALL domains, keyed by resolved path.

    Cross-domain on purpose: a bare pipe code must resolve unambiguously across the loaded
    library — ``PipeLibrary.get_optional_pipe`` raises on a bare code declared by two domains —
    so a rename target colliding with a same-named declaration in ANY other loaded file would
    leave the library unloadable. Rebuilt each iteration: multiple files can now mutate per
    round. A file that fails to parse contributes nothing here — its own problems surface
    through validation, not this scan.
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
            codes_by_file[mthds_path] = {key for key in cast("dict[Any, Any]", pipe_section) if isinstance(key, str)}
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
        case FixOpKind.DELETE_KEY | FixOpKind.DELETE_TABLE:
            return None


def _split_cross_file_collisions(
    fixes: list[SuggestedFix],
    *,
    entry_path: Path,
    codes_by_file: dict[Path, set[str]],
) -> tuple[list[SuggestedFix], list[str]]:
    """Split ``fixes`` into (kept, colliding pipe codes of the dropped ones).

    The raise-site collision gate only sees the one file being validated; in a multi-file run a
    bare pipe of the same name may live in another loaded file, where writing it (as a ``[pipe]``
    key rename or a ``main_pipe`` value) would create a state the loop can never repair. Each
    fix is checked against the pipe codes of every loaded file OTHER than its own target.
    Dropped fixes simply leave their error unfixed (still reported in ``remaining_errors``).
    """
    kept: list[SuggestedFix] = []
    colliding_names: list[str] = []
    other_codes_cache: dict[Path, set[str]] = {}
    for fix in fixes:
        target_path = _fix_target_path(fix, entry_path=entry_path)
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
            for fix_op in fix.ops
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
    max_iterations: int | None = None,
    select_codes: Sequence[str] | None = None,
    ignore_codes: Sequence[str] | None = None,
) -> FixBundleResult:
    """Fix a bundle in place until valid, out of fixes, no progress, or max_iterations.

    Each iteration: validate; on failure collect the SAFE suggested fixes riding the
    structured errors; group the unseen ones by the file they target (declaring file via
    ``source``, entry file for source-less); apply each group to its file's tomlkit DOM
    (style-preserving) and write the changed files; re-validate. Only fixes with at least one
    applied op count in ``fixes_applied``. ``max_iterations=None`` resolves to the
    ``fix_loop_max_attempts`` builder config. ``select_codes`` / ``ignore_codes`` filter which
    fix rules may apply (see ``_safe_fixes``); the CLI validates the codes before calling.
    """
    if max_iterations is None:
        max_iterations = get_config().pipelex.builder_config.fix_loop_max_attempts
    entry_path = mthds_file_path.resolve()
    effective_dirs, _ = resolve_library_dirs(library_dirs)
    is_single_file = not effective_dirs
    writable_dirs: list[Path] = [Path(writable_dir).resolve() for writable_dir in library_dirs] if library_dirs is not None else []

    seen_fingerprints: set[str] = set()
    fixes_applied: list[SuggestedFix] = []
    files_written: list[str] = []
    written_paths: set[Path] = set()
    apply_rounds = 0
    last_error_items: list[ValidationErrorItem] = []

    for _ in range(max_iterations):
        try:
            await validate_bundle(mthds_file_path=mthds_file_path, library_dirs=library_dirs)
            return FixBundleResult(
                is_valid=True,
                iterations=apply_rounds,
                fixes_applied=fixes_applied,
                files_written=files_written,
                remaining_errors=[],
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

        in_scope_fixes, out_of_scope_paths = _partition_by_write_scope(safe_fixes, entry_path=entry_path, writable_dirs=writable_dirs)
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
            in_scope_fixes, colliding_names = _split_cross_file_collisions(in_scope_fixes, entry_path=entry_path, codes_by_file=codes_by_file)
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

        new_fixes = [fix for fix in in_scope_fixes if _fix_fingerprint(fix) not in seen_fingerprints]
        if not new_fixes:
            bail_reason = (
                "no progress: every proposed fix fingerprint was already applied or skipped in a previous iteration "
                f"({', '.join(sorted(_fix_fingerprint(fix) for fix in in_scope_fixes))})"
            )
            return FixBundleResult(
                is_valid=False,
                iterations=apply_rounds,
                fixes_applied=fixes_applied,
                files_written=files_written,
                remaining_errors=last_error_items,
                bail_reason=bail_reason,
            )

        fixes_by_target: dict[Path, list[SuggestedFix]] = {}
        for fix in new_fixes:
            fixes_by_target.setdefault(_fix_target_path(fix, entry_path=entry_path), []).append(fix)

        for target_path, target_fixes in fixes_by_target.items():
            toml_doc = load_toml_with_tomlkit(target_path)
            any_op_applied = False
            for fix in target_fixes:
                seen_fingerprints.add(_fix_fingerprint(fix))
                applications = apply_fix_ops(toml_doc, ops=fix.ops)
                if any(application.outcome.did_apply for application in applications):
                    fixes_applied.append(fix)
                    any_op_applied = True
            if any_op_applied:
                target_path.write_text(serialize_and_format(toml_doc), encoding="utf-8")
                if target_path not in written_paths:
                    written_paths.add(target_path)
                    files_written.append(str(target_path))
        apply_rounds += 1

    # max_iterations apply rounds done — the final verdict comes from one last validation.
    try:
        await validate_bundle(mthds_file_path=mthds_file_path, library_dirs=library_dirs)
        return FixBundleResult(
            is_valid=True,
            iterations=apply_rounds,
            fixes_applied=fixes_applied,
            files_written=files_written,
            remaining_errors=[],
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
