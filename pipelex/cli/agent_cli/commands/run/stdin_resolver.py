"""Stdin input resolution and shared CLI input parsing for agent CLI run commands."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, cast

from pipelex.cli.agent_cli.commands.agent_output import agent_error
from pipelex.cli.commands.run._inputs_file_loader import find_default_inputs_file, load_inputs_dict_from_path
from pipelex.cli.commands.run._inputs_path_resolver import resolve_inputs_paths
from pipelex.cli.commands.run.exceptions import AmbiguousInputsFilesError, InputsDatetimeNotSupportedError
from pipelex.tools.misc.exceptions import JsonTypeError, TomlError

WORKING_MEMORY_KEY = "working_memory"
MAIN_STUFF_KEY = "main_stuff"


def _extract_concept_code(concept_data: Any) -> str:
    """Extract a concept code string from a concept data value.

    Args:
        concept_data: The concept field from a stuff dict — may be a dict with
            a ``code`` key, a plain string, or another type.

    Returns:
        The concept code string.
    """
    if isinstance(concept_data, dict):
        concept_dict = cast("dict[str, Any]", concept_data)
        return str(concept_dict.get("code", ""))
    if isinstance(concept_data, str):
        return concept_data
    return str(concept_data)


def _extract_stuff_entry(stuff_data: dict[str, Any]) -> dict[str, Any] | None:
    """Extract a ``{ concept, content }`` input entry from a serialized stuff dict.

    Args:
        stuff_data: A serialized Stuff dict with ``concept`` and ``content`` keys.

    Returns:
        A dict with ``concept`` (str) and ``content`` (Any) keys, or None if
        the stuff dict is missing required fields.
    """
    concept_data: Any = stuff_data.get("concept")
    content_data: Any = stuff_data.get("content")
    if concept_data is None or content_data is None:
        return None
    return {
        "concept": _extract_concept_code(concept_data),
        "content": content_data,
    }


def resolve_stdin_inputs(stdin_data: dict[str, Any]) -> dict[str, Any]:
    """Resolve pipeline inputs from parsed stdin JSON data.

    Handles two formats:

    - **Flat inputs**: a plain dict of input name -> value (today's ``--inputs`` format).
      Returned as-is.
    - **Full envelope**: a dict with a ``working_memory`` key at the top level
      (from upstream ``--with-memory`` output). Stuffs are extracted from
      ``working_memory.root`` and converted to ``{ concept, content }`` entries
      suitable for ``PipelineInputs``.

    Args:
        stdin_data: Parsed JSON dict from stdin.

    Returns:
        A dict suitable for passing as ``inputs`` to the pipeline runner.
    """
    if WORKING_MEMORY_KEY not in stdin_data:
        return stdin_data

    working_memory_raw: Any = stdin_data[WORKING_MEMORY_KEY]
    if not isinstance(working_memory_raw, dict):
        agent_error("stdin envelope has invalid 'working_memory': expected a dict", error_type="JSONDecodeError")
    working_memory = cast("dict[str, Any]", working_memory_raw)

    root_raw: Any = working_memory.get("root", {})
    if not isinstance(root_raw, dict):
        agent_error("stdin envelope has invalid 'working_memory.root': expected a dict", error_type="JSONDecodeError")
    root = cast("dict[str, Any]", root_raw)

    aliases_raw: Any = working_memory.get("aliases", {})
    aliases: dict[str, str] = cast("dict[str, str]", aliases_raw) if isinstance(aliases_raw, dict) else {}

    resolved: dict[str, Any] = {}
    for stuff_name, stuff_data_raw in root.items():
        # Skip the main_stuff alias entry — we want the real named stuffs
        if stuff_name == MAIN_STUFF_KEY:
            continue

        if not isinstance(stuff_data_raw, dict):
            continue
        stuff_data = cast("dict[str, Any]", stuff_data_raw)

        entry = _extract_stuff_entry(stuff_data)
        if entry is not None:
            resolved[stuff_name] = entry

    # If there's a main_stuff that is NOT an alias (a real entry), include it too
    main_data_raw: Any = root.get(MAIN_STUFF_KEY)
    if main_data_raw is not None and MAIN_STUFF_KEY not in aliases and isinstance(main_data_raw, dict):
        main_data = cast("dict[str, Any]", main_data_raw)
        entry = _extract_stuff_entry(main_data)
        if entry is not None:
            resolved[MAIN_STUFF_KEY] = entry

    return resolved


def parse_cli_inputs(
    inputs_arg: str | None,
    *,
    stdin_fallback: bool = True,
    auto_inputs_dir: Path | None = None,
) -> dict[str, Any] | None:
    """Parse pipeline inputs from CLI --inputs argument, stdin, or an auto-detected directory.

    Resolution order:

    1. If ``inputs_arg`` is provided: parse as inline JSON (starts with ``{``) or file path.
    2. If ``inputs_arg`` is None and ``stdin_fallback`` is True and stdin is not a TTY:
       read JSON from stdin and resolve envelope format if present.
    3. If ``auto_inputs_dir`` is provided: probe it for a default inputs file
       (``inputs.json`` / ``inputs.toml``) and parse it (lowest-priority fallback).
    4. Otherwise return None (no inputs).

    The auto-detect probe — including its ``inputs.json``/``inputs.toml`` ambiguity
    rule — runs only here, in step 3, so it can never pre-empt higher-priority
    ``--inputs`` or piped stdin: the ambiguity error is surfaced only when the
    auto-detected file is the source actually being used.

    Args:
        inputs_arg: The ``--inputs`` CLI argument value, or None.
        stdin_fallback: Whether to attempt reading from stdin when ``inputs_arg`` is None.
        auto_inputs_dir: Directory to probe for a default inputs file (e.g. a
            directory target). Only consulted as a last-resort fallback when both
            ``inputs_arg`` and stdin are absent.

    Returns:
        Parsed inputs dict, or None if no inputs are available.
    """
    if inputs_arg is not None:
        return _parse_inputs_arg(inputs_arg)

    if stdin_fallback and not sys.stdin.isatty():
        stdin_inputs = _read_stdin_inputs()
        if stdin_inputs is not None:
            return stdin_inputs

    if auto_inputs_dir is not None:
        try:
            auto_inputs_file = find_default_inputs_file(auto_inputs_dir)
        except AmbiguousInputsFilesError as ambiguity_exc:
            agent_error(ambiguity_exc.message, error_type="AmbiguousInputsFilesError", cause=ambiguity_exc)
        if auto_inputs_file is not None:
            return _parse_inputs_arg(str(auto_inputs_file))

    return None


def _parse_inputs_arg(inputs_arg: str) -> dict[str, Any] | None:
    """Parse the --inputs argument as inline JSON or file path.

    Args:
        inputs_arg: The --inputs CLI argument value.

    Returns:
        Parsed inputs dict, or None if empty.
    """
    if inputs_arg.startswith("{"):
        try:
            result: dict[str, Any] = json.loads(inputs_arg)
            return result
        except json.JSONDecodeError as exc:
            agent_error(f"Failed to parse inline JSON inputs: {exc}", error_type="JSONDecodeError", cause=exc)
    else:
        try:
            loaded = load_inputs_dict_from_path(Path(inputs_arg))
            # Resolve relative url paths against the inputs file's parent directory
            base_dir = Path(inputs_arg).parent.resolve()
            return resolve_inputs_paths(loaded, base_dir=base_dir)
        except FileNotFoundError as exc:
            agent_error(f"Input file not found: {inputs_arg}", error_type="FileNotFoundError", cause=exc)
        except json.JSONDecodeError as exc:
            agent_error(f"Input file contains invalid JSON: {inputs_arg}: {exc}", error_type="JSONDecodeError", cause=exc)
        except JsonTypeError as exc:
            agent_error(f"Input file must be a valid JSON dictionary: {inputs_arg}", error_type="JsonTypeError", cause=exc)
        except TomlError as exc:
            agent_error(exc.message, error_type="TomlError", cause=exc)
        except InputsDatetimeNotSupportedError as exc:
            agent_error(exc.message, error_type="InputsDatetimeNotSupportedError", cause=exc)
    return None


def _read_stdin_inputs() -> dict[str, Any] | None:
    """Read and parse JSON from stdin, applying envelope detection.

    Returns:
        Resolved inputs dict, or None if stdin is empty.
    """
    try:
        stdin_raw = sys.stdin.read()
    except (OSError, UnicodeDecodeError):
        return None

    if not stdin_raw.strip():
        return None

    try:
        parsed: Any = json.loads(stdin_raw)
    except json.JSONDecodeError as exc:
        agent_error(f"Failed to parse stdin JSON: {exc}", error_type="JSONDecodeError", cause=exc)

    if not isinstance(parsed, dict):
        agent_error("stdin JSON must be a dictionary, got " + type(parsed).__name__, error_type="JSONDecodeError")

    parsed_dict = cast("dict[str, Any]", parsed)
    return resolve_stdin_inputs(parsed_dict)
