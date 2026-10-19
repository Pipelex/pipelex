"""A method a request carries as a tree: reading its map of file entries, and writing it out to load it.

A run or validate request names its method by a map of file entries, `files`: each key a tree path, each value the
file's text, its bytes in Base64 (`{"base64": …}`) or the hash of bytes this runner already holds (`{"sha256": …,
"size": …}`), as the MTHDS standard writes a tree that travels (`mthds/docs/spec/method-tree.md`, "The File Entry").
The map is the tree: the runner reads it with the standard's own reader, from the JSON text the request carried, since a
key given twice and a `size` written `13.0` are only visible there, and never applies the membership rule to it again.
A dependency the runner cannot fetch travels beside it in `dependencies`, a tree of its own keyed by its address. A
`bundle_b64` archive is read the same way, its entries made a map, so every form a method travels in is judged by the
one rule of the tree: a key that is not a tree path, or that names a file the membership rule keeps out of every tree,
is refused whatever form carried it.

What this module does, in order:

1. Every limit of this runner on a tree (`MAX_METHOD_TREE_FILES`, `MAX_METHOD_TREE_TOTAL_KIB`,
   `MAX_METHOD_TREE_FILE_KIB`) is checked on the sizes the entries state, before any blob is read: a 422
   `method.package_invalid` whose `reason` names the limit and whose `limit` gives it.
2. The bytes of every hash entry are read from the runner's blob store, under the caller's scope, at once.
3. The map is read (`read_file_map`): a refusal of the standard is a 422 `method.package_invalid` whose `reason` is the
   refusal's code and whose `path` is the first path it names, except a key leaving the tree, which is the security
   refusal `security.input_path_refused`, and an entry of the wrong shape, which is `request.invalid`; hash entries the
   store does not hold at their stated size are one 422 `request.blobs_missing` whose `missing_blobs` parameter lists
   every such hash.
4. The files `resources` sends join the tree (`with_resources`), the same bytes under a path the tree holds or a new
   file at a tree path; other bytes under a path the tree holds are a 422 `request.invalid` naming `resources`.
5. Python is honored only on a sandbox-hosted deployment: a method holding a `.py` file is refused with a 501
   `pipelex.deployment.custom_code_requires_sandbox` before anything is written, and on a sandbox-hosted deployment a
   tree declaring a Python structure class is refused (`MethodStructuresRefusedError`, a 422).
6. Each tree read in full is recorded in the blob store, its files then its listing, so the next request can send it
   by hash, and `POST /v1/blobs/missing` answers its digest with one lookup.
7. The trees are written out into a temporary directory and held as written (`pipelex.libraries.written_trees`), so
   the load reads them back as written and names their files by their tree paths, then removed when the request ends.
"""

import base64
import json
import shutil
import tempfile
from collections.abc import Generator, Mapping
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import Any, NamedTuple, NoReturn, cast

from mthds.method_tree.digest import is_sha256_hex, tree_digest, tree_files_from_contents
from mthds.method_tree.discovery import BUNDLE_SUFFIX, MANIFEST_NAME
from mthds.method_tree.exceptions import MethodTreeRefusedError, TreeSourceError
from mthds.method_tree.file_entry import BASE64_KEY, SHA256_KEY, SIZE_KEY, BlobStore, InMemoryBlobStore, excluded_name_violation, read_file_map
from mthds.method_tree.models import MethodTree
from mthds.method_tree.tree_path import path_collisions, tree_path_violation
from mthds.method_tree.vocabulary import TreeRefusalCode
from mthds.package.exceptions import ManifestError
from mthds.package.manifest.parser import parse_methods_toml
from mthds.package.manifest.schema import MethodsManifest
from mthds.protocol.problem.registry import CoreCode, MethodResourceMissingReason, RequestMalformedReason
from pipelex.cli.installed_methods import PROVENANCE_FILENAME
from pipelex.config import is_pipe_func_sandbox_hosted
from pipelex.core.bundle_resources.bundle_resource import SUBMITTED_FILES_FIELD, root_escape_of
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode
from pipelex.libraries.written_trees import WRITTEN_METHOD_TREES, write_method_tree
from pipelex.methods.package_reason import MethodPackageReason
from pipelex.methods.structures_check import ensure_no_structured_content_in_library_sources, ensure_no_structured_content_python
from pipelex.mthds_parsing.parser import MthdsParser
from pipelex.pipeline.exceptions import MethodEntryError
from pipelex.pipeline.method_entry import EntryCandidate, MethodEntry, select_entry
from pipelex.pipeline.validate_bundle_translation import translate_to_validate_bundle_error

from pipelex_api.blob_store import RunnerBlobStore
from pipelex_api.bundle import decode_bundle_archive
from pipelex_api.bundle_resources import refuse_two_files_under_one_path
from pipelex_api.exceptions import CustomCodeOrigin, CustomCodeRequiresSandboxError, RequestMethodError, RunnerRequestError
from pipelex_api.limits import (
    MAX_METHOD_DEPENDENCIES,
    MAX_METHOD_REQUEST_TOTAL_BYTES,
    MAX_METHOD_TREE_FILE_BYTES,
    MAX_METHOD_TREE_FILES,
    MAX_METHOD_TREE_TOTAL_BYTES,
)

