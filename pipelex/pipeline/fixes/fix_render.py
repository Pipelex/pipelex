"""Markdown rendering for deterministic bundle-fix results."""

from pathlib import Path
from typing import Any, cast


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
