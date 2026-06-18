"""Public, non-CLI Markdown rendering for validation results.

This is the public home of ``format_validate_markdown`` — lifted out of the
agent CLI (``cli/agent_cli/commands/validate/_output_helpers.py``) so it can be
imported by other surfaces (notably ``pipelex-api``'s ``/validate`` route, which
attaches an opt-in ``rendered_markdown`` extra) WITHOUT pulling in Typer / the
CLI internals. The agent CLI keeps using it for its ``--format markdown`` valid
path, so the local-CLI and API-runner Markdown share one source of truth and
cannot drift.

It renders the **valid-arm** validation result. The invalid-arm rendering for
the API is deferred to Phase 3 (see ``wip/validate-rendered-markdown-invalid-arm.md``).
"""

from __future__ import annotations

from typing import Any, cast


def format_validate_markdown(result: dict[str, Any]) -> str:
    """Render a validation result dict as agent-readable markdown.

    Covers the success-path shape produced by the ``validate`` core helpers:
    ``validated_pipes`` (a list of ``{pipe_ref, status}``), ``total_pipes``,
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
        lines.append(f"- `{entry.get('pipe_ref')}` — {entry.get('status')}")

    # Runnability verdict — gated on key *presence*, not truthiness. Only the bundle-validate
    # surfaces put `pending_signatures` in the result; `validate all` / `validate pipe` omit the key,
    # so they get no verdict (claiming runnability there would be misleading). Present-and-empty is a
    # complete bundle (runnable); present-and-non-empty still has forward declarations to implement.
    if "pending_signatures" in result:
        pending_signatures: list[str] = result["pending_signatures"] or []
        if pending_signatures:
            # Verdict line is emitted immediately above the verbatim "Pending signatures" heading —
            # downstream consumers rely on that exact ordering (see agent_cli/CLAUDE.md).
            lines += [
                "",
                (
                    f"⚠️ This method is NOT yet runnable — {len(pending_signatures)} pipe(s) are still "
                    "`PipeSignature` placeholders and must be implemented before running:"
                ),
                "",
                f"## Pending signatures ({len(pending_signatures)})",
                "",
            ]
            for pending_ref in pending_signatures:
                lines.append(f"- `{pending_ref}`")
        else:
            lines += [
                "",
                (
                    "✅ All pipes are concretely implemented — no `PipeSignature` placeholders remain. "
                    "Strict validation will pass; this method is runnable."
                ),
            ]

    graph_files = result.get("graph_files")
    if isinstance(graph_files, dict):
        lines += ["", "## Graph files", ""]
        for graph_label, graph_path in cast("dict[str, Any]", graph_files).items():
            lines.append(f"- **{graph_label}:** `{graph_path}`")

    if "graphspec" in result:
        lines += ["", "_A GraphSpec (structured graph JSON) is included — use `--format json` to retrieve it._"]

    return "\n".join(lines)
