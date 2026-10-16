"""Resolve a `method_ref` into a method tree: fetch, read from the commit's git objects, list, refuse.

The wire field `method_ref` carries a globally resolvable address —
`github.com/<owner>/<repo>[/<selector>][@<tag>]` — and THIS runner is its resolver (the
layered extension policy's Rule 3: an address needs no catalog, so it is a layer-2 concept;
the hosted-only `method_id` never reaches this server). The grammar, the fetch-at-tag, the
manifest-identity package location and the bounds all live in `pipelex.methods`; this module
composes them behind the SHA-keyed clone cache (`pipelex_api.method_cache`), so a package is
cached by its commit and a second request for the same commit fetches nothing.

The package is a method tree (`mthds/docs/spec/method-tree.md`): the files of the package's directory in the resolved
commit, read from the commit's git objects as stored, with no checkout filter, line-ending conversion or
`export-ignore`, so its digest is the same on every machine, and filtered by the membership rule read with that
commit's own `.gitignore` files and the package's own `exclude` patterns. A submodule contributes no file, and a
symbolic link committed in the package is refused unless the rule excludes it. The tree's digest is recorded in the
run's provenance (`method_provenance.tree_digest`), beside the commit.

The packages a package ships under its own `.mthds/methods/<name>/`, the layout of the local method cache, are out of
its tree (a dot directory), and each becomes a dependency tree of its own, keyed by the address its manifest declares,
as a dependency a request sends in `dependencies` is.

The routes use it two ways:

- The run routes and `/validate` use :func:`fetched_method`: the tree and its dependency trees, read in full, which the
  routes write out and load as a request's `files` are (`pipelex_api.method_tree_request`), so a fetched package and a
  sent method run the same path, the files a step reads, such as a `PipeDocGen` template, included.
- The tooling routes (`/resolve`, `/codegen`, `/pipe-io`) use :func:`fetch_method_mthds_files`: the tree's `.mthds`
  files, as `files[]` items labelled with their tree paths, paired with the manifest's `main_pipe` so the per-pipe route
  defaults its selector as a run does. No Python ever loads there, so the execution-locus gate does not apply.

The security gate (packaging invariant 7 — execution locus decides) is the request tree's
(`pipelex_api.method_tree_request.ensure_python_allowed`): on a deployment that is not sandbox-hosted, a package
carrying any `.py` is refused with a 403 `CustomCodeRequiresSandbox`; on a sandbox-hosted one, PipeFunc `.py` is
acceptable but a package declaring `StructuredContent` subclasses is refused (`MethodStructuresRefusedError` → 403).

Everything a run needs is read OUT of the cached clone before this module returns — the tree's bytes into memory — so
cache eviction can never race a running pipeline.
"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import NamedTuple

from mthds.method_tree.discovery import BUNDLE_SUFFIX
from pipelex import log
from pipelex.libraries.method_trees import list_package_method_tree
from pipelex.methods.exceptions import MethodFetchError
from pipelex.methods.fetching import FetchedMethodPackage, MethodProvenance
from pipelex.methods.method_ref import parse_method_ref

from pipelex_api.error_types import ErrorType
from pipelex_api.errors import raise_validation_error
from pipelex_api.limits import MAX_MTHDS_FILE_BYTES
from pipelex_api.method_cache import get_method_clone_cache
from pipelex_api.method_tree_request import (
    RequestMethod,
    RequestTree,
    add_dependency,
    dependency_address_of,
    ensure_tree_within_limits,
)
from pipelex_api.schemas.models import MthdsFileItem

GIT_TIMEOUT_SECONDS = 60
# The git modes of a tree entry this reader treats apart from a file: an executable file, a symbolic link, and a submodule's commit.
_GIT_MODE_EXECUTABLE = "100755"
_GIT_MODE_SYMLINK = "120000"
_GIT_MODE_SUBMODULE = "160000"
# Where a package ships the method packages it calls, the layout of the local method cache.
_VENDORED_METHODS_DIR = Path(".mthds") / "methods"


class FetchedMethod(NamedTuple):
    """A fetched package as a method: its tree with the dependency trees it ships, and what the run records."""

    request_method: RequestMethod
    package: FetchedMethodPackage
    provenance: MethodProvenance

    @property
    def label(self) -> str:
        """How messages name the package: its address, quoted."""
        return f"'{self.package.full_address}'"


class FetchedMthdsFiles(NamedTuple):
    """A fetched package shaped for the tooling path: its `.mthds` files plus the manifest's entry pipe."""

    files: list[MthdsFileItem]
    """The package's `.mthds` files as `files[]` items, each labelled with its tree path."""

    main_pipe: str | None
    """The manifest's declared `main_pipe` (a bare pipe code), or None when the manifest declares none."""


class _GitTreeEntry(NamedTuple):
    mode: str
    object_sha: str
    path: str


