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
from typing import Any

from pipelex.builder.conventions import DEFAULT_INPUTS_FILE_NAME, DEFAULT_INPUTS_TOML_FILE_NAME
from pipelex.cli.commands.run.exceptions import AmbiguousInputsFilesError
from pipelex.core.stuffs.date_content import DateContent
from pipelex.core.stuffs.time_content import TimeContent
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
        converted to a ``DateContent`` and any top-level TOML time-of-day literal to
        a ``TimeContent`` (each enters the pipeline-inputs seam as a bare content
        instance); nested temporal values are left in place for the
        envelope/structure factory arms to consume.

    Raises:
        FileNotFoundError: If the file does not exist.
        TomlError: If a ``.toml`` file has invalid TOML syntax.
        json.JSONDecodeError: If a JSON file has invalid JSON syntax.
        JsonTypeError: If a JSON file does not hold a dictionary.
    """
    inputs_dict: dict[str, Any]
    if path.suffix.lower() == TOML_SUFFIX:
        inputs_dict = load_toml_from_path(path)
    else:
        inputs_dict = load_json_dict_from_path(path)
    return _convert_temporal_inputs(inputs_dict)


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


def find_default_inputs_file(*, directory: Path) -> Path | None:
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


def _convert_temporal_inputs(inputs_dict: dict[str, Any]) -> dict[str, Any]:
    """Map top-level TOML temporal literals to native ``Date`` / ``Time`` inputs.

    Only TOML can produce temporal Python objects (JSON has no temporal type), but the
    walk is format-agnostic and harmless on JSON (which yields none).

    - A **top-level** ``datetime.datetime`` / ``datetime.date`` becomes a ``DateContent``
      (a datetime keeps its time and offset; a bare date has ``time=None``). It then enters
      the pipeline-inputs seam as a bare content instance, inferred as ``native.Date``.
    - A **top-level** ``datetime.time`` becomes a ``TimeContent`` (offset kept when stated),
      inferred as ``native.Time``. A time never silently becomes a ``Date`` — shaping a
      ``Time`` into a ``Date`` slot fails the concept-compatibility check downstream.
    - A **nested** temporal value (inside an envelope's ``content`` or a structured dict) is
      left in place for the factory arms and pydantic validation to consume.

    Args:
        inputs_dict: The loaded top-level inputs dictionary.

    Returns:
        A new dict with top-level temporal literals converted.
    """
    converted: dict[str, Any] = {}
    for key, value in inputs_dict.items():
        if isinstance(value, datetime.datetime):
            converted[key] = DateContent(date=value.date(), time=value.timetz())
        elif isinstance(value, datetime.date):
            converted[key] = DateContent(date=value)
        elif isinstance(value, datetime.time):
            converted[key] = TimeContent(time=value)
        else:
            converted[key] = value
    return converted
