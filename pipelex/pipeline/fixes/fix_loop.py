"""Minimal fix convergence loop — validate → collect SAFE fixes → apply → re-validate.

Reuses ``validate_bundle`` wholesale (THE validator — no parallel validation pipeline).
Cascades are expected: fixing one pipe can surface the next mismatch, so the loop runs to a
fixed point bounded by ``max_iterations``. Non-convergence is a first-class, loudly-reported
outcome: a fix fingerprint proposed twice (e.g. its ops target a synthetic pipe the applier
skips) ends the loop with a ``bail_reason`` instead of spinning.
"""

from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from pipelex.base_exceptions import ValidationErrorItem
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.fixes.applier import apply_fix_ops, serialize_and_format
from pipelex.pipeline.validate_bundle import validate_bundle
from pipelex.pipeline.validation_errors import build_validation_error_items
from pipelex.suggested_fix import SuggestedFix
from pipelex.tools.misc.toml_utils import load_toml_with_tomlkit


class FixBundleResult(BaseModel):
    """Outcome of one fix run: the final verdict, the work done, and what remains."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    is_valid: bool
    iterations: int
    """Number of apply rounds performed (0 when the bundle was already valid)."""
    fixes_applied: list[SuggestedFix]
    """Fixes with at least one op actually applied, in application order."""
    remaining_errors: list[ValidationErrorItem]
    """The last failed validation's structured errors; empty when ``is_valid``."""
    bail_reason: str | None = None
    """Why the loop stopped early (no-progress fingerprint repeat, max_iterations), if it did."""


def _fix_fingerprint(fix: SuggestedFix) -> str:
    """Stable identity of a fix attempt: fix_code + source + each op's (kind, path, key, value)."""
    op_parts = [f"{op.kind}:{'.'.join(op.table_path)}:{op.key}:{op.value!r}" for op in fix.ops]
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


def _applicable_safe_fixes(items: list[ValidationErrorItem], *, mthds_file_path: Path, is_single_file: bool) -> list[SuggestedFix]:
    """SAFE fixes provably targeting the file being fixed.

    A source-less fix is only trustworthy under single-file validation: with library dirs
    merged in, a same-named pipe from another domain could resolve to this file's table
    (pipe codes are only unique per domain), so source-less fixes are dropped rather than
    risk patching an unrelated pipe. Multi-file targeting is Phase 1 work.
    """
    fixes: list[SuggestedFix] = []
    for item in items:
        suggested_fix = item.suggested_fix
        if suggested_fix is None or not suggested_fix.safety.is_safe:
            continue
        if suggested_fix.source is None:
            if not is_single_file:
                continue
        elif Path(suggested_fix.source) != mthds_file_path:
            continue
        fixes.append(suggested_fix)
    return fixes


async def fix_bundle_file(
    mthds_file_path: Path,
    *,
    library_dirs: Sequence[Path] | None = None,
    max_iterations: int = 5,
) -> FixBundleResult:
    """Fix one bundle file in place until valid, out of fixes, no progress, or max_iterations.

    Each iteration: validate; on failure collect the SAFE suggested fixes riding the
    structured errors; apply the unseen ones to the file's tomlkit DOM (style-preserving);
    write when anything applied; re-validate. Only fixes with at least one applied op count
    in ``fixes_applied``.
    """
    seen_fingerprints: set[str] = set()
    fixes_applied: list[SuggestedFix] = []
    apply_rounds = 0
    last_error_items: list[ValidationErrorItem] = []

    for _ in range(max_iterations):
        try:
            await validate_bundle(mthds_file_path=mthds_file_path, library_dirs=library_dirs)
            return FixBundleResult(is_valid=True, iterations=apply_rounds, fixes_applied=fixes_applied, remaining_errors=[])
        except ValidateBundleError as exc:
            last_error_items = _validation_error_items(exc)

        safe_fixes = _applicable_safe_fixes(last_error_items, mthds_file_path=mthds_file_path, is_single_file=library_dirs is None)
        if not safe_fixes:
            return FixBundleResult(is_valid=False, iterations=apply_rounds, fixes_applied=fixes_applied, remaining_errors=last_error_items)

        new_fixes = [fix for fix in safe_fixes if _fix_fingerprint(fix) not in seen_fingerprints]
        if not new_fixes:
            bail_reason = (
                "no progress: every proposed fix fingerprint was already applied or skipped in a previous iteration "
                f"({', '.join(sorted(_fix_fingerprint(fix) for fix in safe_fixes))})"
            )
            return FixBundleResult(
                is_valid=False,
                iterations=apply_rounds,
                fixes_applied=fixes_applied,
                remaining_errors=last_error_items,
                bail_reason=bail_reason,
            )

        toml_doc = load_toml_with_tomlkit(mthds_file_path)
        any_op_applied = False
        for fix in new_fixes:
            seen_fingerprints.add(_fix_fingerprint(fix))
            applications = apply_fix_ops(toml_doc, ops=fix.ops)
            if any(application.outcome.did_apply for application in applications):
                fixes_applied.append(fix)
                any_op_applied = True
        apply_rounds += 1
        if any_op_applied:
            mthds_file_path.write_text(serialize_and_format(toml_doc), encoding="utf-8")

    # max_iterations apply rounds done — the final verdict comes from one last validation.
    try:
        await validate_bundle(mthds_file_path=mthds_file_path, library_dirs=library_dirs)
        return FixBundleResult(is_valid=True, iterations=apply_rounds, fixes_applied=fixes_applied, remaining_errors=[])
    except ValidateBundleError as exc:
        return FixBundleResult(
            is_valid=False,
            iterations=apply_rounds,
            fixes_applied=fixes_applied,
            remaining_errors=_validation_error_items(exc),
            bail_reason=f"max_iterations ({max_iterations}) reached without convergence",
        )
