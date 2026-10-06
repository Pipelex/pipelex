"""Resolve a `method_ref` into run/validate/tooling inputs: fetch → locate → refuse → materialize.

The wire field `method_ref` carries a globally resolvable address —
`github.com/<owner>/<repo>[/<selector>][@<tag>]` — and THIS runner is its resolver (the
layered extension policy's Rule 3: an address needs no catalog, so it is a layer-2 concept;
the hosted-only `method_id` never reaches this server). The grammar, the fetch-at-tag, the
manifest-identity package location, the bounds, and the structures check all live in
`pipelex.methods`; this module composes them behind the SHA-keyed clone cache
(`pipelex_api.method_cache`) and shapes the result for each route family:

- The run routes and `/validate` use :func:`fetched_method_source`: the package's `.mthds`
  files travel as `mthds_contents` (paired with their real relative paths as
  `mthds_sources`, so diagnostics carry true per-file labels), and only the non-`.mthds`
  files are materialized into a temporary `library_dirs` entry — exactly the split the
  method-bundle transport uses, so a fetched package runs the same proven path. The
  packages it ships under its own `.mthds/methods/<name>/` are partitioned out of both, as
  a bundle's are, into a temporary `methods_dirs` entry: the run routes hand it to the
  engine, and `/validate` does not, resolving such a dependency through the installed store
  or fetch-on-miss.
- The tooling routes (`/resolve`, `/codegen`, `/pipe-io`) use
  :func:`fetch_method_mthds_files`: only the package's own `.mthds` files, as `files[]` items,
  paired with the manifest's `main_pipe` so the per-pipe route defaults its selector exactly
  as a run does. No Python ever loads there, so the execution-locus gate does not apply.

The security gate (packaging invariant 7 — execution locus decides): `.mthds` content is
data, always acceptable. On a deployment that is NOT sandbox-hosted, a fetched package
carrying ANY `.py` is refused with the same 403 the bundle transport uses
(`CustomCodeRequiresSandbox`) — running it would import customer code in-process. On a
sandbox-hosted deployment, PipeFunc `.py` is acceptable (captured as text, executed in the
network-blocked sandbox) but a package declaring `StructuredContent` subclasses is refused
loudly (`MethodStructuresRefusedError` → 403): structure classes would have to be imported into
the runner's own process, and the rule-naming error teaches authors to express types as MTHDS
concepts. The library load refuses the same classes again, for a bundle as for a package.

Everything a run needs is copied OUT of the cached clone before this module yields — the
`.mthds` text into memory, the rest into a per-request temp directory — so cache eviction
can never race a running pipeline.
"""

from collections.abc import Generator
from contextlib import ExitStack, contextmanager
from pathlib import Path, PurePosixPath
from typing import NamedTuple, NoReturn

from mthds.package.discovery import MANIFEST_FILENAME
from pipelex import log
from pipelex.config import is_pipe_func_sandbox_hosted
from pipelex.methods.fetching import FetchedMethodPackage, MethodProvenance
from pipelex.methods.method_ref import parse_method_ref
from pipelex.methods.structures_check import ensure_no_structured_content_python
from pydantic import BaseModel, ConfigDict, Field

from pipelex_api.bundle import BundlePartition, ParsedBundle, materialize_parsed, materialized_methods_dir, partition_bundle_entries
from pipelex_api.error_types import ErrorType
from pipelex_api.errors import raise_forbidden, raise_validation_error
from pipelex_api.limits import MAX_MTHDS_FILE_BYTES
from pipelex_api.method_cache import get_method_clone_cache
from pipelex_api.schemas.models import MthdsFileItem

_SKIPPED_DIR_NAMES = {".git", "__pycache__"}


class FetchedMethodSource(BaseModel):
    """A fetched package shaped for the run/validate path (see the module docstring)."""

    model_config = ConfigDict(frozen=True)

    mthds_contents: list[str]
    mthds_sources: list[str]
    library_dirs: list[str] | None = None
    methods_dirs: list[Path] | None = Field(
        default=None, description="The methods directory holding the packages the package ships under its own `.mthds/methods/`."
    )
    main_pipe: str | None = Field(default=None, description="The manifest's declared entry pipe; a request `pipe_code` overrides it.")
    provenance: MethodProvenance


