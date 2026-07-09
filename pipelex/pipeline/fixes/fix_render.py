"""Markdown rendering for deterministic bundle-fix results."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from pipelex.pipeline.validation_render import format_validation_error_items_markdown

if TYPE_CHECKING:
    from pipelex.pipeline.fixes.fix_loop import FixBundleResult


def _format_fix_file(fix_payload: dict[str, Any], *, bundle_path: str | None) -> str | None:
    source = fix_payload.get("source")
    if not isinstance(source, str):
        return None
    if bundle_path is not None and Path(source).resolve() == Path(bundle_path).resolve():
        return None
    return source


def format_fix_markdown(result: dict[str, Any]) -> str:
    """Render a successful ``pipelex-agent fix bundle`` result as markdown."""
    fixes = result.get("fixes_applied")
    fix_items = cast("list[Any]", fixes) if isinstance(fixes, list) else []
    is_runnable = result.get("is_runnable")
    if is_runnable is False:
        title = "# Bundle valid but not runnable"
    elif fix_items:
        title = "# Fix applied - bundle is valid"
    else:
        title = "# Bundle already valid"
    lines: list[str] = [title, ""]

    bundle_path = result.get("bundle_path")
    bundle_path_str = bundle_path if isinstance(bundle_path, str) else None
    if bundle_path_str is not None:
        lines.append(f"- **Bundle:** `{bundle_path_str}`")

    iterations = result.get("iterations")
    if isinstance(iterations, int):
        lines.append(f"- **Iterations:** {iterations}")

    pending_signatures = result.get("pending_signatures")
    if isinstance(pending_signatures, list) and pending_signatures:
        lines += [
            "",
            "## Pending Signatures",
            "",
            "This bundle is valid but not runnable until these `PipeSignature` placeholders are implemented:",
            "",
        ]
        for pipe_ref in cast("list[Any]", pending_signatures):
            lines.append(f"- `{pipe_ref}`")

    if fix_items:
        lines += ["", "## Applied Fixes", ""]
        for fix_item in fix_items:
            if not isinstance(fix_item, dict):
                continue
            typed_fix_item = cast("dict[str, Any]", fix_item)
            fix_code = str(typed_fix_item.get("fix_code", "unknown"))
            description = str(typed_fix_item.get("description", ""))
            source = _format_fix_file(typed_fix_item, bundle_path=bundle_path_str)
            suffix = f" (`{source}`)" if source is not None else ""
            lines.append(f"- `{fix_code}` - {description}{suffix}")

    files_written = result.get("files_written")
    if isinstance(files_written, list) and files_written:
        lines += ["", "## Files Written", ""]
        for file_path in cast("list[Any]", files_written):
            lines.append(f"- `{file_path}`")

    return "\n".join(lines)


def format_fix_still_invalid_markdown(result: FixBundleResult, *, bundle_path: str) -> str:
    """Render a still-invalid ``fix bundle`` result as agent-readable markdown (stderr, exit 1).

    The markdown sibling of the human ``_render_fix_result`` still-invalid arm
    (``cli/commands/fix/_fix_core.py``): a heading, the bundle, the partial progress that WAS
    applied, the bail reason, then the remaining errors rendered as prose items (with their ``💡
    Suggested fix`` lines, via the shared :func:`format_validation_error_items_markdown`) rather
    than a raw JSON dump, and a context-aware tip. This is the step-5-deferred "richer
    still-invalid markdown for the agent command".
    """
    lines: list[str] = ["# Fix incomplete - bundle still invalid", "", f"**Bundle:** `{bundle_path}`"]

    # Partial progress is normal: name what WAS applied before the remaining errors.
    if result.fixes_applied:
        entry_resolved = Path(bundle_path).resolve()
        lines += ["", "## Applied Fixes", ""]
        for fix in result.fixes_applied:
            suffix = f" (`{fix.source}`)" if fix.source is not None and Path(fix.source).resolve() != entry_resolved else ""
            lines.append(f"- `{fix.fix_code}` - {fix.description}{suffix}")
        if result.files_written:
            lines += ["", "## Files Written", ""]
            for file_path in result.files_written:
                lines.append(f"- `{file_path}`")
        lines += ["", f"- **Iterations:** {result.iterations}"]

    if result.bail_reason:
        lines += ["", f"**Stopped:** {result.bail_reason}"]

    if result.remaining_errors:
        lines += ["", format_validation_error_items_markdown(result.remaining_errors)]

    # A remaining error can still carry a 💡 suggested-fix line — dropped by --select/--ignore, left
    # outside the write scope, or unconverged when the loop bailed. Claiming "no safe fix" there would
    # contradict the line just printed, so only say it when nothing fixable remains (mirrors the human tip).
    if any(item.suggested_fix is not None for item in result.remaining_errors):
        lines += [
            "",
            (
                "💡 Some remaining errors above still show a suggested fix that was not applied — they were skipped by "
                "--select/--ignore, fell outside the write scope, or the loop stopped early (see the reason above). "
                "Adjust those flags (or pass -L) and re-run, or fix the rest manually."
            ),
        ]
    else:
        lines += ["", "💡 The remaining errors have no deterministic safe fix — they need a manual edit."]

    return "\n".join(lines)
