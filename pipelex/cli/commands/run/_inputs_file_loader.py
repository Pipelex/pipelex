"""Shared pipeline-inputs file loader for the run CLI surfaces.

The inputs format is discriminated by file extension: a ``.toml`` suffix loads
through the TOML parser, every other suffix (``.json``, extensionless, ...)
keeps the JSON behavior. Both the main CLI (``pipelex run``) and the agent CLI
(``pipelex-agent run``) load inputs files through this module so the two
surfaces cannot drift — same deal for the ``inputs.json`` / ``inputs.toml``
auto-detect probe and its ambiguity rule.
"""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any, cast

from pipelex.builder.conventions import DEFAULT_INPUTS_FILE_NAME, DEFAULT_INPUTS_TOML_FILE_NAME
from pipelex.cli.commands.run.exceptions import AmbiguousInputsFilesError, InputsDatetimeNotSupportedError
from pipelex.tools.misc.json_utils import load_json_dict_from_path
from pipelex.tools.misc.toml_utils import load_toml_from_path

TOML_SUFFIX = ".toml"


def load_inputs_dict_from_path(path: Path) -> dict[str, Any]:
    """Load a pipeline-inputs dict from a JSON or TOML file, discriminated by extension.

    Args:
        path: Path to the inputs file. A ``.toml`` suffix selects the TOML
            parser; every other suffix (including none) is parsed as JSON.

    Returns:
        The loaded inputs dictionary.

    Raises:
        FileNotFoundError: If the file does not exist.
        TomlError: If a ``.toml`` file has invalid TOML syntax.
        json.JSONDecodeError: If a JSON file has invalid JSON syntax.
        JsonTypeError: If a JSON file does not hold a dictionary.
        InputsDatetimeNotSupportedError: If a loaded value is a TOML
            datetime/date/time instance (no native concept support yet).
    """
    inputs_dict: dict[str, Any]
    if path.suffix == TOML_SUFFIX:
        inputs_dict = load_toml_from_path(path)
    else:
        inputs_dict = load_json_dict_from_path(path)
    _assert_no_datetime_values(inputs_dict, source_path=path, key_path="")
    return inputs_dict


def resolve_inputs_arg_against_dir(inputs_arg: str | None, *, base_dir: Path) -> str | None:
    """Resolve a relative ``--inputs`` file path against ``base_dir``.

    Inline JSON (a ``{`` prefix), absolute paths, and None pass through
    unchanged. Shared by the ``run method`` commands of both CLI surfaces so
    the resolve-against-the-method-dir rule cannot drift.

    Args:
        inputs_arg: The raw ``--inputs`` CLI argument value, or None.
        base_dir: The directory relative file paths are resolved against.

    Returns:
        The resolved ``--inputs`` value, same form as the input.
    """
    if not inputs_arg or inputs_arg.startswith("{"):
        return inputs_arg
    inputs_path = Path(inputs_arg)
    if inputs_path.is_absolute():
        return inputs_arg
    return str(base_dir / inputs_path)


def find_default_inputs_file(directory: Path) -> Path | None:
    """Probe a bundle directory for the default inputs file (JSON or TOML).

    Args:
        directory: The bundle/pipeline directory to probe.

    Returns:
        The path to ``inputs.json`` or ``inputs.toml`` when exactly one exists,
        None when neither does.

    Raises:
        AmbiguousInputsFilesError: When both default files exist — the caller
            must pass ``--inputs`` explicitly.
    """
    json_file = directory / DEFAULT_INPUTS_FILE_NAME
    toml_file = directory / DEFAULT_INPUTS_TOML_FILE_NAME
    json_exists = json_file.is_file()
    toml_exists = toml_file.is_file()
    if json_exists and toml_exists:
        msg = (
            f"Directory '{directory}' holds both '{DEFAULT_INPUTS_FILE_NAME}' and '{DEFAULT_INPUTS_TOML_FILE_NAME}', "
            "so inputs auto-detection is ambiguous. Pass --inputs explicitly to choose one."
        )
        raise AmbiguousInputsFilesError(msg)
    if json_exists:
        return json_file
    if toml_exists:
        return toml_file
    return None


def _assert_no_datetime_values(value: Any, *, source_path: Path, key_path: str) -> None:
    """Recursively reject datetime/date/time instances in a loaded inputs value.

    Only TOML can produce such values (JSON has no datetime type), but the walk
    is format-agnostic and harmless to run on both.

    Args:
        value: The loaded value to inspect (dict, list, scalar, ...).
        source_path: The inputs file the value was loaded from, for the error message.
        key_path: Dotted/indexed path to ``value`` inside the inputs dict, empty at the root.

    Raises:
        InputsDatetimeNotSupportedError: On the first datetime-typed value found.
    """
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        located = f" at '{key_path}'" if key_path else ""
        msg = (
            f"Inputs file '{source_path}' holds a TOML datetime value{located} ({value!r}). "
            "TOML datetime inputs are not supported yet: quote the value as a string in the meantime."
        )
        raise InputsDatetimeNotSupportedError(msg)
    if isinstance(value, dict):
        value_dict = cast("dict[str, Any]", value)
        for key, sub_value in value_dict.items():
            sub_key_path = f"{key_path}.{key}" if key_path else str(key)
            _assert_no_datetime_values(sub_value, source_path=source_path, key_path=sub_key_path)
    elif isinstance(value, list):
        value_list = cast("list[Any]", value)
        for index_item, sub_value in enumerate(value_list):
            _assert_no_datetime_values(sub_value, source_path=source_path, key_path=f"{key_path}[{index_item}]")
