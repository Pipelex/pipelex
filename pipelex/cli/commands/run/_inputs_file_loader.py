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
from pipelex.cli.commands.run.exceptions import AmbiguousInputsFilesError, InputsTimeOnlyNotSupportedError
from pipelex.core.stuffs.date_content import DateContent
from pipelex.tools.misc.json_utils import load_json_dict_from_path
from pipelex.tools.misc.toml_utils import load_toml_from_path

TOML_SUFFIX = ".toml"


def load_inputs_dict_from_path(path: Path) -> dict[str, Any]:
    """Load a pipeline-inputs dict from a JSON or TOML file, discriminated by extension.

    Args:
        path: Path to the inputs file. A ``.toml`` suffix selects the TOML
            parser; every other suffix (including none) is parsed as JSON.

    Returns:
        The loaded inputs dictionary. Any top-level TOML date/datetime literal is
        converted to a ``DateContent`` (which enters the pipeline-inputs seam as a
        bare content instance); nested date/datetime values are left in place for
        the envelope/structure factory arms to consume.

    Raises:
        FileNotFoundError: If the file does not exist.
        TomlError: If a ``.toml`` file has invalid TOML syntax.
        json.JSONDecodeError: If a JSON file has invalid JSON syntax.
        JsonTypeError: If a JSON file does not hold a dictionary.
        InputsTimeOnlyNotSupportedError: If a loaded value is a bare TOML
            time-of-day (which has no date to attach to and no native concept).
    """
    inputs_dict: dict[str, Any]
    if path.suffix.lower() == TOML_SUFFIX:
        inputs_dict = load_toml_from_path(path)
    else:
        inputs_dict = load_json_dict_from_path(path)
    return _convert_temporal_inputs(inputs_dict, source_path=path)


def resolve_inputs_arg_against_dir(inputs_arg: str | None, *, base_dir: Path) -> str | None:
    """Resolve a relative ``--inputs`` file path against ``base_dir``.

    Inline JSON (a ``{`` prefix), URI-scheme strings (containing ``://``, e.g.
    ``https://...``/``s3://...``) and None pass through unchanged. A file path
    has ``~`` expanded first; if it is then absolute it is returned as-is,
    otherwise it is joined onto ``base_dir``. Shared by the ``run method``
    commands of both CLI surfaces so the resolve-against-the-method-dir rule
    cannot drift.

    Args:
        inputs_arg: The raw ``--inputs`` CLI argument value, or None.
        base_dir: The directory relative file paths are resolved against.

    Returns:
        The resolved ``--inputs`` value, same form as the input.
    """
    if not inputs_arg or inputs_arg.startswith("{") or "://" in inputs_arg:
        return inputs_arg
    # expanduser so a quoted/`=`-form `~/inputs.toml` resolves to the home dir, not a literal `~` component
    # (matches the --save-csv handling in _run_core.py). Return the expanded path in both branches, since
    # nothing downstream re-expands it.
    inputs_path = Path(inputs_arg).expanduser()
    if inputs_path.is_absolute():
        return str(inputs_path)
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


def _convert_temporal_inputs(inputs_dict: dict[str, Any], *, source_path: Path) -> dict[str, Any]:
    """Map TOML temporal literals to native ``Date`` inputs, rejecting bare times.

    Only TOML can produce temporal Python objects (JSON has no temporal type), but the
    walk is format-agnostic and harmless on JSON (which yields none).

    - A **top-level** ``datetime.datetime`` / ``datetime.date`` becomes a ``DateContent``
      (a datetime keeps its time and offset; a bare date has ``time=None``). It then enters
      the pipeline-inputs seam as a bare content instance, inferred as ``native.Date``.
    - A ``datetime.time`` **anywhere** in the tree is rejected: a time of day alone has no
      date to attach to and no native concept.
    - A **nested** date/datetime (inside an envelope's ``content`` or a structured dict) is
      left in place for the factory arms and pydantic validation to consume.

    Args:
        inputs_dict: The loaded top-level inputs dictionary.
        source_path: The inputs file the values were loaded from, for the error message.

    Returns:
        A new dict with top-level temporal literals converted.

    Raises:
        InputsTimeOnlyNotSupportedError: On the first bare time-of-day value found.
    """
    converted: dict[str, Any] = {}
    for key, value in inputs_dict.items():
        _reject_time_of_day(value, source_path=source_path, key_path=str(key))
        if isinstance(value, datetime.datetime):
            converted[key] = DateContent(date=value.date(), time=value.timetz())
        elif isinstance(value, datetime.date):
            converted[key] = DateContent(date=value)
        else:
            converted[key] = value
    return converted


def _reject_time_of_day(value: Any, *, source_path: Path, key_path: str) -> None:
    """Recursively reject bare ``datetime.time`` values; leave date/datetime alone.

    Args:
        value: The loaded value to inspect (dict, list, scalar, ...).
        source_path: The inputs file the value was loaded from, for the error message.
        key_path: Dotted/indexed path to ``value`` inside the inputs dict.

    Raises:
        InputsTimeOnlyNotSupportedError: On the first ``datetime.time`` value found.
    """
    # datetime is a subclass of date and neither is a time, so this only fires on a bare time-of-day.
    if isinstance(value, datetime.time):
        located = f" at '{key_path}'" if key_path else ""
        msg = (
            f"Inputs file '{source_path}' holds a bare TOML time-of-day{located} ({value!r}). "
            "A time of day alone has no date to attach to: include the date (e.g. 2026-07-06T12:00:00) "
            "or quote the value as a string."
        )
        raise InputsTimeOnlyNotSupportedError(msg)
    if isinstance(value, dict):
        value_dict = cast("dict[str, Any]", value)
        for key, sub_value in value_dict.items():
            sub_key_path = f"{key_path}.{key}" if key_path else str(key)
            _reject_time_of_day(sub_value, source_path=source_path, key_path=sub_key_path)
    elif isinstance(value, list):
        value_list = cast("list[Any]", value)
        for index_item, sub_value in enumerate(value_list):
            _reject_time_of_day(sub_value, source_path=source_path, key_path=f"{key_path}[{index_item}]")
