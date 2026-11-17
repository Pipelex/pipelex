"""Shared output formatting helpers for agent CLI run commands."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, cast

from kajson.exceptions import KajsonException
from kajson.kajson import json_decode_date, json_decode_datetime, json_decode_time

from pipelex.tools.misc.json_utils import clean_json_dumps

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

# The only kajson class markers the renderer revives, each through kajson's own parser for that type, which reads
# strings and numbers and never imports a module or calls a constructor the payload names. Every other marker stays
# plain data, and `clean_json_dumps` drops its marker keys.
_REVIVED_MARKERS: dict[tuple[str, str], Callable[[dict[str, Any]], Any]] = {
    ("datetime", "datetime"): json_decode_datetime,
    ("datetime", "date"): json_decode_date,
    ("datetime", "time"): json_decode_time,
}


def build_run_output(
    *,
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


def _revive_safe_marker(obj: dict[str, Any]) -> Any:
    """`json.loads` object hook: turn a kajson date, datetime or time marker back into its value, leave every other object as it is."""
    module_name = obj.get("__module__")
    class_name = obj.get("__class__")
    if not isinstance(module_name, str) or not isinstance(class_name, str):
        return obj
    decoder = _REVIVED_MARKERS.get((module_name, class_name))
    if decoder is None:
        return obj
    try:
        return decoder(obj)
    except (KajsonException, ValueError, TypeError, KeyError, AttributeError):
        return obj


def _render_json_payload_lines(result_payload: Any) -> list[str]:
    """Render a structured payload as a fenced ``## Result`` json block.

    The local runner stores ``json`` as a kajson-encoded string (kajson.dumps of smart_dump, carrying ``__class__``
    metadata for custom types), and a hosted run's ``json`` is whatever the server sent. The string is decoded with plain
    ``json.loads``, never ``kajson.loads``: kajson imports the module a ``__module__`` key names and calls the class a
    ``__class__`` key names, so a payload naming ``subprocess.Popen`` would start a process on this machine. Only the
    date, datetime and time markers are revived, through kajson's parsers for them, so they render as ISO strings; every
    other marker stays plain data whose marker keys ``clean_json_dumps`` drops. A string that does not decode is
    rendered as-is.
    """
    if isinstance(result_payload, str):
        try:
            result_payload = json.loads(result_payload, object_hook=_revive_safe_marker)
        except (json.JSONDecodeError, RecursionError):
            pass
    return ["## Result", "", "```json", clean_json_dumps(result_payload, indent=2), "```"]


def format_run_markdown(result: dict[str, Any], *, with_memory: bool, warnings: Sequence[Mapping[str, Any]] = ()) -> str:
    """Render a pipeline-run result dict as agent-readable markdown.

    Handles both shapes ``build_run_output()`` produces, disambiguated by the
    authoritative ``with_memory`` flag rather than guessed from the dict's keys:
    the full envelope (``with_memory=True`` — ``main_stuff`` carries a rendered
    ``markdown`` representation) and the compact concept JSON (``with_memory=False``).

    Args:
        result: The JSON-mode result dict for the run.
        with_memory: True when ``result`` is the full envelope (``main_stuff`` +
            ``working_memory`` + side-effect metadata); False when ``result`` is
            the bare compact concept JSON.
        warnings: What the run reports beside its output without failing, each a `{type, message, …}` object, rendered
            as a `## Warnings` section after the result in both shapes, since the compact one has no room for them.

    Returns:
        A markdown string for stdout.
    """
    lines: list[str] = ["# Pipeline run complete", ""]

    if not with_memory:
        # Compact mode: `result` IS the bare concept JSON, not an envelope — render it whole.
        # Probing for envelope keys here would misread a concept field that happens to be
        # named like one (e.g. a dict-valued `main_stuff`) and silently drop the real result.
        if result:
            lines += _render_json_payload_lines(result)
        else:
            lines.append("_The pipeline produced no main output._")
        lines += _render_warning_lines(warnings=warnings)
        return "\n".join(lines)

    main_stuff = result.get("main_stuff")
    main_stuff_dict = cast("dict[str, Any]", main_stuff) if isinstance(main_stuff, dict) else None
    rendered_markdown: str | None = None
    if main_stuff_dict is not None:
        candidate = main_stuff_dict.get("markdown")
        if isinstance(candidate, str) and candidate:
            rendered_markdown = candidate

    if rendered_markdown is not None:
        lines += ["## Result", "", rendered_markdown]
    else:
        # No rendered markdown — e.g. the API runner cannot render it and leaves `markdown`
        # empty. Surface the structured `json` payload `main_stuff` still carries rather than
        # dropping it (it sits under an excluded envelope key).
        result_payload = main_stuff_dict.get("json") if main_stuff_dict is not None else None
        if result_payload is not None:
            lines += _render_json_payload_lines(result_payload)
        else:
            lines.append("_The pipeline produced no main output._")

    # output_file / graph_files are envelope-only side-effect metadata — build_run_output
    # merges them solely under with_memory — so they are read only on this branch.
    output_file = result.get("output_file")
    if isinstance(output_file, str):
        lines += ["", f"**Output file:** `{output_file}`"]

    graph_files = result.get("graph_files")
    if isinstance(graph_files, dict):
        graph_html = cast("dict[str, Any]", graph_files).get("graph_html")
        if isinstance(graph_html, str):
            lines += ["", f"**Graph:** `{graph_html}`"]

    lines += _render_warning_lines(warnings=warnings)
    return "\n".join(lines)


def _render_warning_lines(*, warnings: Sequence[Mapping[str, Any]]) -> list[str]:
    """The `## Warnings` section of a run's Markdown, one `- **<type>** — <message>` line per warning, as `validate` renders its own."""
    if not warnings:
        return []
    lines: list[str] = ["", f"## Warnings ({len(warnings)})", ""]
    for warning in warnings:
        lines.append(f"- **{warning.get('type')}** — {warning.get('message')}")
    return lines
