"""Shared output formatting helpers for agent CLI run commands."""

from __future__ import annotations

from typing import Any, cast

from pipelex.tools.misc.json_utils import clean_json_dumps

# Envelope keys that carry metadata rather than the pipeline's main result;
# excluded from the markdown "Result" JSON block so it stays focused.
_RUN_ENVELOPE_KEYS: frozenset[str] = frozenset({"working_memory", "main_stuff", "output_file", "graph_files"})


def build_run_output(
    with_memory: bool,
    main_stuff_json: dict[str, Any],
    working_memory_dump: dict[str, Any],
    compact_result: dict[str, Any] | None,
    extra_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the final output dict for a pipeline run, respecting the output mode.

    Args:
        with_memory: If True, return the full envelope with ``main_stuff`` and
            ``working_memory``. If False, return compact output (concept JSON only).
        main_stuff_json: The main stuff rendered in ``{ json, markdown, html }`` format.
        working_memory_dump: The serialized working memory (``smart_dump()`` or
            ``model_dump()``).
        compact_result: The concept's structured JSON as a dict for compact output,
            or None if there is no main stuff.
        extra_metadata: Additional metadata to merge into the envelope when
            ``with_memory=True`` (e.g. ``pipeline_run_id``, ``pipeline_state``).
            Ignored in compact mode.

    Returns:
        The output dict ready for ``agent_success()``.
    """
    if with_memory:
        envelope: dict[str, Any] = {
            "main_stuff": main_stuff_json,
            "working_memory": working_memory_dump,
        }
        if extra_metadata:
            envelope.update(extra_metadata)
        return envelope
    if compact_result is not None:
        return compact_result
    return {}


def format_run_markdown(result: dict[str, Any]) -> str:
    """Render a pipeline-run result dict as agent-readable markdown.

    Handles both shapes ``build_run_output()`` produces: the full envelope
    (``with_memory=True`` — ``main_stuff`` carries a rendered ``markdown``
    representation) and the compact concept JSON (``with_memory=False``).

    Args:
        result: The JSON-mode result dict for the run.

    Returns:
        A markdown string for stdout.
    """
    lines: list[str] = ["# Pipeline run complete", ""]

    main_stuff = result.get("main_stuff")
    rendered_markdown: str | None = None
    if isinstance(main_stuff, dict):
        candidate = cast("dict[str, Any]", main_stuff).get("markdown")
        if isinstance(candidate, str) and candidate:
            rendered_markdown = candidate

    if rendered_markdown is not None:
        lines += ["## Result", "", rendered_markdown]
    else:
        # No rendered markdown — e.g. the API runner cannot render it and leaves `markdown`
        # empty. Surface the structured `json` payload `main_stuff` still carries rather than
        # dropping it (it sits under an excluded envelope key). Only with no `main_stuff` at
        # all do we fall back to the remaining non-envelope keys.
        result_payload: Any | None = None
        if isinstance(main_stuff, dict):
            result_payload = cast("dict[str, Any]", main_stuff).get("json")
        if result_payload is None and not isinstance(main_stuff, dict):
            body = {key: value for key, value in result.items() if key not in _RUN_ENVELOPE_KEYS}
            result_payload = body or None
        if result_payload is not None:
            lines += ["## Result", "", "```json", clean_json_dumps(result_payload, indent=2), "```"]
        else:
            lines.append("_The pipeline produced no main output._")

    output_file = result.get("output_file")
    if isinstance(output_file, str):
        lines += ["", f"**Output file:** `{output_file}`"]

    graph_files = result.get("graph_files")
    if isinstance(graph_files, dict):
        graph_html = cast("dict[str, Any]", graph_files).get("graph_html")
        if isinstance(graph_html, str):
            lines += ["", f"**Graph:** `{graph_html}`"]

    return "\n".join(lines)