FILES_FIELD = "files"
DEPENDENCIES_FIELD = "dependencies"
BUNDLE_FIELD = "bundle_b64"
PYTHON_SUFFIX = ".py"
FILES_LABEL = "The `files` map"
ARCHIVE_LABEL = "The `bundle_b64` archive"
_METHOD_LABEL = "The method sent in `files`"
_WITH_RESOURCES_LABEL = "The method's tree with the files sent in `resources`"
# How a request's method is named in the messages of the entry rule: "The method sent in `files` holds no …".
REQUEST_METHOD_LABEL = "sent in the request"
# Where a `bundle_b64` archive ships the method packages it calls, the layout of the local method cache.
VENDORED_METHODS_PREFIX = ".mthds/methods/"
# A file the membership rule judges a directory by, which stands in for any file inside a directory being judged.
_ANY_FILE_NAME = "file"
# The `finding` of a `method.syntax` refusing a bundle that is not text.
NOT_UTF8_FINDING = "the bundle is not UTF-8 text"


class RequestTree(NamedTuple):
    """A method tree read in full: the tree, and each file's bytes by its tree path."""

    tree: MethodTree
    contents: dict[str, bytes]

    @property
    def has_python(self) -> bool:
        return any(tree_path.endswith(PYTHON_SUFFIX) for tree_path in self.contents)

    @property
    def bundle_paths(self) -> list[str]:
        return [tree_path for tree_path in self.tree.tree_paths if tree_path.endswith(BUNDLE_SUFFIX)]

    @property
    def bundle_texts(self) -> dict[str, str]:
        """The text of each `.mthds` bundle of the tree by its tree path, in tree path order, as a valid verdict echoes them.

        Decoded strictly, so it is read only once the bundles loaded: a bundle that is not UTF-8 never loads.

        Raises:
            UnicodeDecodeError: A bundle is not UTF-8 text, which a tree that loaded never holds.
        """
        return {tree_path: self.contents[tree_path].decode("utf-8") for tree_path in self.bundle_paths}

    @classmethod
    def make_from_contents(cls, *, contents: dict[str, bytes]) -> "RequestTree":
        """The tree these files make, each at its tree path, already judged as a tree's files."""
        files = tree_files_from_contents(contents)
        return cls(tree=MethodTree(files=files, digest=tree_digest(files)), contents=contents)


class RequestMethod(NamedTuple):
    """A method as trees: its own, and the dependency trees it carries, keyed by their addresses."""

    tree: RequestTree
    dependencies: dict[str, RequestTree]

    @property
    def has_python(self) -> bool:
        return self.tree.has_python or any(dependency.has_python for dependency in self.dependencies.values())


class TreeDocuments(NamedTuple):
    """The `files` and `dependencies` members of a request body, each map as the JSON text a receiver reads it from."""

    files: str | None
    dependencies: dict[str, str] | None


class _JsonObject(NamedTuple):
    """A JSON object as the pairs it was written with, in document order, a key given twice included."""

    pairs: list[tuple[str, Any]]


class _JsonConstant(NamedTuple):
    """`NaN`, `Infinity` or `-Infinity`, which `json.loads` accepts and JSON does not hold, kept as it was written.

    The body's other members are the rest of the server's to judge, so a constant is refused here only inside a map of
    file entries, where it reaches the standard's reader as it was written, and that reader refuses it.
    """

    text: str


def _parse_keeping_pairs(text: str) -> Any:
    return json.loads(text, object_pairs_hook=_JsonObject, parse_constant=_JsonConstant)


def _serialized(value: Any) -> str:
    """The JSON text of a value parsed keeping its pairs, written back as it was parsed.

    A key given twice stays twice, and a number keeps its form: an integer stays an integer, and a number written with a
    fraction or an exponent comes back as a float, which the standard's reader refuses as a `size`. A string is written
    with JSON's escapes, so a lone surrogate reaches the reader as the escape it was. The body's nesting was bounded
    before it was parsed (`pipelex_api.json_body`), which bounds this recursion.
    """
    if isinstance(value, _JsonObject):
        members = ",".join(f"{json.dumps(key)}:{_serialized(member)}" for key, member in value.pairs)
        return f"{{{members}}}"
    if isinstance(value, _JsonConstant):
        return value.text
    if isinstance(value, list):
        return f"[{','.join(_serialized(item) for item in cast('list[Any]', value))}]"
    return json.dumps(value)


def tree_documents_of(*, body: bytes) -> TreeDocuments:
    """The `files` and `dependencies` members of a request body, each map as JSON text, or None where a member is absent.

    The body was already parsed and checked as JSON (`pipelex_api.json_body`); it is parsed again here keeping every
    object's pairs, since a receiver reads a map from its text, so a route calls this only for a body that sends a
    tree. It is decoded as `json.loads` decodes bytes, UTF-8, UTF-16 or UTF-32, as the route's own parser accepted it.
    A member given twice in the body is read as JSON reads it, the last one counting, and a `null` member is absent.

    Raises (as problem documents): a 422 `request.malformed` for a body that does not decode or parse, and a 422
    `request.invalid` naming `dependencies` when it is not an object, or gives one address twice.
    """
    try:
        parsed = _parse_keeping_pairs(body.decode(json.detect_encoding(body), "surrogatepass"))
    except (UnicodeDecodeError, ValueError) as exc:
        # The route's parser read these bytes already, so this is a second line of defence: `JSONDecodeError` and
        # an integer longer than Python converts are both a `ValueError`.
        msg = f"Request body is not valid JSON: {exc!s}"
        raise RunnerRequestError(msg).with_error_code(CoreCode.REQUEST_MALFORMED).with_params(reason=RequestMalformedReason.NOT_JSON) from exc
    if not isinstance(parsed, _JsonObject):
        return TreeDocuments(files=None, dependencies=None)
    members = dict(parsed.pairs)
    files_member = members.get(FILES_FIELD)
    files_document = _serialized(files_member) if files_member is not None else None
    dependencies_member = members.get(DEPENDENCIES_FIELD)
    if dependencies_member is None:
        return TreeDocuments(files=files_document, dependencies=None)
    if not isinstance(dependencies_member, _JsonObject):
        msg = "`dependencies` must be a JSON object mapping each dependency's address to its map of file entries."
        raise RunnerRequestError(msg, field=DEPENDENCIES_FIELD)
    dependency_documents: dict[str, str] = {}
    for address, dependency_member in dependencies_member.pairs:
        if address in dependency_documents:
            msg = f"`dependencies` gives the address '{wire_name(address)}' twice."
            raise RunnerRequestError(msg, field=DEPENDENCIES_FIELD)
        dependency_documents[address] = _serialized(dependency_member)
    return TreeDocuments(files=files_document, dependencies=dependency_documents)


