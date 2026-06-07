"""Shared output formatting helpers for agent CLI validate commands."""

from __future__ import annotations

from typing import Any, cast


def format_validate_markdown(result: dict[str, Any]) -> str:
    """Render a validation result dict as agent-readable markdown.

    Covers the success-path shape produced by the ``validate`` core helpers:
    ``validated_pipes`` (a list of ``{pipe_code, status}``), ``total_pipes``,
    and an optional ``bundle_path``. ``validate bundle --graph`` / ``--view``
    also merge ``graph_files`` / ``graphspec`` into the result — those are
    surfaced too so markdown mode does not silently drop them.

    Args:
        result: The JSON-mode result dict for the validation.

    Returns:
        A markdown string for stdout.
    """
    lines: list[str] = ["# Validation passed", ""]

    bundle_path = result.get("bundle_path")
    if bundle_path:
        lines += [f"**Bundle:** `{bundle_path}`", ""]

    validated_pipes: list[dict[str, Any]] = result.get("validated_pipes") or []
    total_pipes = result.get("total_pipes", len(validated_pipes))
    lines.append(f"Validated {total_pipes} pipe(s):")
    lines.append("")
    for entry in validated_pipes:
        lines.append(f"- `{entry.get('pipe_code')}` — {entry.get('status')}")

    pending_signatures: list[str] = result.get("pending_signatures") or []
    if pending_signatures:
        lines += ["", f"## Pending signatures ({len(pending_signatures)})", ""]
        lines.append("These pipes are still forward declarations (`PipeSignature`) awaiting a concrete definition:")
        lines.append("")
        for pending_ref in pending_signatures:
            lines.append(f"- `{pending_ref}`")

    graph_files = result.get("graph_files")
    if isinstance(graph_files, dict):
        lines += ["", "## Graph files", ""]
        for graph_label, graph_path in cast("dict[str, Any]", graph_files).items():
            lines.append(f"- **{graph_label}:** `{graph_path}`")

    if "graphspec" in result:
        lines += ["", "_A GraphSpec (structured graph JSON) is included — use `--format json` to retrieve it._"]

    return "\n".join(lines)
