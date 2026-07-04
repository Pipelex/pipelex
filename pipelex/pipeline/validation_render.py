"""Public, non-CLI Markdown rendering for validation results.

This is the public home of ``format_validate_markdown`` — lifted out of the
agent CLI (``cli/agent_cli/commands/validate/_output_helpers.py``) so it can be
imported by other surfaces (notably ``pipelex-api``'s ``/validate`` route, which
attaches an opt-in ``rendered_markdown`` extra) WITHOUT pulling in Typer / the
CLI internals. The agent CLI keeps using it for its ``--format markdown`` valid
path, so the local-CLI and API-runner Markdown share one source of truth and
cannot drift.

``format_validate_markdown`` renders the **valid-arm** result;
``render_invalid_validation_markdown`` renders the **invalid-arm** verdict (the
structured ``validation_errors``). Both are shared pipelex code so the local CLI
and the API-runner cannot drift in format/structure.
"""

from __future__ import annotations

from typing import Any, cast

from pipelex.tools.misc.string_utils import count_with_noun


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
    lines.append(f"Validated {count_with_noun(total_pipes, singular='pipe')}:")
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
            pending_count = len(pending_signatures)
            if pending_count == 1:
                verdict = "⚠️ This method is NOT yet runnable — 1 pipe is still a `PipeSignature` placeholder and must be implemented before running:"
            else:
                verdict = (
                    f"⚠️ This method is NOT yet runnable — {pending_count} pipes are still "
                    "`PipeSignature` placeholders and must be implemented before running:"
                )
            # Verdict line is emitted immediately above the verbatim "Pending signatures" heading —
            # downstream consumers rely on that exact ordering (see agent_cli/CLAUDE.md).
            lines += [
                "",
                verdict,
                "",
                f"## Pending signatures ({pending_count})",
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

    # Advisory lints (e.g. the useless-`!` lint) — informational: the bundle IS valid.
    warnings: list[dict[str, Any]] = result.get("warnings") or []
    if warnings:
        lines += ["", f"## Warnings ({len(warnings)})", ""]
        for warning in warnings:
            lines.append(f"- **{warning.get('error_type') or warning.get('category')}** — {warning.get('message')}")

    graph_files = result.get("graph_files")
    if isinstance(graph_files, dict):
        lines += ["", "## Graph files", ""]
        for graph_label, graph_path in cast("dict[str, Any]", graph_files).items():
            lines.append(f"- **{graph_label}:** `{graph_path}`")

    if "graphspec" in result:
        lines += ["", "_A GraphSpec (structured graph JSON) is included — use `--format json` to retrieve it._"]

    return "\n".join(lines)


def render_invalid_validation_markdown(report: dict[str, Any]) -> str:
    """Render an invalid validation verdict (the InvalidReport arm) as agent-readable markdown.

    Faithfully renders the structured ``validation_errors`` the hosted ``/validate``
    InvalidReport carries — the same typed items the agent CLI emits — as a
    ``# Validation failed`` heading, the summary ``message``, then a numbered
    ``## Errors`` list with each item's ``category`` + ``message`` and any present
    locators (pipe / concept / domain / field / source). This is a faithful render
    of the structured verdict; it does NOT reproduce the agent CLI's generic
    error-envelope byte-for-byte.

    Args:
        report: The InvalidReport-shaped dict (``is_valid: False``,
            ``validation_errors: [...]``, ``message``).

    Returns:
        A markdown string.
    """
    lines: list[str] = ["# Validation failed", ""]

    message = report.get("message")
    if message:
        lines += [str(message), ""]

    validation_errors: list[dict[str, Any]] = report.get("validation_errors") or []
    lines += [f"## Errors ({len(validation_errors)})", ""]

    # Locators rendered in a stable order, only when present (non-None) — mirrors the
    # structured-info invariant: each item carries the locators it can attribute.
    locator_labels: list[tuple[str, str]] = [
        ("pipe", "pipe_code"),
        ("missing pipe", "missing_pipe_code"),
        ("concept", "concept_code"),
        ("missing concept", "missing_concept_code"),
        ("domain", "domain_code"),
        ("field", "field_name"),
        ("path", "field_path"),
        ("source", "source"),
    ]
    for index, item in enumerate(validation_errors, start=1):
        lines.append(f"{index}. **{item.get('category')}** — {item.get('message')}")
        for label, key in locator_labels:
            value = item.get(key)
            if value:
                lines.append(f"   - {label}: `{value}`")

    return "\n".join(lines)
