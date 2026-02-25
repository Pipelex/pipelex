"""Shared output formatting helpers for agent CLI run commands."""

from __future__ import annotations

from typing import Any


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
