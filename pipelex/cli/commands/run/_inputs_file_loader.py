"""Shared pipeline-inputs file loader for the run CLI surfaces.

The inputs format is discriminated by file extension: a ``.toml`` suffix loads
through the TOML parser, every other suffix (``.json``, extensionless, ...)
keeps the JSON behavior. Both the main CLI (``pipelex run``) and the agent CLI
(``pipelex-agent run``) load inputs files through this module so the two
surfaces cannot drift — same deal for the ``inputs.json`` / ``inputs.toml``
auto-detect probe, its ambiguity rule and its refusal of anything but a
regular file.
"""

from __future__ import annotations

import datetime
import errno
import os
import stat
from pathlib import Path
from typing import Any, NamedTuple

from pipelex.cli.commands.run.exceptions import AmbiguousInputsFilesError, AutoDetectedInputsFileError
from pipelex.core.stuffs.date_content import DateContent
from pipelex.core.stuffs.time_content import TimeContent
from pipelex.pipeline.default_file_names import DEFAULT_INPUTS_FILE_NAME, DEFAULT_INPUTS_TOML_FILE_NAME
from pipelex.tools.misc.json_utils import load_json_dict_from_bytes
from pipelex.tools.misc.toml_utils import load_toml_from_bytes

TOML_SUFFIX = ".toml"

# Opening the auto-detected inputs file: read-only, never following a link in its last component, and never blocking
# on a named pipe, so the descriptor `fstat` judges is the one the bytes are read from. `O_NOFOLLOW` and `O_NONBLOCK`
# do not exist on Windows, where the `lstat` check before the open is the only guard; `O_BINARY` exists only there.
_NO_FOLLOW_READ_FLAGS = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
_READ_CHUNK_BYTES = 1 << 16


class DetectedInputsFile(NamedTuple):
    """The inputs file auto-detection found in a bundle directory, with the bytes read from it.

    The bytes were read from a descriptor opened without following a link, so whoever loads the file parses these
    bytes and never opens its path again.
    """

    path: Path
    data: bytes


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
    return load_inputs_dict_from_bytes(data=path.read_bytes(), path=path)


def load_inputs_dict_from_bytes(*, data: bytes, path: Path) -> dict[str, Any]:
    """Load a pipeline-inputs dict from the bytes of a JSON or TOML file, as ``load_inputs_dict_from_path`` loads the file.

    Args:
        data: The bytes read from the inputs file.
        path: The file they were read from: its suffix selects the parser, and a parsing error names it.

    Raises:
        TomlError: If a ``.toml`` file has invalid TOML syntax.
        json.JSONDecodeError: If a JSON file has invalid JSON syntax.
        JsonTypeError: If a JSON file does not hold a dictionary.
    """
    inputs_dict: dict[str, Any]
    if path.suffix.lower() == TOML_SUFFIX:
        inputs_dict = load_toml_from_bytes(data=data, source=path)
    else:
        inputs_dict = load_json_dict_from_bytes(data=data, source=path)
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


def read_default_inputs_file(*, directory: Path) -> DetectedInputsFile | None:
    """Probe a bundle directory for the default inputs file (JSON or TOML), and read it.

    Each name is looked up by ``lstat``, never following a link, and only a regular file is read: a link named
    ``inputs.json`` in a checked-out method, which the method's tree can keep out, for instance through a
    ``.gitignore``, would otherwise carry JSON from outside the method's folder into the run. The file is read through
    a descriptor opened without following a link and judged by ``fstat``, so an entry swapped for a link or for
    anything else between the lookup and the read is refused too, and its bytes are returned so that nothing opens the
    path again. An inputs file the caller names with ``--inputs`` never comes through here, and is read as given, a
    link followed.

    Args:
        directory: The bundle/pipeline directory to probe.

    Returns:
        The path to ``inputs.json`` or ``inputs.toml`` and the bytes read from it, when exactly one exists,
        None when neither does.

    Raises:
        AmbiguousInputsFilesError: When an entry of each name exists — the caller
            must pass ``--inputs`` explicitly.
        AutoDetectedInputsFileError: When the one entry found is a symbolic link,
            a directory or any other entry that is not a regular file.
    """
    json_file = directory / DEFAULT_INPUTS_FILE_NAME
    toml_file = directory / DEFAULT_INPUTS_TOML_FILE_NAME
    json_mode = _entry_mode(path=json_file)
    toml_mode = _entry_mode(path=toml_file)
    if json_mode is not None and toml_mode is not None:
        msg = (
            f"Directory '{directory}' holds both '{DEFAULT_INPUTS_FILE_NAME}' and '{DEFAULT_INPUTS_TOML_FILE_NAME}', "
            "so inputs auto-detection is ambiguous. Pass --inputs explicitly to choose one."
        )
        raise AmbiguousInputsFilesError(msg)
    found: Path
    if json_mode is not None:
        _refuse_unless_regular_file(path=json_file, mode=json_mode)
        found = json_file
    elif toml_mode is not None:
        _refuse_unless_regular_file(path=toml_file, mode=toml_mode)
        found = toml_file
    else:
        return None
    return DetectedInputsFile(path=found, data=_read_regular_file_without_following_link(path=found))


def _entry_mode(*, path: Path) -> int | None:
    """The mode of the entry at ``path``, a symbolic link not followed, or None when there is none."""
    try:
        return path.lstat().st_mode
    except (FileNotFoundError, NotADirectoryError):
        return None


def _read_regular_file_without_following_link(*, path: Path) -> bytes:
    """The bytes of the regular file at ``path``, read from a descriptor opened without following a link.

    Raises:
        AutoDetectedInputsFileError: When ``path`` is a symbolic link, which fails the open, or the opened entry is
            not a regular file.
    """
    try:
        descriptor = os.open(path, _NO_FOLLOW_READ_FLAGS)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            # The entry was swapped for a link since it was looked up: `O_NOFOLLOW` refuses to open a link.
            raise _not_a_regular_file_error(path=path, mode=stat.S_IFLNK) from exc
        raise
    try:
        _refuse_unless_regular_file(path=path, mode=os.fstat(descriptor).st_mode)
        chunks: list[bytes] = []
        while chunk := os.read(descriptor, _READ_CHUNK_BYTES):
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _refuse_unless_regular_file(*, path: Path, mode: int) -> None:
    """Refuse an auto-detected inputs file that is not a regular file, naming what it is.

    Raises:
        AutoDetectedInputsFileError: When ``mode`` is not a regular file's.
    """
    if stat.S_ISREG(mode):
        return
    raise _not_a_regular_file_error(path=path, mode=mode)


def _not_a_regular_file_error(*, path: Path, mode: int) -> AutoDetectedInputsFileError:
    """The refusal of an auto-detected inputs file of mode ``mode``, which is not a regular file's, naming what it is."""
    what: str
    if stat.S_ISLNK(mode):
        what = "a symbolic link"
    elif stat.S_ISDIR(mode):
        what = "a directory"
    else:
        what = "not a regular file"
    msg = (
        f"'{path}' was found as the run's inputs because no --inputs was given, but it is {what}. "
        "An inputs file found automatically must be a regular file, so that a link never carries data from outside "
        "the method's folder into the run. Replace it with the file itself, or name the inputs with --inputs <path>."
    )
    return AutoDetectedInputsFileError(msg)


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