class FetchedMthdsFiles(NamedTuple):
    """A fetched package shaped for the tooling path: its `.mthds` files plus the manifest's entry pipe."""

    files: list[MthdsFileItem]
    """The package's `.mthds` files as `files[]` items, each labelled with its real relative path."""

    main_pipe: str | None
    """The manifest's declared `main_pipe` (a bare pipe code), or None when the manifest declares none."""


def _fetch_package(method_ref: str) -> FetchedMethodPackage:
    """Parse the reference and fetch its package through the SHA-keyed clone cache.

    Every failure mode is a distinct pipelex `MethodRefError` subclass, rendered by the
    global handler as RFC 7807 `problem+json` with the class name as `error_type` and the
    status the API maps for it (`pipelex_api.exception_handlers._ERROR_TYPE_STATUS_OVERRIDES`).
    """
    ref = parse_method_ref(method_ref)
    package = get_method_clone_cache().get_or_fetch(ref=ref)
    log.info(
        f"Resolved method_ref '{ref.ref_str}': address={package.provenance.address} "
        f"tag={package.provenance.tag} commit_sha={package.provenance.commit_sha}"
    )
    return package


def _package_files(package: FetchedMethodPackage) -> list[Path]:
    """The package's files, deterministically ordered, with VCS/tooling residue skipped."""
    files: list[Path] = []
    for file_path in sorted(package.package_dir.rglob("*")):
        relative_parts = file_path.relative_to(package.package_dir).parts
        if any(part in _SKIPPED_DIR_NAMES for part in relative_parts):
            continue
        if file_path.is_file():
            files.append(file_path)
    return files


def _decode_mthds_text(data: bytes, *, relative: str, package_address: str) -> str:
    try:
        content = data.decode("utf-8")
    except UnicodeDecodeError:
        raise_validation_error(message=f"File '{relative}' in method package '{package_address}' is not valid UTF-8.")
    if len(data) > MAX_MTHDS_FILE_BYTES:
        msg = f"File '{relative}' in method package '{package_address}' exceeds the {MAX_MTHDS_FILE_BYTES // 1024} KiB per-file limit."
        raise_validation_error(message=msg)
    return content


def _partition_package(package: FetchedMethodPackage, *, files: list[Path]) -> BundlePartition:
    """Sort a fetched package's files as a bundle's are: its own `.mthds`, its other files, and the packages it ships.

    The refusals are a bundle's too: a `.mthds` path no reference could find is a `422` naming the file.
    """
    entries = tuple((PurePosixPath(file_path.relative_to(package.package_dir).as_posix()), file_path.read_bytes()) for file_path in files)
    return partition_bundle_entries(entries, owner=f"Method package '{package.full_address}'")


def _refuse_no_own_mthds(package: FetchedMethodPackage, *, partition: BundlePartition) -> NoReturn:
    msg = f"Method package '{package.full_address}' contains no .mthds file."
    if partition.vendored_packages:
        msg = (
            f"Method package '{package.full_address}' contains no .mthds file of its own: "
            "the files under '.mthds/methods/' are the packages it ships."
        )
    raise_validation_error(message=msg)


def _apply_execution_locus_gate(package: FetchedMethodPackage, *, python_relpaths: list[str]) -> None:
    """Refuse Python that would execute where it must not (see the module docstring)."""
    if not python_relpaths:
        return
    if not is_pipe_func_sandbox_hosted():
        msg = f"Method package '{package.full_address}' ships custom Python (.py); running it requires a sandbox-hosted deployment."
        raise_forbidden(message=msg, error_type=ErrorType.CUSTOM_CODE_REQUIRES_SANDBOX)
    ensure_no_structured_content_python(package_dir=package.package_dir, package_address=package.full_address)