class _MapCensus(NamedTuple):
    """What a map's entries state before any is read: how many files, how many bytes, and which hashes at which sizes."""

    file_count: int
    stated_bytes: int
    largest_path: str | None
    largest_bytes: int
    stated_sizes: dict[str, set[int]]


def _stated_size(entry: Any) -> tuple[int, str | None]:
    """The size an entry states, and the hash it names when it is a hash entry; zero for an entry the reader will refuse."""
    if isinstance(entry, str):
        return len(entry.encode("utf-8", errors="surrogatepass")), None
    if not isinstance(entry, _JsonObject):
        return 0, None
    fields = dict(entry.pairs)
    encoded = fields.get(BASE64_KEY)
    if isinstance(encoded, str) and len(fields) == 1:
        # The decoded length of well-formed Base64, its padding taken off; the reader refuses any other value.
        return len(encoded) * 3 // 4 - encoded[-2:].count("="), None
    sha256 = fields.get(SHA256_KEY)
    size = fields.get(SIZE_KEY)
    if isinstance(sha256, str) and is_sha256_hex(sha256) and isinstance(size, int) and not isinstance(size, bool) and size >= 0:
        return size, sha256
    return 0, None


def _census(*, document: str) -> _MapCensus | None:
    """The census of a map of file entries, or None when the document holds no JSON object, for the reader to refuse."""
    try:
        parsed = _parse_keeping_pairs(document)
    except (ValueError, RecursionError):
        return None
    if not isinstance(parsed, _JsonObject):
        return None
    stated_bytes = 0
    largest_path: str | None = None
    largest_bytes = 0
    stated_sizes: dict[str, set[int]] = {}
    for tree_path, entry in parsed.pairs:
        size, sha256 = _stated_size(entry)
        stated_bytes += size
        if size > largest_bytes:
            largest_path, largest_bytes = tree_path, size
        if sha256 is not None:
            stated_sizes.setdefault(sha256, set()).add(size)
    return _MapCensus(
        file_count=len(parsed.pairs),
        stated_bytes=stated_bytes,
        largest_path=largest_path,
        largest_bytes=largest_bytes,
        stated_sizes=stated_sizes,
    )


def wire_name(name: str) -> str:
    """A name a refusal reports, as JSON can carry it: a code point UTF-8 cannot encode, a lone surrogate, as its escape."""
    return name.encode("utf-8", errors="backslashreplace").decode("utf-8")


def ensure_within_tree_limits(*, file_count: int, total_bytes: int, largest_path: str | None, largest_bytes: int, label: str) -> None:
    """Refuse a tree past one of this runner's limits with a 422 `method.package_invalid`, its `reason` naming the limit."""
    if file_count > MAX_METHOD_TREE_FILES:
        msg = f"{label} holds {file_count} files, past this runner's limit of {MAX_METHOD_TREE_FILES} files in a method tree."
        raise RequestMethodError(msg).with_params(reason=MethodPackageReason.TOO_MANY_FILES, limit=MAX_METHOD_TREE_FILES)
    if largest_path is not None and largest_bytes > MAX_METHOD_TREE_FILE_BYTES:
        msg = (
            f"{label} holds the file '{wire_name(largest_path)}' of {largest_bytes} bytes, past this runner's limit of "
            f"{MAX_METHOD_TREE_FILE_BYTES // 1024} KiB for one file of a method tree."
        )
        raise RequestMethodError(msg, file=wire_name(largest_path)).with_params(
            reason=MethodPackageReason.FILE_TOO_LARGE, path=wire_name(largest_path), limit=MAX_METHOD_TREE_FILE_BYTES
        )
    if total_bytes > MAX_METHOD_TREE_TOTAL_BYTES:
        msg = f"{label} holds {total_bytes} bytes, past this runner's limit of {MAX_METHOD_TREE_TOTAL_BYTES // 1024} KiB for a method tree."
        raise RequestMethodError(msg).with_params(reason=MethodPackageReason.TREE_TOO_LARGE, limit=MAX_METHOD_TREE_TOTAL_BYTES)


def ensure_tree_within_limits(*, tree: RequestTree, label: str) -> None:
    """Refuse a tree read in full that passes one of this runner's limits, with a 422 `method.package_invalid`."""
    largest_path: str | None = None
    largest_bytes = 0
    for tree_path, data in tree.contents.items():
        if len(data) > largest_bytes:
            largest_path, largest_bytes = tree_path, len(data)
    ensure_within_tree_limits(
        file_count=len(tree.contents),
        total_bytes=sum(len(data) for data in tree.contents.values()),
        largest_path=largest_path,
        largest_bytes=largest_bytes,
        label=label,
    )