def _run_git(*, clone_dir: Path, args: list[str], stdin: bytes | None, package_address: str) -> bytes:
    """Run one git command on a cached clone, its output as bytes.

    Raises:
        MethodFetchError: git is not installed, the command fails, or it times out.
    """
    try:
        result = subprocess.run(  # noqa: S603 — fixed argv, no shell; every argument is ours or an object id git printed
            ["git", "-C", str(clone_dir), *args],  # noqa: S607
            input=stdin,
            capture_output=True,
            check=True,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as exc:
        msg = "git is not installed or not found on PATH"
        raise MethodFetchError(msg) from exc
    except subprocess.CalledProcessError as exc:
        msg = f"Could not read method package '{package_address}' from its commit: {exc.stderr.decode('utf-8', errors='replace').strip()}"
        raise MethodFetchError(msg) from exc
    except subprocess.TimeoutExpired as exc:
        msg = f"Timed out reading method package '{package_address}' from its commit"
        raise MethodFetchError(msg) from exc
    return result.stdout


def _package_tree_entries(*, package: FetchedMethodPackage) -> list[_GitTreeEntry]:
    """Every entry of the package's directory in the fetched commit, by its path relative to the package's directory.

    Raises:
        MethodFetchError: git cannot list the commit's tree, or a path in it is not UTF-8 text.
    """
    package_rel = package.package_dir.relative_to(package.clone_dir).as_posix()
    # The clone the cache keys by the resolved commit is checked out at that commit, so its HEAD is the commit.
    args = ["ls-tree", "-r", "-z", "--full-tree", "HEAD"]
    prefix = ""
    if package_rel != ".":
        args += ["--", f":(literal){package_rel}"]
        prefix = f"{package_rel}/"
    output = _run_git(clone_dir=package.clone_dir, args=args, stdin=None, package_address=package.full_address)
    entries: list[_GitTreeEntry] = []
    for record in output.split(b"\0"):
        if not record:
            continue
        header, _, raw_path = record.partition(b"\t")
        mode, _, rest = header.decode("ascii").partition(" ")
        _, _, object_sha = rest.partition(" ")
        try:
            path = raw_path.decode("utf-8")
        except UnicodeDecodeError as exc:
            msg = f"Method package '{package.full_address}' holds a file whose name is not UTF-8 text, which no method tree can hold."
            raise MethodFetchError(msg) from exc
        if not path.startswith(prefix):
            continue
        entries.append(_GitTreeEntry(mode=mode, object_sha=object_sha, path=path.removeprefix(prefix)))
    return entries


def _read_git_objects(*, package: FetchedMethodPackage, object_shas: list[str]) -> dict[str, bytes]:
    """The contents of these blobs of the clone, read in one `git cat-file --batch`, by object id.

    Raises:
        MethodFetchError: git cannot read an object, or its answer is not the one asked for.
    """
    if not object_shas:
        return {}
    unique_shas = sorted(set(object_shas))
    output = _run_git(
        clone_dir=package.clone_dir,
        args=["cat-file", "--batch"],
        stdin="".join(f"{object_sha}\n" for object_sha in unique_shas).encode("ascii"),
        package_address=package.full_address,
    )
    contents: dict[str, bytes] = {}
    cursor = 0
    for object_sha in unique_shas:
        line_end = output.index(b"\n", cursor)
        header = output[cursor:line_end].decode("ascii").split(" ")
        if len(header) != 3 or header[0] != object_sha:
            msg = f"Could not read the object {object_sha} of method package '{package.full_address}' from its commit."
            raise MethodFetchError(msg)
        size = int(header[2])
        start = line_end + 1
        contents[object_sha] = output[start : start + size]
        cursor = start + size + 1
    return contents


def _stage_package(*, package: FetchedMethodPackage, staging_dir: Path) -> None:
    """Write the package's directory as its commit stores it into `staging_dir`, from the clone's git objects.

    A symbolic link is written as one, for the tree's lister to refuse unless the membership rule excludes it, and a
    submodule contributes no file.
    """
    entries = _package_tree_entries(package=package)
    blobs = _read_git_objects(package=package, object_shas=[entry.object_sha for entry in entries if entry.mode != _GIT_MODE_SUBMODULE])
    for entry in entries:
        if entry.mode == _GIT_MODE_SUBMODULE:
            continue
        target = staging_dir.joinpath(*entry.path.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        data = blobs[entry.object_sha]
        if entry.mode == _GIT_MODE_SYMLINK:
            target.symlink_to(os.fsdecode(data))
            continue
        target.write_bytes(data)
        if entry.mode == _GIT_MODE_EXECUTABLE:
            target.chmod(0o755)


def _read_listed_tree(*, root: Path, package_address: str, label: str) -> RequestTree:
    """List a staged package directory as a method tree and read every file of it into memory.

    Raises:
        MethodTreeLoadError: The standard refused the tree, it passed a limit, or it could not be read.
    """
    tree = list_package_method_tree(root=root, package_address=package_address)
    contents = {tree_path: tree.file_location(tree_path).read_bytes() for tree_path in tree.tree_paths}
    request_tree = RequestTree.make_from_contents(contents=contents)
    ensure_tree_within_limits(tree=request_tree, label=label)
    return request_tree


def _read_package_method(*, package: FetchedMethodPackage) -> RequestMethod:
    """The package's tree and the dependency trees it ships, read from the commit's git objects."""
    staging_dir = Path(tempfile.mkdtemp(prefix="pipelex-package-"))
    try:
        package_root = staging_dir / "package"
        package_root.mkdir()
        _stage_package(package=package, staging_dir=package_root)
        label = f"Method package '{package.full_address}'"
        tree = _read_listed_tree(root=package_root, package_address=package.full_address, label=label)
        dependencies: dict[str, RequestTree] = {}
        vendored_root = package_root / _VENDORED_METHODS_DIR
        if vendored_root.is_dir():
            for vendored_dir in sorted(vendored_root.iterdir()):
                if not vendored_dir.is_dir() or vendored_dir.is_symlink():
                    continue
                vendored_label = f"The package '.mthds/methods/{vendored_dir.name}/' of method package '{package.full_address}'"
                dependency_tree = _read_listed_tree(root=vendored_dir, package_address=vendored_label, label=vendored_label)
                address = dependency_address_of(tree=dependency_tree, fallback_name=vendored_dir.name, label=vendored_label)
                add_dependency(dependencies=dependencies, address=address, tree=dependency_tree, label=vendored_label)
        return RequestMethod(tree=tree, dependencies=dependencies)
    finally:
        shutil.rmtree(staging_dir, ignore_errors=True)


def _fetch_package(method_ref: str) -> FetchedMethodPackage:
    """Parse the reference and fetch its package through the SHA-keyed clone cache.

    Every failure mode is a distinct pipelex `MethodRefError` subclass, rendered by the
    global handler as RFC 7807 `problem+json` with the class name as `error_type` and the
    status the API maps for it (`pipelex_api.exception_handlers._ERROR_TYPE_STATUS_OVERRIDES`).
    """
    ref = parse_method_ref(method_ref)
    package = get_method_clone_cache().get_or_fetch(ref=ref)
    # The tag and the commit say which version of the package a hosted run executed; the tag is `None` when the
    # reference named none and the default branch was fetched.
    log.info(
        "A method reference was resolved to a package",
        fields={
            "method_ref": ref.ref_str,
            "package_address": package.provenance.address,
            "fetched_tag": package.provenance.tag,
            "commit_sha": package.provenance.commit_sha,
        },
    )
    return package


def fetched_method(method_ref: str) -> FetchedMethod:
    """Fetch a `method_ref`'s package and read it as a method tree, with the dependency trees it ships.

    Args:
        method_ref: The raw `method_ref` string from the request.

    Raises:
        MethodRefError subclasses: parse, fetch, location and bounds failures, each rendered as `problem+json` by the
            global handler.
        MethodTreeLoadError: The standard refused the package's tree (a 422 naming the package by its address).
        ApiError: A tree past this runner's limits, or a shipped package without a manifest (422s).
    """
    package = _fetch_package(method_ref)
    request_method = _read_package_method(package=package)
    provenance = package.provenance.model_copy(update={"tree_digest": request_method.tree.tree.digest})
    return FetchedMethod(request_method=request_method, package=package, provenance=provenance)


def fetch_method_mthds_files(method_ref: str) -> FetchedMthdsFiles:
    """Fetch a `method_ref`'s package and return its tree's `.mthds` files as `files[]` items, plus its `main_pipe`.

    The tooling-route shape: each item pairs the file's content with its tree path as `source`, so crate provenance and
    diagnostics carry true per-file labels. Only the package's own `.mthds` files travel, never those of a package it
    ships under its `.mthds/methods/`, since these routes resolve no address-based dependency. The manifest's `main_pipe`
    rides beside the files so a per-pipe projection can default its selector the way a run does.

    Args:
        method_ref: The raw `method_ref` string from the request.

    Raises:
        MethodRefError subclasses: parse, fetch, location, and bounds failures.
        MethodTreeLoadError: The standard refused the package's tree.
        ApiError: 422 for a package with no `.mthds` file or one this server cannot accept.
    """
    fetched = fetched_method(method_ref)
    tree = fetched.request_method.tree
    items: list[MthdsFileItem] = []
    for tree_path in tree.bundle_paths:
        data = tree.contents[tree_path]
        try:
            content = data.decode("utf-8")
        except UnicodeDecodeError:
            raise_validation_error(message=f"File '{tree_path}' in method package {fetched.label} is not valid UTF-8.")
        if len(data) > MAX_MTHDS_FILE_BYTES:
            msg = f"File '{tree_path}' in method package {fetched.label} exceeds the {MAX_MTHDS_FILE_BYTES // 1024} KiB per-file limit."
            raise_validation_error(message=msg)
        items.append(MthdsFileItem(content=content, source=tree_path))
    if not items:
        raise_validation_error(message=f"Method package {fetched.label} contains no {BUNDLE_SUFFIX} file.", error_type=ErrorType.INVALID_BUNDLE)
    return FetchedMthdsFiles(files=items, main_pipe=fetched.package.manifest.main_pipe)