@contextmanager
def fetched_method_source(method_ref: str) -> Generator[FetchedMethodSource, None, None]:
    """Fetch a `method_ref`'s package and shape it for the run/validate path.

    Yields the package's `.mthds` files as `(mthds_contents, mthds_sources)` pairs, its
    non-`.mthds` files (PipeFunc `.py`, `requirements.txt`, …) materialized into a temporary
    `library_dirs` entry, and the packages it ships under its own `.mthds/methods/<name>/`
    materialized into a temporary `methods_dirs` entry, each cleaned up on exit. The
    execution-locus gate runs before anything touches disk.

    Args:
        method_ref: The raw `method_ref` string from the request.

    Raises:
        MethodRefError subclasses: parse, fetch, location, bounds, and structures failures —
            each rendered as `problem+json` by the global handler.
        ApiError: the 403 custom-code gate on a non-sandbox deployment, and 422s for a
            package whose `.mthds` content this server cannot accept.
    """
    package = _fetch_package(method_ref)
    files = _package_files(package)
    python_relpaths = [file_path.relative_to(package.package_dir).as_posix() for file_path in files if file_path.suffix == ".py"]
    # The whole package, the packages it ships included, so a structure class anywhere in it is refused before anything is copied.
    _apply_execution_locus_gate(package, python_relpaths=python_relpaths)

    partition = _partition_package(package, files=files)
    mthds_contents: list[str] = []
    mthds_sources: list[str] = []
    for relpath, data in partition.mthds_entries:
        relative = relpath.as_posix()
        mthds_contents.append(_decode_mthds_text(data, relative=relative, package_address=package.full_address))
        mthds_sources.append(relative)
    if not mthds_contents:
        _refuse_no_own_mthds(package, partition=partition)
    # The manifest is already consumed (identity + `main_pipe`); materializing it into the library dir would hand the
    # local loader a package boundary it must not see.
    other_entries = tuple((relpath, data) for relpath, data in partition.library_entries if relpath.name != MANIFEST_FILENAME)

    with ExitStack() as stack:
        library_dirs: list[str] | None = None
        if other_entries:
            library_bundle = stack.enter_context(materialize_parsed(ParsedBundle(entries=other_entries)))
            library_dirs = [str(library_bundle.directory)]
        methods_dirs: list[Path] | None = None
        if partition.vendored_packages:
            methods_dirs = [stack.enter_context(materialized_methods_dir(partition.vendored_packages))]
        yield FetchedMethodSource(
            mthds_contents=mthds_contents,
            mthds_sources=mthds_sources,
            library_dirs=library_dirs,
            methods_dirs=methods_dirs,
            main_pipe=package.manifest.main_pipe,
            provenance=package.provenance,
        )


def fetch_method_mthds_files(method_ref: str) -> FetchedMthdsFiles:
    """Fetch a `method_ref`'s package and return its `.mthds` files as `files[]` items, plus its `main_pipe`.

    The tooling-route shape: each item pairs the file's content with its real relative path
    as `source`, so crate provenance and diagnostics carry true per-file labels. Only the
    package's own `.mthds` data travels, never that of a package it ships under its
    `.mthds/methods/`, since these routes resolve no address-based dependency. The package's
    Python (if any) never loads on these routes, so the execution-locus gate does not apply here. The manifest's `main_pipe` rides beside the
    files so a per-pipe projection can default its selector the way a run does — the manifest
    is the package author's declaration of the entry pipe, and dropping it here would make
    `main_pipe` buy them nothing on the tooling routes.

    Args:
        method_ref: The raw `method_ref` string from the request.

    Raises:
        MethodRefError subclasses: parse, fetch, location, and bounds failures.
        ApiError: 422 for a package with no `.mthds` file or one this server cannot accept.
    """
    package = _fetch_package(method_ref)
    partition = _partition_package(package, files=_package_files(package))
    items: list[MthdsFileItem] = []
    for relpath, data in partition.mthds_entries:
        relative = relpath.as_posix()
        content = _decode_mthds_text(data, relative=relative, package_address=package.full_address)
        items.append(MthdsFileItem(content=content, source=relative))
    if not items:
        _refuse_no_own_mthds(package, partition=partition)
    return FetchedMthdsFiles(files=items, main_pipe=package.manifest.main_pipe)