def ensure_trees_within_request_limits(*, dependency_count: int, total_bytes: int, label: str) -> None:
    """Refuse a method whose trees together pass this runner's limits, with a 422 `method.package_invalid`.

    Each tree is held to the tree limits on its own; these bound what one request carries in all, its method's tree and
    every dependency tree beside it, so the memory and the disk a request takes do not grow with its dependencies.
    """
    if dependency_count > MAX_METHOD_DEPENDENCIES:
        msg = f"{label} carries {dependency_count} dependencies, past this runner's limit of {MAX_METHOD_DEPENDENCIES} dependency trees."
        raise RequestMethodError(msg).with_params(reason=MethodPackageReason.TOO_MANY_DEPENDENCIES, limit=MAX_METHOD_DEPENDENCIES)
    if total_bytes > MAX_METHOD_REQUEST_TOTAL_BYTES:
        msg = (
            f"{label} holds {total_bytes} bytes across its tree and its dependency trees, past this runner's limit of "
            f"{MAX_METHOD_REQUEST_TOTAL_BYTES // 1024} KiB for a method and its dependencies."
        )
        raise RequestMethodError(msg).with_params(reason=MethodPackageReason.METHOD_TOO_LARGE, limit=MAX_METHOD_REQUEST_TOTAL_BYTES)


def ensure_method_within_limits(*, request_method: "RequestMethod", label: str) -> None:
    """Refuse a method read in full whose trees together pass this runner's limits, with a 422 `method.package_invalid`."""
    trees = [request_method.tree, *request_method.dependencies.values()]
    ensure_trees_within_request_limits(
        dependency_count=len(request_method.dependencies),
        total_bytes=sum(len(data) for tree in trees for data in tree.contents.values()),
        label=label,
    )


def _refuse_map(*, refusal_error: MethodTreeRefusedError, label: str, field: str) -> NoReturn:
    """Answer the standard's refusal of a map with the code it is, its facts as the code's parameters.

    Hashes this runner does not hold are `request.blobs_missing`, listing every one to upload. A key that is not a tree
    path and tries to leave the tree is the security refusal `security.input_path_refused`, by the runtime's one rule for
    a caller's path that leaves its root (`root_escape_of`): absolute, naming a drive or a network share, or climbing
    with a `..` segment, read with either separator, whether the caller sent it as a key of `files` or as a member of
    `bundle_b64`, as it is under `resources`. An entry of the wrong shape is the request's own, `request.invalid` naming
    the field the map rides. A file reference that names no file of the tree, or that leaves it, is
    `method.resource_missing`. Every other refusal is a rule of the method's package the tree breaks,
    `method.package_invalid`, whose `reason` is the standard's refusal code and whose `path` is the first path it names.

    Args:
        refusal_error: The standard's refusal.
        label: How the refusal names the map, such as "The `files` map".
        field: The request field the map rides, such as `files`.
    """
    refusal = refusal_error.refusal
    names = [wire_name(name) for name in refusal.names]
    first_name = names[0] if names else None
    msg = f"{label} is not a method tree. {refusal_error.message}"
    match refusal.code:
        case TreeRefusalCode.MISSING_BLOB:
            msg = (
                f"{label} names, by hash, bytes this runner does not hold at their stated size: {', '.join(refusal.names)}. "
                "Upload them (POST /v1/blobs/missing, then PUT /v1/blobs/{sha256}) and send the request again."
            )
            raise (
                RunnerRequestError(msg, field=field).with_error_code(CoreCode.REQUEST_BLOBS_MISSING).with_params(missing_blobs=list(refusal.names))
            ) from refusal_error
        case TreeRefusalCode.INVALID_TREE_PATH:
            for name in refusal.names:
                escape = root_escape_of(path=name)
                if escape is not None:
                    raise (
                        RequestMethodError(msg, file=wire_name(name))
                        .with_error_code(CoreCode.SECURITY_INPUT_PATH_REFUSED)
                        .with_params(rule=escape.rule)
                    ) from refusal_error
            raise RequestMethodError(msg, file=first_name).with_params(reason=refusal.code, path=first_name) from refusal_error
        case TreeRefusalCode.MALFORMED_ENTRY:
            raise RunnerRequestError(msg, field=field) from refusal_error
        case TreeRefusalCode.REFERENCE_NOT_IN_TREE:
            raise (
                RequestMethodError(msg, file=first_name)
                .with_error_code(CoreCode.METHOD_RESOURCE_MISSING)
                .with_params(file=first_name or "", reason=MethodResourceMissingReason.NOT_IN_TREE)
            ) from refusal_error
        case TreeRefusalCode.REFERENCE_LEAVES_TREE:
            raise (
                RequestMethodError(msg, file=first_name)
                .with_error_code(CoreCode.METHOD_RESOURCE_MISSING)
                .with_params(file=first_name or "", reason=MethodResourceMissingReason.LEAVES_TREE)
            ) from refusal_error
        case (
            TreeRefusalCode.SYMBOLIC_LINK
            | TreeRefusalCode.SPECIAL_FILE
            | TreeRefusalCode.NORMALIZATION_COLLISION
            | TreeRefusalCode.PATH_COLLISION
            | TreeRefusalCode.EMPTY_TREE
            | TreeRefusalCode.LONE_FILE_EXCLUDED
            | TreeRefusalCode.GITIGNORE_NOT_UTF8
            | TreeRefusalCode.DUPLICATE_KEY
            | TreeRefusalCode.EXCLUDED_NAME
            | TreeRefusalCode.REFERENCE_INVALID
            | TreeRefusalCode.REFERENCE_NOT_A_TREE_PATH
            | TreeRefusalCode.REFERENCE_IN_ONE_FILE_TREE
            | TreeRefusalCode.FUNCTION_NAME_WITHOUT_MODULE
            | TreeRefusalCode.FUNCTION_NAME_INVALID_SEGMENT
            | TreeRefusalCode.MODULE_NOT_IN_TREE
            | TreeRefusalCode.MODULE_AMBIGUOUS
        ):
            raise RequestMethodError(msg, file=first_name).with_params(reason=refusal.code, path=first_name) from refusal_error


