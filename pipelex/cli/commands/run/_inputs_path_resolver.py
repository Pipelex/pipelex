"""Resolve relative file paths inside pipeline inputs relative to a base directory.

When inputs are loaded from a JSON file (e.g. ``inputs.json`` inside a bundle
directory), any relative ``url`` values should be resolved relative to that
file's parent directory — not relative to the process CWD.  This module
provides the logic to walk an inputs dict and prepend a base directory to
relative local paths.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from pipelex.tools.uri.resolved_uri import ResolvedLocalPath
from pipelex.tools.uri.uri_resolver import resolve_uri


def is_relative_local_path(uri: str) -> bool:
    """Check whether *uri* is a relative local file path.

    Uses :func:`resolve_uri` to classify the URI.  Returns ``True`` only when
    the URI resolves to a :class:`ResolvedLocalPath` **and** the path is not
    absolute.

    Args:
        uri: The URI string to check.

    Returns:
        ``True`` if *uri* is a relative local path, ``False`` otherwise.
    """
    resolved = resolve_uri(uri)
    if not isinstance(resolved, ResolvedLocalPath):
        return False
    if "://" in resolved.path:
        # An unrecognized scheme (``s3://``, ``gs://``, …) slips through ``resolve_uri`` as a
        # ResolvedLocalPath but is NOT a local file path; do not rewrite it relative to base_dir
        # (that would mangle ``s3://bucket/x`` into ``<base_dir>/s3:/bucket/x`` and defeat the
        # downstream remote-url guards). Mirrors the same ``"://"`` stopgap in the CSV input hook;
        # both go away once ``resolve_uri`` classifies schemes (tools/uri follow-up).
        return False
    return not Path(resolved.path).is_absolute()


def resolve_url_in_value(value: Any, *, base_dir: Path) -> Any:
    """Recursively walk a JSON-like value and resolve relative ``url`` fields.

    When a ``dict`` contains a ``"url"`` key whose value is a relative local
    path, the path is prepended with *base_dir* so that it becomes absolute.

    Args:
        value: An arbitrary JSON-decoded value (dict, list, str, etc.).
        base_dir: The directory against which relative paths are resolved.

    Returns:
        The value with relative ``url`` entries resolved.
    """
    if isinstance(value, dict):
        value_dict = cast("dict[str, Any]", value)
        result: dict[str, Any] = {}
        for key, val in value_dict.items():
            if key == "url" and isinstance(val, str) and is_relative_local_path(val):
                result[key] = str(base_dir / val)
            else:
                result[key] = resolve_url_in_value(val, base_dir=base_dir)
        return result

    if isinstance(value, list):
        value_list = cast("list[Any]", value)
        return [resolve_url_in_value(item, base_dir=base_dir) for item in value_list]

    return value


def resolve_inputs_paths(inputs_dict: dict[str, Any], *, base_dir: Path) -> dict[str, Any]:
    """Resolve relative ``url`` paths in a pipeline inputs dict.

    Entry point that applies :func:`resolve_url_in_value` to each top-level
    value in *inputs_dict*.

    Args:
        inputs_dict: The parsed pipeline inputs dictionary.
        base_dir: The directory to resolve relative paths against (typically
            the parent directory of the ``inputs.json`` file).

    Returns:
        A new dict with all relative ``url`` values resolved to absolute paths.
    """
    resolved: dict[str, Any] = {}
    for key, value in inputs_dict.items():
        resolved[key] = resolve_url_in_value(value, base_dir=base_dir)
    return resolved
