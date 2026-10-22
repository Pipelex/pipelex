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

The files a local method is sent as are the bundles of the method trees the run reads (`pipelex.libraries.method_trees`),
each read as its tree's listing hashed it, gathered into the one tree the MTHDS protocol's `files` map carries: each
bundle is keyed by a tree path, the hosted API names it by that path in the diagnostics of a method that does not load,
and both `POST /v1/pipe-io` and the run route read the same tree (`method_tree_contents`).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

from mthds.method_tree.file_entry import excluded_name_violation
from mthds.method_tree.tree_path import nfc, path_collisions, tree_path_violation
from pydantic import BaseModel, ConfigDict

from pipelex.cli.commands.run._run_output_folder import run_output_label
from pipelex.cli.exceptions import DuplicateMethodNameError, MethodNotFoundError
from pipelex.cli.installed_methods import find_method_by_name
from pipelex.cli.method_resolver import method_output_base_dir, resolve_method_target
from pipelex.core.method_trees.tree_bundle import TreeBundle
from pipelex.hosted.exceptions import HostedRunSourceError
from pipelex.libraries.exceptions import MethodTreeLoadError
from pipelex.libraries.method_trees import list_library_bundle_files, list_local_method_tree, lone_file_member, read_tree_bundle_as_listed
from pipelex.methods.method_ref import looks_like_method_ref, parse_method_ref
from pipelex.mthds_parsing.helpers import is_pipelex_file
from pipelex.system.environment import PIPELEXPATH_ENV_KEY, get_pipelexpath_dirs

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mthds.method_tree.models import MethodTree

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


#: The folder a tree beside the method is keyed under when its root's name is no folder a tree may hold, numbered from 1.
_FALLBACK_FOLDER_STEM = "library-"
#: A file name to ask the membership rule whether a folder may hold anything, since it judges file paths alone.
_PROBE_FILE_NAME = "probe.mthds"


class _SentBundle(NamedTuple):
    """A bundle to send: the root of the tree listing it, its tree path there, and its bytes as that listing hashed them."""

    root: Path
    tree_path: str
    data: bytes


def _bundles_to_send(*, method_tree: MethodTree | None, library_dirs: Sequence[str | Path] | None) -> list[TreeBundle]:
    """The bundles a local run would load, each as the member of its listed tree: `method_tree`'s entry, then each library's.

    Raises:
        HostedRunSourceError: If a tree cannot be listed.
    """
    bundles: list[TreeBundle] = []
    if method_tree is not None and method_tree.entry is not None:
        bundles.append(TreeBundle(tree=method_tree, tree_path=method_tree.entry))
    for library_dir in library_dirs or []:
        library_path = Path(library_dir)
        try:
            if library_path.is_file() and is_pipelex_file(library_path):
                bundles.append(lone_file_member(tree=list_local_method_tree(handed_over=library_path), bundle_file=library_path))
            elif library_path.is_dir():
                bundles.extend(bundle_file.tree_bundle for bundle_file in list_library_bundle_files(library_dirs=[library_path]))
        except MethodTreeLoadError as exc:
            msg = f"Could not list the method tree of '{library_path}' to send its bundles to the hosted API: {exc.message}"
            raise HostedRunSourceError(msg) from exc
    return bundles


def _is_tree_folder(*, folder: str) -> bool:
    """Whether a folder, one name or several joined by `/`, is one a tree may hold files in."""
    return tree_path_violation(folder) is None and not excluded_name_violation(f"{folder}/{_PROBE_FILE_NAME}")


def _fresh_folder(*, name: str, used_folders: set[str]) -> str:
    """A top-level folder for a tree beside the method: its root's name, numbered when taken, else a numbered `library-`.

    `used_folders` holds the top-level names already taken, case-folded, since a tree refuses two names equal once folded.
    """
    if _is_tree_folder(folder=name):
        candidate = name
        index_name = 1
        while candidate.casefold() in used_folders:
            index_name += 1
            candidate = f"{name}-{index_name}"
        if _is_tree_folder(folder=candidate):
            return candidate
    index_fallback = 1
    while f"{_FALLBACK_FOLDER_STEM}{index_fallback}".casefold() in used_folders:
        index_fallback += 1
    return f"{_FALLBACK_FOLDER_STEM}{index_fallback}"


def _tree_prefixes(*, sent: list[_SentBundle], anchor: Path) -> dict[Path, str]:
    """The folder each listed tree's bundles are keyed under, in the one tree the request carries, by the tree's root.

    The tree rooted at `anchor`, the method's own, is keyed by its own tree paths, as the run names its bundles, and a
    tree rooted under it, such as a package nested in the method's folder, under its folder from there: the method's
    files keep the places they hold on disk. Every other tree, such as a `-L` directory beside the method, goes under a
    top-level folder of its own that no other key uses, its root's name, numbered when taken, so no library is mixed
    into a folder of the method's.
    """
    prefixes: dict[Path, str] = {}
    beside: list[Path] = []
    for one_bundle in sent:
        root = one_bundle.root
        if root in prefixes or root in beside:
            continue
        if root == anchor:
            prefixes[root] = ""
        elif root.is_relative_to(anchor) and _is_tree_folder(folder=nfc(root.relative_to(anchor).as_posix())):
            prefixes[root] = f"{nfc(root.relative_to(anchor).as_posix())}/"
        else:
            beside.append(root)
    used_folders = {
        f"{prefixes[one_bundle.root]}{one_bundle.tree_path}".split("/", 1)[0].casefold() for one_bundle in sent if one_bundle.root in prefixes
    }
    for root in beside:
        folder = _fresh_folder(name=nfc(root.name), used_folders=used_folders)
        used_folders.add(folder.casefold())
        prefixes[root] = f"{folder}/"
    return prefixes