async def _held_blobs(*, blob_store: RunnerBlobStore, stated_sizes: dict[str, set[int]], label: str, field: str) -> BlobStore:
    """The bytes a map's hash entries name that the blob store holds, looked up by size before any is read.

    A hash held at another size than one of its entries states is refused, since uploading its bytes again would not
    change the size the store holds them at. Every other held hash is held at the one size its entries state, which the
    census bounded, so reading them reads no more than the census allowed. A hash not held is left out, for the reader
    to report among the blobs this runner does not hold.

    Raises (as a problem document): a 422 `request.invalid` naming the field the map rides; its message, in the operator's
    diagnostics, lists each hash held at another size, with that size, which no parameter of the code carries.
    """
    stored = await blob_store.stored_sizes(sha256s=sorted(stated_sizes))
    mismatched = {sha256: size for sha256, size in stored.items() if size is not None and stated_sizes[sha256] != {size}}
    if mismatched:
        described = ", ".join(f"{sha256} (held at {size} bytes)" for sha256, size in mismatched.items())
        msg = (
            f"{label} states a size for a hash other than the size of the bytes this runner holds under it: {described}. "
            "A hash names one set of bytes, so state the size of those bytes."
        )
        raise RunnerRequestError(msg, field=field)
    return await blob_store.read_held(sizes={sha256: size for sha256, size in stored.items() if size is not None})


async def read_request_tree(
    *, document: str, blob_store: RunnerBlobStore | None, label: str, field: str, census: _MapCensus | None = None
) -> RequestTree:
    """Read one map of file entries a request carried, its hash entries from the runner's blob store.

    Args:
        document: The map's JSON text, as the request carried it.
        blob_store: The blob store of the caller's scope, or None for a map that names no bytes by hash.
        label: How a refusal names the map, such as "The `files` map".
        field: The request field the map rides, such as `files`, which a refusal of the request names.
        census: The map's census when the caller took it already, else taken here.

    Raises (as problem documents): the refusals of `_refuse_map`, `method.package_invalid` for a tree past a limit, and
    `request.invalid` for a map the reader cannot take as a source of a tree, each a 422.
    """
    if census is None:
        census = _census(document=document)
    held: BlobStore = InMemoryBlobStore()
    if census is not None:
        ensure_within_tree_limits(
            file_count=census.file_count,
            total_bytes=census.stated_bytes,
            largest_path=census.largest_path,
            largest_bytes=census.largest_bytes,
            label=label,
        )
        if census.stated_sizes and blob_store is not None:
            held = await _held_blobs(blob_store=blob_store, stated_sizes=census.stated_sizes, label=label, field=field)
    try:
        reading = read_file_map(document, blob_store=held)
    except MethodTreeRefusedError as exc:
        _refuse_map(refusal_error=exc, label=label, field=field)
    except TreeSourceError as exc:
        msg = f"{label} is not a method tree. {exc.message}"
        raise RunnerRequestError(msg, field=field) from exc
    request_tree = RequestTree(tree=reading.tree, contents=reading.contents)
    ensure_tree_within_limits(tree=request_tree, label=label)
    return request_tree


def _base64_map_document(*, entries: list[tuple[str, bytes]]) -> str:
    """A map of Base64 entries written from `(key, bytes)` pairs, a key given twice kept twice for the reader to refuse."""
    pairs = [(key, _JsonObject(pairs=[(BASE64_KEY, base64.b64encode(data).decode("ascii"))])) for key, data in entries]
    return _serialized(_JsonObject(pairs=pairs))


def manifest_of(*, tree: RequestTree, label: str, root: str) -> MethodsManifest | None:
    """The `METHODS.toml` at a tree's root, parsed, or None when the tree holds none there.

    `root` is the path the request names the tree's root by, empty for the method's own tree and `<address>/` or
    `.mthds/methods/<name>/` for a package it ships, so that a refusal's `path` names the manifest as the request does.

    Raises:
        MethodEntryError: The manifest is not UTF-8 text, or not a valid manifest (a 422 in the input domain).
    """
    manifest_bytes = tree.contents.get(MANIFEST_NAME)
    if manifest_bytes is None:
        return None
    try:
        return parse_methods_toml(manifest_bytes.decode("utf-8"))
    except UnicodeDecodeError as exc:
        msg = f"The {MANIFEST_NAME} of {label} is not UTF-8 text."
        raise (
            MethodEntryError(msg)
            .with_error_code(CoreCode.METHOD_PACKAGE_INVALID)
            .with_params(reason=MethodPackageReason.MANIFEST_INVALID, path=f"{root}{MANIFEST_NAME}")
        ) from exc
    except ManifestError as exc:
        msg = f"The {MANIFEST_NAME} of {label} is not a valid manifest: {exc.message}"
        raise (
            MethodEntryError(msg)
            .with_error_code(CoreCode.METHOD_PACKAGE_INVALID)
            .with_params(reason=MethodPackageReason.MANIFEST_INVALID, path=f"{root}{MANIFEST_NAME}")
        ) from exc


