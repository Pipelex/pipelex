"""The method a hosted run names, read from the same places a local run loads it from.

Both CLIs resolve a hosted run's source here, so `pipelex run --hosted` and `pipelex-agent run --runner hosted`
send the same thing for the same arguments:

- `run bundle` sends the bundle file, then every `.mthds` file in the library directories a local run would load
  (the bundle's own directory when the target is one, then `-L`; with neither, `PIPELEXPATH`), each file once.
- `run pipe` sends every `.mthds` file in its library directories: the installed method exporting the pipe and
  `-L`, else `PIPELEXPATH`. With none of them there is nothing to send, and the run is refused.
- `run method` names a published address as `method_ref` and a stored method's catalog id (`mt_…`) as `method_id`,
  both resolved by the hosted API, so nothing is fetched or read here. An installed method's name or a local
  method directory is resolved as a local run resolves it, and its files are sent; an installed method wins over a
  catalog id spelled the same, since `mt_reports` is a valid method name too.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from pipelex_sdk.crate_models import MthdsFileItem
from pydantic import BaseModel, ConfigDict

from pipelex.cli.installed_methods import DuplicateMethodNameError, MethodNotFoundError, find_method_by_name
from pipelex.cli.method_resolver import method_output_base_dir, resolve_method_target
from pipelex.hosted.exceptions import HostedRunSourceError
from pipelex.hosted.execution import get_or_load_pipelex_config
from pipelex.methods.method_ref import looks_like_method_ref, parse_method_ref
from pipelex.mthds_parsing.helpers import MTHDS_EXTENSION, is_pipelex_file
from pipelex.system.environment import PIPELEXPATH_ENV_KEY, get_pipelexpath_dirs
from pipelex.tools.misc.file_utils import find_files_in_dir

if TYPE_CHECKING:
    from collections.abc import Sequence

#: A stored method's catalog id on the hosted platform, as `pipelex-server` mints it.
METHOD_ID_PATTERN = re.compile(r"^mt_[A-Za-z0-9_-]{1,64}$")


def looks_like_method_id(target: str) -> bool:
    """Whether a `run method` target is spelled as a stored method's catalog id (`mt_…`).

    The spelling alone does not decide it: a method may be installed under such a name, and then that method is the
    target. `resolve_hosted_method_target` checks.
    """
    return METHOD_ID_PATTERN.fullmatch(target) is not None


def _names_an_installed_method(*, name: str, library_dirs: list[str] | None) -> bool:
    """Whether an installed method, or one in the library directories, bears this name; several count, and are refused later."""
    try:
        find_method_by_name(name, library_dirs=library_dirs)
    except MethodNotFoundError:
        return False
    except DuplicateMethodNameError:
        return True
    return True


def hosted_library_dirs(*, library_dirs: Sequence[str] | None) -> Sequence[str | Path] | None:
    """The library directories a local run would load: `-L` when given, which replaces `PIPELEXPATH`, else `PIPELEXPATH`.

    `None` when neither names any.
    """
    if library_dirs is not None:
        return library_dirs
    return get_pipelexpath_dirs()


def collect_mthds_files(*, primary: Path | None, library_dirs: Sequence[str | Path] | None) -> list[MthdsFileItem]:
    """Read the `.mthds` files a local run would load: `primary` first, then each library directory's, each file once.

    A library directory is scanned recursively, skipping the configured `[interpreter.scan] excluded_dirs`, as a
    local load scans it; a library entry naming a `.mthds` file is taken as it is; a missing one is skipped, as a
    local load skips it. Each file carries its path as its label: the hosted API names it in the validation errors
    of the method's signature, read before the run, while the run route takes the bare contents.

    Raises:
        HostedRunSourceError: If a file cannot be read.
    """
    excluded_dirs = list(get_or_load_pipelex_config().interpreter.scan.excluded_dirs)
    ordered: list[Path] = []
    if primary is not None:
        ordered.append(primary)
    for library_dir in library_dirs or []:
        library_path = Path(library_dir)
        if library_path.is_file() and is_pipelex_file(library_path):
            ordered.append(library_path)
        elif library_path.is_dir():
            found = find_files_in_dir(dir_path=library_path, pattern=f"*{MTHDS_EXTENSION}", excluded_dirs=excluded_dirs)
            ordered.extend(path for path in found if is_pipelex_file(path))

    seen: set[Path] = set()
    files: list[MthdsFileItem] = []
    for path in ordered:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            msg = f"Could not read the method file '{path}' to send it to the hosted API: {exc}"
            raise HostedRunSourceError(msg) from exc
        files.append(MthdsFileItem(content=content, source=str(path)))
    return files


def hosted_pipe_library_files(*, library_dirs: Sequence[str] | None) -> list[MthdsFileItem]:
    """The library a hosted `run pipe` sends: its library directories', else `PIPELEXPATH`'s.

    Raises:
        HostedRunSourceError: If no directory names a library, or the ones named hold no `.mthds` file.
    """
    effective_dirs = hosted_library_dirs(library_dirs=library_dirs or None)
    if not effective_dirs:
        msg = (
            f"A hosted pipe run sends the library that defines the pipe, and none is named: pass -L <dir> (repeatable), "
            f"set {PIPELEXPATH_ENV_KEY}, or run the bundle with 'run bundle <path>'."
        )
        raise HostedRunSourceError(msg)
    files = collect_mthds_files(primary=None, library_dirs=effective_dirs)
    if not files:
        named = ", ".join(str(one_dir) for one_dir in effective_dirs)
        msg = f"No .mthds file found to send to the hosted API in {named}."
        raise HostedRunSourceError(msg)
    return files


class HostedMethodTarget(BaseModel):
    """What a hosted `run method` sends, and where its outputs and inputs are anchored.

    Exactly one of `mthds_files`, `method_ref` and `method_id` is set, as `HostedRunRequest` takes them.
    """

    model_config = ConfigDict(frozen=True)

    mthds_files: list[MthdsFileItem] | None = None
    method_ref: str | None = None
    method_id: str | None = None
    #: The pipe to run: `--pipe`, or a local method's `main_pipe`; `None` lets the hosted API run the entry pipe.
    pipe_code: str | None = None
    #: A short name for the run's outputs: the pipe, else the method.
    label: str
    #: The directory default outputs go under: a local method's own, else the working directory.
    output_base_dir: Path
    #: The directory a relative `--inputs` file path resolves against: a local method's own, else the working one.
    inputs_anchor_dir: Path


def resolve_hosted_method_target(*, name: str, pipe_override: str | None, library_dirs: list[str] | None) -> HostedMethodTarget:
    """Resolve a hosted `run method` target.

    Args:
        name: A catalog id (`mt_…`), a method address or GitHub URL, an installed method's name, or a local method
            directory. A name spelled as a catalog id that an installed method bears is that method.
        pipe_override: `--pipe`.
        library_dirs: `-L`, sent along with a local method's files. A method the hosted API resolves loads no local
            library, so `-L` is refused with one.

    Raises:
        HostedRunSourceError: If `-L` is given with a method the hosted API resolves, or a local file cannot be read.
        MethodRefParseError: If an address does not parse.
        typer.Exit: If an installed method's name does not resolve, as on a local run.
    """
    cwd = Path.cwd()
    remote_ref: str | None = None
    remote_id: str | None = None
    if looks_like_method_id(name) and not _names_an_installed_method(name=name, library_dirs=library_dirs):
        remote_id = name
    elif looks_like_method_ref(name):
        remote_ref = parse_method_ref(name).ref_str
    if remote_ref is not None or remote_id is not None:
        if library_dirs:
            msg = (
                f"-L does not apply to '{name}': the hosted API resolves this method and loads no local library. "
                "Install it and run it by name, or run its bundle with 'run bundle <path> -L <dir>'."
            )
            raise HostedRunSourceError(msg)
        label = pipe_override or (parse_method_ref(remote_ref).address.rsplit("/", 1)[-1] if remote_ref else name)
        return HostedMethodTarget(
            method_ref=remote_ref,
            method_id=remote_id,
            pipe_code=pipe_override,
            label=label,
            output_base_dir=cwd,
            inputs_anchor_dir=cwd,
        )

    pipe_code, method_library_dirs, method = resolve_method_target(method_name=name, pipe_override=pipe_override, library_dirs=library_dirs)
    all_library_dirs = [*method_library_dirs, *(library_dirs or [])]
    mthds_files = collect_mthds_files(primary=None, library_dirs=all_library_dirs)
    if not mthds_files:
        msg = f"Method '{name}' at '{method.path}' holds no .mthds file to send to the hosted API."
        raise HostedRunSourceError(msg)
    return HostedMethodTarget(
        mthds_files=mthds_files,
        pipe_code=pipe_code,
        label=pipe_code,
        output_base_dir=method_output_base_dir(method=method),
        inputs_anchor_dir=Path(method_library_dirs[0]),
    )