def method_tree_contents(*, method_tree: MethodTree | None, library_dirs: Sequence[str | Path] | None) -> dict[str, bytes]:
    """The bundles a local run would load, as the one tree a hosted run sends: each bundle's bytes by its tree path.

    `method_tree`'s entry goes first, when it is the tree of a bundle file named alone, then each library directory's
    bundles, those of its method tree and of the trees nested in it, as a local load reads them
    (`pipelex.libraries.method_trees`), so a file the membership rule keeps out, a `.gitignore`d or hidden one, is never
    sent; a library entry naming a `.mthds` file is taken alone, as the member of its tree; a missing one is skipped, as
    a local load skips it. Each file goes once, and is read as its tree's listing hashed it.

    Only the bundles are sent, keyed as `_tree_prefixes` places their trees: the method's own tree, `method_tree`'s, else
    the first one listed, by its own tree paths. A run names its pipe, so no manifest is needed to select it.

    Args:
        method_tree: The tree the run reads, as the run listed it: a bundle file's own, whose entry is sent first, or a
            method folder's, which the library directories hold. `None` for a run that names no bundle.
        library_dirs: The library directories a local run would load.

    Raises:
        HostedRunSourceError: If a tree cannot be listed, a file is not the one its listing hashed, or the bundles hold no
            one tree, which listed trees never give.
    """
    sent: list[_SentBundle] = []
    seen: set[Path] = set()
    for tree_bundle in _bundles_to_send(method_tree=method_tree, library_dirs=library_dirs):
        location = tree_bundle.location.resolve()
        if location in seen:
            continue
        seen.add(location)
        if tree_bundle.tree.directory is None or tree_bundle.tree_path is None:
            msg = f"The bundle '{location}' to send to the hosted API belongs to no tree listed from a directory."
            raise HostedRunSourceError(msg)
        try:
            data = read_tree_bundle_as_listed(tree_bundle=tree_bundle)
        except MethodTreeLoadError as exc:
            msg = f"Could not read the method file '{location}' to send it to the hosted API: {exc.message}"
            raise HostedRunSourceError(msg) from exc
        sent.append(_SentBundle(root=tree_bundle.tree.directory.resolve(), tree_path=tree_bundle.tree_path, data=data))
    if not sent:
        return {}
    # The method's own tree sets the root every other tree is placed from, the library directories holding it or not.
    anchor = method_tree.directory.resolve() if method_tree is not None and method_tree.directory is not None else sent[0].root
    prefixes = _tree_prefixes(sent=sent, anchor=anchor)
    contents = {f"{prefixes[one_bundle.root]}{one_bundle.tree_path}": one_bundle.data for one_bundle in sent}
    faulty_keys = [key for key in contents if tree_path_violation(key) is not None or excluded_name_violation(key)]
    faulty_keys.extend(path_collisions(contents))
    if len(contents) != len(sent) or faulty_keys:
        msg = f"The method's bundles hold no one tree to send to the hosted API: {', '.join(faulty_keys) or 'two bundles share a tree path'}."
        raise HostedRunSourceError(msg)
    return contents


def hosted_pipe_library_contents(*, library_dirs: Sequence[str] | None) -> dict[str, bytes]:
    """The library a hosted `run pipe` sends, as one tree's bundles by tree path: its library directories', else `PIPELEXPATH`'s.

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
    contents = method_tree_contents(method_tree=None, library_dirs=effective_dirs)
    if not contents:
        named = ", ".join(str(one_dir) for one_dir in effective_dirs)
        msg = f"No .mthds file found to send to the hosted API in {named}."
        raise HostedRunSourceError(msg)
    return contents


class HostedMethodTarget(BaseModel):
    """What a hosted `run method` sends, and where its outputs and inputs are anchored.

    Exactly one of `contents`, `method_ref` and `method_id` is set, as `HostedRunRequest` takes them.
    """

    model_config = ConfigDict(frozen=True)

    #: A local method's bundles, as one tree's bytes by tree path (`method_tree_contents`).
    contents: dict[str, bytes] | None = None
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
        label: str
        if pipe_override:
            label = run_output_label(pipe_ref=pipe_override)
        else:
            label = parse_method_ref(remote_ref).address.rsplit("/", 1)[-1] if remote_ref else name
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
    contents = method_tree_contents(method_tree=None, library_dirs=all_library_dirs)
    if not contents:
        msg = f"Method '{name}' at '{method.path}' holds no .mthds file to send to the hosted API."
        raise HostedRunSourceError(msg)
    return HostedMethodTarget(
        contents=contents,
        pipe_code=pipe_code,
        label=run_output_label(pipe_ref=pipe_code),
        output_base_dir=method_output_base_dir(method=method),
        inputs_anchor_dir=Path(method_library_dirs[0]),
    )