def is_package_dir_name(name: str) -> bool:
    """Whether `name` can name a package's directory: one tree path segment the membership rule keeps.

    That refuses an empty name, `.` and `..`, a name holding a separator or a character no tree path holds, and a name
    the rule keeps out of every tree, such as a dot directory or `node_modules`. Both readers of a method's shipped
    packages, a `bundle_b64` archive's and a fetched package's, hold each directory under `.mthds/methods/` to it, as
    the name a manifest declaring none gives its package.
    """
    if not name or "/" in name or tree_path_violation(name) is not None:
        return False
    return not excluded_name_violation(f"{name}/{_ANY_FILE_NAME}")


def dependency_address_of(*, tree: RequestTree, fallback_name: str, label: str, root: str) -> str:
    """The address a dependency tree's manifest declares, `address/name`, as a reference names the package.

    A manifest declaring no name takes `fallback_name`, the name of the directory the tree is written as, which is the
    name the engine's discovery gives such a package; it must then be a name a package's directory can take. `root` is
    the path the request names the tree's root by (`manifest_of`).

    Raises (as a 422 `method.package_invalid`): a tree with no valid `METHODS.toml` at its root (the manifest's own
    refusal, `MethodEntryError`, when it holds one that cannot be read), or one whose manifest declares no name when
    `fallback_name` cannot name a package's directory.
    """
    manifest = manifest_of(tree=tree, label=label, root=root)
    if manifest is None:
        msg = f"{label} holds no {MANIFEST_NAME} at its root, so no reference could find it as a package."
        raise RequestMethodError(msg).with_params(reason=MethodPackageReason.MANIFEST_MISSING, path=f"{root}{MANIFEST_NAME}")
    if manifest.name is not None:
        return f"{manifest.address}/{manifest.name}"
    if not is_package_dir_name(fallback_name):
        msg = (
            f"{label} declares no name in its {MANIFEST_NAME}, so it takes the last segment of its address, "
            f"'{wire_name(fallback_name)}', which cannot name a package's directory: declare the package's name in its {MANIFEST_NAME}."
        )
        raise RequestMethodError(msg).with_params(reason=MethodPackageReason.PACKAGE_NAME_INVALID, path=f"{root}{MANIFEST_NAME}")
    return f"{manifest.address}/{fallback_name}"


def dependency_dir_name(*, address: str) -> str:
    """The directory a dependency tree is written as: the last segment of its address, the name a reference finds it by."""
    return address.rsplit("/", 1)[-1]


def add_dependency(*, dependencies: dict[str, RequestTree], address: str, tree: RequestTree, label: str, root: str) -> None:
    """Add a dependency tree under its address, refusing an address a reference could not tell from one already there.

    A reference matches a package by its address without regard to case, so two addresses differing only in case are
    one identity too. `root` is the path the request names the tree's root by, which a refusal names.
    """
    for known in dependencies:
        if known.casefold() == address.casefold():
            msg = (
                f"{label} declares the address '{wire_name(address)}', which another dependency of the request declares too: a reference "
                "matches a package by its address without regard to case, so it could not tell them apart."
            )
            raise RequestMethodError(msg).with_params(reason=MethodPackageReason.DEPENDENCY_ADDRESS_COLLISION, path=root)
    dependencies[address] = tree


async def read_request_method(*, documents: TreeDocuments, blob_store: RunnerBlobStore) -> RequestMethod | None:
    """The method a request sends in `files`, with its `dependencies`, read in full, or None when it sends no `files`.

    Each dependency tree's manifest must declare the address it is keyed by.

    Raises (as problem documents): the refusals of `read_request_tree`, a 422 `request.invalid` naming `dependencies`
    for dependencies without `files`, and a 422 `pipelex.request.dependency_key_mismatch` naming the address to key it by
    for a dependency keyed by another address than its manifest's.
    """
    if documents.files is None:
        if documents.dependencies:
            msg = "`dependencies` accompany the method's own `files`: send the method's tree in `files`, and its dependencies beside it."
            raise RunnerRequestError(msg, field=DEPENDENCIES_FIELD)
        return None
    dependency_documents = documents.dependencies or {}
    # Every map's census first, so the request's trees together are held to their limits before any blob is read.
    files_census = _census(document=documents.files)
    dependency_censuses = {address: _census(document=dependency_document) for address, dependency_document in dependency_documents.items()}
    ensure_trees_within_request_limits(
        dependency_count=len(dependency_documents),
        total_bytes=sum(census.stated_bytes for census in [files_census, *dependency_censuses.values()] if census is not None),
        label=_METHOD_LABEL,
    )
    tree = await read_request_tree(document=documents.files, blob_store=blob_store, label=FILES_LABEL, field=FILES_FIELD, census=files_census)
    dependencies: dict[str, RequestTree] = {}
    for address, dependency_document in dependency_documents.items():
        label = f"The dependency '{wire_name(address)}'"
        dependency_tree = await read_request_tree(
            document=dependency_document, blob_store=blob_store, label=label, field=DEPENDENCIES_FIELD, census=dependency_censuses[address]
        )
        # The caller names a file of a dependency by the dependency's address, then its path inside it.
        root = f"{address}/"
        declared = dependency_address_of(tree=dependency_tree, fallback_name=dependency_dir_name(address=address), label=label, root=root)
        if declared != address:
            msg = f"{label} is keyed by an address its {MANIFEST_NAME} does not declare: it declares '{declared}'."
            raise (
                RunnerRequestError(msg, field=DEPENDENCIES_FIELD)
                .with_error_code(PipelexErrorCode.REQUEST_DEPENDENCY_KEY_MISMATCH)
                .with_params(key=address, address=declared)
            )
        add_dependency(dependencies=dependencies, address=address, tree=dependency_tree, label=label, root=root)
    request_method = RequestMethod(tree=tree, dependencies=dependencies)
    ensure_method_within_limits(request_method=request_method, label=_METHOD_LABEL)
    return request_method


async def read_archive_method(*, bundle_b64: str) -> RequestMethod:
    """The method a `bundle_b64` archive carries, read as a map of its entries, with the packages it ships.

    An entry under `.mthds/methods/<name>/` belongs to the method package `<name>` the archive ships, the layout of the
    local method cache, which becomes a dependency tree keyed by the address its manifest declares; the cache's
    provenance sidecar at the package's root is left out, as no file of the package. Every other entry is
    a file of the method's tree at the path the archive names it by, so any other entry under a dot directory, `.mthds/`
    included, is refused by the tree's rule.

    Raises (as problem documents): the archive's own refusals (`decode_bundle_archive`), the refusals of
    `read_request_tree`, and a 422 `method.package_invalid` for a shipped package with no manifest, or two declaring one
    address.
    """
    archive_entries = decode_bundle_archive(bundle_b64=bundle_b64)
    own_entries: list[tuple[str, bytes]] = []
    vendored_entries: dict[str, list[tuple[str, bytes]]] = {}
    for name, data in archive_entries:
        package_name, _, package_path = name.removeprefix(VENDORED_METHODS_PREFIX).partition("/")
        # A package directory the membership rule would keep out of the store, a dot directory, is no package: its
        # entries stay the method's own, which the tree's rule refuses.
        if name.startswith(VENDORED_METHODS_PREFIX) and package_path and is_package_dir_name(package_name):
            # The store's provenance sidecar records how the package was installed, and is no file of its tree.
            if package_path != PROVENANCE_FILENAME:
                vendored_entries.setdefault(package_name, []).append((package_path, data))
        else:
            own_entries.append((name, data))
    tree = await read_request_tree(document=_base64_map_document(entries=own_entries), blob_store=None, label=ARCHIVE_LABEL, field=BUNDLE_FIELD)
    dependencies: dict[str, RequestTree] = {}
    for package_name, package_entries in vendored_entries.items():
        label = f"The package '{VENDORED_METHODS_PREFIX}{package_name}/' of {ARCHIVE_LABEL[0].lower()}{ARCHIVE_LABEL[1:]}"
        dependency_tree = await read_request_tree(
            document=_base64_map_document(entries=package_entries), blob_store=None, label=label, field=BUNDLE_FIELD
        )
        root = f"{VENDORED_METHODS_PREFIX}{package_name}/"
        address = dependency_address_of(tree=dependency_tree, fallback_name=package_name, label=label, root=root)
        add_dependency(dependencies=dependencies, address=address, tree=dependency_tree, label=label, root=root)
    request_method = RequestMethod(tree=tree, dependencies=dependencies)
    ensure_method_within_limits(request_method=request_method, label=ARCHIVE_LABEL)
    return request_method


def with_resources(*, request_method: RequestMethod, resources: Mapping[str, bytes] | None) -> RequestMethod:
    """The method with the files `resources` sends joined to its tree, each at its path from the tree's root.

    A file the tree already holds with the same bytes changes nothing; other bytes under a path the tree holds, or a path
    that cannot name a file of a tree, are refused naming the path.

    Raises (as problem documents): a 422 `request.invalid` naming `resources` for two different files under one path or
    a path no tree could hold, and a 422 `method.package_invalid` for a tree the files take past this runner's limits.
    """
    if not resources:
        return request_method
    contents = dict(request_method.tree.contents)
    for path, data in resources.items():
        held = contents.get(path)
        if held is not None:
            if held != data:
                refuse_two_files_under_one_path(path=path, where="one in `resources` and one in the method's files")
            continue
        violation = tree_path_violation(path)
        if violation is not None or excluded_name_violation(path):
            reason = violation or "the membership rule keeps it out of every method tree"
            msg = f"The file '{wire_name(path)}' sent in `resources` cannot be a file of the method's tree: {reason}."
            raise RunnerRequestError(msg, field=SUBMITTED_FILES_FIELD)
        contents[path] = data
    collisions = path_collisions(contents)
    if collisions:
        msg = f"The files sent in `resources` collide with the method's files: {', '.join(repr(path) for path in collisions)}."
        raise RunnerRequestError(msg, field=SUBMITTED_FILES_FIELD)
    merged = RequestMethod(tree=RequestTree.make_from_contents(contents=contents), dependencies=request_method.dependencies)
    ensure_tree_within_limits(tree=merged.tree, label=_WITH_RESOURCES_LABEL)
    ensure_method_within_limits(request_method=merged, label=_WITH_RESOURCES_LABEL)
    return merged


def _python_sources(*, tree: RequestTree) -> dict[str, str]:
    """A tree's Python sources by tree path, skipping a file that is not UTF-8, which no interpreter could import."""
    sources: dict[str, str] = {}
    for tree_path, data in tree.contents.items():
        if not tree_path.endswith(PYTHON_SUFFIX):
            continue
        try:
            sources[tree_path] = data.decode("utf-8")
        except UnicodeDecodeError:
            continue
    return sources


def ensure_python_allowed(*, request_method: RequestMethod, label: str, origin: CustomCodeOrigin) -> None:
    """Refuse a method shipping Python where it may not run, before anything of it is written.

    On a deployment that is not sandbox-hosted, any `.py` file is refused (501
    `pipelex.deployment.custom_code_requires_sandbox`, whose `origin` says whether the request sent the method or named
    a package to fetch): running it would import it in-process. On a sandbox-hosted deployment, the method's own tree
    declaring a Python structure class is refused (`MethodStructuresRefusedError`, a 422), naming each file by its tree
    path; a dependency tree is checked once written, by its address (`written_method`).
    """
    if not request_method.has_python:
        return
    if not is_pipe_func_sandbox_hosted():
        msg = f"{label} ships custom Python (.py); running it requires a sandbox-hosted deployment."
        raise CustomCodeRequiresSandboxError(msg, origin=origin)
    ensure_no_structured_content_in_library_sources(sources_by_dir={Path(): _python_sources(tree=request_method.tree)})


async def record_request_method(*, request_method: RequestMethod, blob_store: RunnerBlobStore) -> None:
    """Hold every tree of a method read in full in the blob store, its files then its listing."""
    await blob_store.record_tree(tree=request_method.tree.tree, contents=request_method.tree.contents)
    for dependency in request_method.dependencies.values():
        await blob_store.record_tree(tree=dependency.tree, contents=dependency.contents)


def ensure_method_holds_a_bundle(*, request_method: RequestMethod, label: str) -> None:
    """Refuse a method whose own tree holds no `.mthds` bundle, with a 422 `method.package_invalid`."""
    if not request_method.tree.bundle_paths:
        msg = f"{label} holds no .mthds bundle of its own."
        if request_method.dependencies:
            msg += " The packages it carries are dependencies: the method's own bundles go in its own tree."
        raise RequestMethodError(msg).with_params(reason=MethodPackageReason.NO_BUNDLE)


def select_tree_entry(*, tree: RequestTree, method_label: str) -> MethodEntry:
    """The pipe a run of a method tree starts at when it names none, by the MTHDS protocol's rule (`select_entry`).

    Each bundle is parsed to read what it declares, its items naming the bundle by its tree path.

    Args:
        tree: The method's tree, read in full.
        method_label: How the entry rule's messages name the method, as in "The method <label> holds no …".

    Raises:
        ValidateBundleError: A bundle of the tree does not parse.
        MethodEntryError: The tree has no single pipe to start at, or a bundle or the manifest cannot be read.
    """
    candidates: list[EntryCandidate] = []
    for tree_path in tree.bundle_paths:
        try:
            content = tree.contents[tree_path].decode("utf-8")
        except UnicodeDecodeError as exc:
            msg = f"The bundle '{tree_path}' of the method {method_label} is not UTF-8 text."
            raise MethodEntryError(msg).with_error_code(CoreCode.METHOD_SYNTAX).with_params(finding=NOT_UTF8_FINDING) from exc
        with translate_to_validate_bundle_error():
            blueprint = MthdsParser.make_pipelex_bundle_blueprint(mthds_content=content, mthds_source=tree_path)
        candidates.append(EntryCandidate.of_blueprint(tree_path=tree_path, blueprint=blueprint))
    manifest = manifest_of(tree=tree, label=f"the method {method_label}", root="")
    return select_entry(candidates=candidates, manifest=manifest, method_label=method_label)


class WrittenMethod(NamedTuple):
    """A method written out and held as written, for the load: its tree's directory, and its dependencies' directories."""

    method_dir: Path
    methods_dirs: list[Path] | None
    tree: MethodTree


@contextmanager
def written_method(*, request_method: RequestMethod) -> Generator[WrittenMethod, None, None]:
    """Write a method's trees into a temporary directory, hold each as written, and remove them all on the way out.

    The method's own tree is written as one directory, the library directory of the load; each dependency tree as
    `<name>/` in a methods directory of its own, the layout the engine's `methods_dirs` take, so two dependencies sharing
    a name never meet. On a sandbox-hosted deployment, a dependency tree declaring a Python structure class is refused,
    naming it by its address, as a fetched package is (`MethodStructuresRefusedError`, a 422).
    """
    with ExitStack() as stack:
        temp_dir = Path(tempfile.mkdtemp(prefix="pipelex-method-"))
        stack.callback(shutil.rmtree, temp_dir, ignore_errors=True)
        method_dir = temp_dir / "tree"
        written = write_method_tree(contents=request_method.tree.contents, destination=method_dir, expected_digest=request_method.tree.tree.digest)
        stack.enter_context(WRITTEN_METHOD_TREES.holding(tree=written))
        methods_dirs: list[Path] = []
        for index_dependency, (address, dependency) in enumerate(request_method.dependencies.items()):
            methods_dir = temp_dir / f"methods-{index_dependency}"
            dependency_dir = methods_dir / dependency_dir_name(address=address)
            dependency_written = write_method_tree(contents=dependency.contents, destination=dependency_dir, expected_digest=dependency.tree.digest)
            stack.enter_context(WRITTEN_METHOD_TREES.holding(tree=dependency_written))
            if dependency.has_python and is_pipe_func_sandbox_hosted():
                ensure_no_structured_content_python(package_dir=dependency_dir, package_address=address)
            methods_dirs.append(methods_dir)
        yield WrittenMethod(method_dir=method_dir, methods_dirs=methods_dirs or None, tree=written)
