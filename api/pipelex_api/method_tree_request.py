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
   `MethodTreeTooLarge` naming the limit.
2. The bytes of every hash entry are read from the runner's blob store, under the caller's scope, at once.
3. The map is read (`read_file_map`): a refusal of the standard is a 422 `InvalidMethodFiles` whose `tree_refusal`
   member carries the refusal's code and the paths it names, and hash entries the store does not hold at their stated
   size are one 422 `MissingBlobs` whose `missing_blobs` member lists every such hash.
4. The files `resources` sends join the tree (`with_resources`), the same bytes under a path the tree holds or a new
   file at a tree path; other bytes under a path the tree holds are a 422 `InvalidResourcePath` naming it.
5. Python is honored only on a sandbox-hosted deployment: a method holding a `.py` file is refused with a 403
   `CustomCodeRequiresSandbox` before anything is written, and on a sandbox-hosted deployment a tree declaring a Python
   structure class is refused (`MethodStructuresRefusedError`, a 403).
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
from mthds.protocol.problem.registry import CoreCode
from pipelex.cli.installed_methods import PROVENANCE_FILENAME
from pipelex.config import is_pipe_func_sandbox_hosted
from pipelex.core.bundle_resources.bundle_resource import root_escape_refusal
from pipelex.libraries.written_trees import WRITTEN_METHOD_TREES, write_method_tree
from pipelex.methods.structures_check import ensure_no_structured_content_in_library_sources, ensure_no_structured_content_python
from pipelex.mthds_parsing.parser import MthdsParser
from pipelex.pipeline.exceptions import MethodEntryError
from pipelex.pipeline.method_entry import EntryCandidate, MethodEntry, select_entry
from pipelex.pipeline.validate_bundle_translation import translate_to_validate_bundle_error

from pipelex_api.blob_store import RunnerBlobStore
from pipelex_api.bundle import decode_bundle_archive
from pipelex_api.bundle_resources import refuse_two_files_under_one_path
from pipelex_api.error_types import ErrorType
from pipelex_api.errors import ApiSecurityRefusal, raise_forbidden, raise_validation_error, raise_validation_problem
from pipelex_api.limits import (
    MAX_METHOD_DEPENDENCIES,
    MAX_METHOD_REQUEST_TOTAL_BYTES,
    MAX_METHOD_TREE_FILE_BYTES,
    MAX_METHOD_TREE_FILES,
    MAX_METHOD_TREE_TOTAL_BYTES,
)

FILES_FIELD = "files"
DEPENDENCIES_FIELD = "dependencies"
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

    Raises (as problem documents): a 422 `InvalidJSON` for a body that does not decode or parse, and a 422
    `InvalidMethodFiles` for `dependencies` that is not an object, or that gives one address twice.
    """
    try:
        parsed = _parse_keeping_pairs(body.decode(json.detect_encoding(body), "surrogatepass"))
    except (UnicodeDecodeError, ValueError) as exc:
        # The route's parser read these bytes already, so this is a second line of defence: `JSONDecodeError` and
        # an integer longer than Python converts are both a `ValueError`.
        raise_validation_error(message=f"Request body is not valid JSON: {exc!s}", error_type=ErrorType.INVALID_JSON)
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
        raise_validation_error(message=msg, error_type=ErrorType.INVALID_METHOD_FILES)
    dependency_documents: dict[str, str] = {}
    for address, dependency_member in dependencies_member.pairs:
        if address in dependency_documents:
            raise_validation_problem(
                message=f"`dependencies` gives the address '{wire_name(address)}' twice.",
                error_type=ErrorType.INVALID_METHOD_FILES,
                members={"tree_refusal": {"code": TreeRefusalCode.DUPLICATE_KEY, "names": [wire_name(address)]}},
            )
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
    """Refuse a tree past one of this runner's limits, naming the limit, with a 422 `MethodTreeTooLarge`."""
    if file_count > MAX_METHOD_TREE_FILES:
        msg = f"{label} holds {file_count} files, past this runner's limit of {MAX_METHOD_TREE_FILES} files in a method tree."
        raise_validation_error(message=msg, error_type=ErrorType.METHOD_TREE_TOO_LARGE)
    if largest_path is not None and largest_bytes > MAX_METHOD_TREE_FILE_BYTES:
        msg = (
            f"{label} holds the file '{wire_name(largest_path)}' of {largest_bytes} bytes, past this runner's limit of "
            f"{MAX_METHOD_TREE_FILE_BYTES // 1024} KiB for one file of a method tree."
        )
        raise_validation_error(message=msg, error_type=ErrorType.METHOD_TREE_TOO_LARGE)
    if total_bytes > MAX_METHOD_TREE_TOTAL_BYTES:
        msg = f"{label} holds {total_bytes} bytes, past this runner's limit of {MAX_METHOD_TREE_TOTAL_BYTES // 1024} KiB for a method tree."
        raise_validation_error(message=msg, error_type=ErrorType.METHOD_TREE_TOO_LARGE)


def ensure_tree_within_limits(*, tree: RequestTree, label: str) -> None:
    """Refuse a tree read in full that passes one of this runner's limits, with a 422 `MethodTreeTooLarge`."""
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
    """Refuse a method whose trees together pass this runner's limits, with a 422 `MethodTreeTooLarge`.

    Each tree is held to the tree limits on its own; these bound what one request carries in all, its method's tree and
    every dependency tree beside it, so the memory and the disk a request takes do not grow with its dependencies.
    """
    if dependency_count > MAX_METHOD_DEPENDENCIES:
        msg = f"{label} carries {dependency_count} dependencies, past this runner's limit of {MAX_METHOD_DEPENDENCIES} dependency trees."
        raise_validation_error(message=msg, error_type=ErrorType.METHOD_TREE_TOO_LARGE)
    if total_bytes > MAX_METHOD_REQUEST_TOTAL_BYTES:
        msg = (
            f"{label} holds {total_bytes} bytes across its tree and its dependency trees, past this runner's limit of "
            f"{MAX_METHOD_REQUEST_TOTAL_BYTES // 1024} KiB for a method and its dependencies."
        )
        raise_validation_error(message=msg, error_type=ErrorType.METHOD_TREE_TOO_LARGE)


def ensure_method_within_limits(*, request_method: "RequestMethod", label: str) -> None:
    """Refuse a method read in full whose trees together pass this runner's limits, with a 422 `MethodTreeTooLarge`."""
    trees = [request_method.tree, *request_method.dependencies.values()]
    ensure_trees_within_request_limits(
        dependency_count=len(request_method.dependencies),
        total_bytes=sum(len(data) for tree in trees for data in tree.contents.values()),
        label=label,
    )


def _refuse_map(*, refusal_error: MethodTreeRefusedError, label: str) -> NoReturn:
    """Answer the standard's refusal of a map: the hashes to upload, or the code and the paths it names."""
    refusal = refusal_error.refusal
    match refusal.code:
        case TreeRefusalCode.MISSING_BLOB:
            msg = (
                f"{label} names, by hash, bytes this runner does not hold at their stated size: {', '.join(refusal.names)}. "
                "Upload them (POST /v1/blobs/missing, then PUT /v1/blobs/{sha256}) and send the request again."
            )
            raise_validation_problem(message=msg, error_type=ErrorType.MISSING_BLOBS, members={"missing_blobs": list(refusal.names)})
        case (
            TreeRefusalCode.SYMBOLIC_LINK
            | TreeRefusalCode.SPECIAL_FILE
            | TreeRefusalCode.INVALID_TREE_PATH
            | TreeRefusalCode.NORMALIZATION_COLLISION
            | TreeRefusalCode.PATH_COLLISION
            | TreeRefusalCode.EMPTY_TREE
            | TreeRefusalCode.LONE_FILE_EXCLUDED
            | TreeRefusalCode.GITIGNORE_NOT_UTF8
            | TreeRefusalCode.DUPLICATE_KEY
            | TreeRefusalCode.EXCLUDED_NAME
            | TreeRefusalCode.MALFORMED_ENTRY
            | TreeRefusalCode.REFERENCE_INVALID
            | TreeRefusalCode.REFERENCE_LEAVES_TREE
            | TreeRefusalCode.REFERENCE_NOT_A_TREE_PATH
            | TreeRefusalCode.REFERENCE_NOT_IN_TREE
            | TreeRefusalCode.REFERENCE_IN_ONE_FILE_TREE
            | TreeRefusalCode.FUNCTION_NAME_WITHOUT_MODULE
            | TreeRefusalCode.FUNCTION_NAME_INVALID_SEGMENT
            | TreeRefusalCode.MODULE_NOT_IN_TREE
            | TreeRefusalCode.MODULE_AMBIGUOUS
        ):
            raise_validation_problem(
                message=f"{label} is not a method tree. {refusal_error.message}",
                error_type=ErrorType.INVALID_METHOD_FILES,
                members={"tree_refusal": {"code": refusal.code, "names": [wire_name(name) for name in refusal.names]}},
                security_refusal=_tree_path_security_refusal(refusal_error=refusal_error),
            )


def _tree_path_security_refusal(*, refusal_error: MethodTreeRefusedError) -> ApiSecurityRefusal | None:
    """The security refusal a tree refusal is, when a path it names tries to leave the tree, else `None`.

    The standard's reader refuses a key that is not a tree path without saying why, so the runtime's one rule for a
    caller's path that leaves its root decides (`root_escape_refusal`): a path that is absolute, names a drive or a
    network share, or climbs with a `..` segment, read with either separator, is a traversal,
    `security.input_path_refused`, whether the caller sent it as a key of `files` or as a member of `bundle_b64`, which
    the same reader judges, and as it is under `resources`. Every other path the reader refuses (an empty segment, a
    backslash, a colon, a path not in NFC) is the shape of how the caller packed the method, a refusal of the request
    and no security event.
    """
    refusal = refusal_error.refusal
    match refusal.code:
        case TreeRefusalCode.INVALID_TREE_PATH:
            if any(root_escape_refusal(path=name) is not None for name in refusal.names):
                return ApiSecurityRefusal(code=CoreCode.SECURITY_INPUT_PATH_REFUSED, error_type=type(refusal_error).__name__)
            return None
        case (
            TreeRefusalCode.MISSING_BLOB
            | TreeRefusalCode.SYMBOLIC_LINK
            | TreeRefusalCode.SPECIAL_FILE
            | TreeRefusalCode.NORMALIZATION_COLLISION
            | TreeRefusalCode.PATH_COLLISION
            | TreeRefusalCode.EMPTY_TREE
            | TreeRefusalCode.LONE_FILE_EXCLUDED
            | TreeRefusalCode.GITIGNORE_NOT_UTF8
            | TreeRefusalCode.DUPLICATE_KEY
            | TreeRefusalCode.EXCLUDED_NAME
            | TreeRefusalCode.MALFORMED_ENTRY
            | TreeRefusalCode.REFERENCE_INVALID
            | TreeRefusalCode.REFERENCE_LEAVES_TREE
            | TreeRefusalCode.REFERENCE_NOT_A_TREE_PATH
            | TreeRefusalCode.REFERENCE_NOT_IN_TREE
            | TreeRefusalCode.REFERENCE_IN_ONE_FILE_TREE
            | TreeRefusalCode.FUNCTION_NAME_WITHOUT_MODULE
            | TreeRefusalCode.FUNCTION_NAME_INVALID_SEGMENT
            | TreeRefusalCode.MODULE_NOT_IN_TREE
            | TreeRefusalCode.MODULE_AMBIGUOUS
        ):
            return None


async def _held_blobs(*, blob_store: RunnerBlobStore, stated_sizes: dict[str, set[int]], label: str) -> BlobStore:
    """The bytes a map's hash entries name that the blob store holds, looked up by size before any is read.

    A hash held at another size than one of its entries states is refused, since uploading its bytes again would not
    change the size the store holds them at. Every other held hash is held at the one size its entries state, which the
    census bounded, so reading them reads no more than the census allowed. A hash not held is left out, for the reader
    to report among the blobs this runner does not hold.

    Raises (as a problem document): a 422 `BlobMismatch` whose `mismatched_blobs` member lists each hash held at another
    size, with that size.
    """
    stored = await blob_store.stored_sizes(sha256s=sorted(stated_sizes))
    mismatched = {sha256: size for sha256, size in stored.items() if size is not None and stated_sizes[sha256] != {size}}
    if mismatched:
        described = ", ".join(f"{sha256} (held at {size} bytes)" for sha256, size in mismatched.items())
        msg = (
            f"{label} states a size for a hash other than the size of the bytes this runner holds under it: {described}. "
            "A hash names one set of bytes, so state the size of those bytes."
        )
        raise_validation_problem(
            message=msg,
            error_type=ErrorType.BLOB_MISMATCH,
            members={"mismatched_blobs": [{"sha256": sha256, "held_size": size} for sha256, size in mismatched.items()]},
        )
    return await blob_store.read_held(sizes={sha256: size for sha256, size in stored.items() if size is not None})


async def read_request_tree(*, document: str, blob_store: RunnerBlobStore | None, label: str, census: _MapCensus | None = None) -> RequestTree:
    """Read one map of file entries a request carried, its hash entries from the runner's blob store.

    Args:
        document: The map's JSON text, as the request carried it.
        blob_store: The blob store of the caller's scope, or None for a map that names no bytes by hash.
        label: How a refusal names the map, such as "The `files` map".
        census: The map's census when the caller took it already, else taken here.

    Raises (as problem documents): `MethodTreeTooLarge`, `InvalidMethodFiles` and `MissingBlobs`, each a 422.
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
            held = await _held_blobs(blob_store=blob_store, stated_sizes=census.stated_sizes, label=label)
    try:
        reading = read_file_map(document, blob_store=held)
    except MethodTreeRefusedError as exc:
        _refuse_map(refusal_error=exc, label=label)
    except TreeSourceError as exc:
        raise_validation_problem(message=f"{label} is not a method tree. {exc.message}", error_type=ErrorType.INVALID_METHOD_FILES, members={})
    request_tree = RequestTree(tree=reading.tree, contents=reading.contents)
    ensure_tree_within_limits(tree=request_tree, label=label)
    return request_tree


def _base64_map_document(*, entries: list[tuple[str, bytes]]) -> str:
    """A map of Base64 entries written from `(key, bytes)` pairs, a key given twice kept twice for the reader to refuse."""
    pairs = [(key, _JsonObject(pairs=[(BASE64_KEY, base64.b64encode(data).decode("ascii"))])) for key, data in entries]
    return _serialized(_JsonObject(pairs=pairs))


def manifest_of(*, tree: RequestTree, label: str) -> MethodsManifest | None:
    """The `METHODS.toml` at a tree's root, parsed, or None when the tree holds none there.

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
        raise MethodEntryError(msg).with_error_code(CoreCode.METHOD_PACKAGE_INVALID) from exc
    except ManifestError as exc:
        msg = f"The {MANIFEST_NAME} of {label} is not a valid manifest: {exc.message}"
        raise MethodEntryError(msg).with_error_code(CoreCode.METHOD_PACKAGE_INVALID) from exc


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


def dependency_address_of(*, tree: RequestTree, fallback_name: str, label: str) -> str:
    """The address a dependency tree's manifest declares, `address/name`, as a reference names the package.

    A manifest declaring no name takes `fallback_name`, the name of the directory the tree is written as, which is the
    name the engine's discovery gives such a package; it must then be a name a package's directory can take.

    Raises (as a 422 `InvalidMethodFiles`): a tree with no valid `METHODS.toml` at its root, or one whose manifest
    declares no name when `fallback_name` cannot name a package's directory.
    """
    try:
        manifest = manifest_of(tree=tree, label=label)
    except MethodEntryError as exc:
        raise_validation_error(message=exc.message, error_type=ErrorType.INVALID_METHOD_FILES)
    if manifest is None:
        msg = f"{label} holds no {MANIFEST_NAME} at its root, so no reference could find it as a package."
        raise_validation_error(message=msg, error_type=ErrorType.INVALID_METHOD_FILES)
    if manifest.name is not None:
        return f"{manifest.address}/{manifest.name}"
    if not is_package_dir_name(fallback_name):
        msg = (
            f"{label} declares no name in its {MANIFEST_NAME}, so it takes the last segment of its address, "
            f"'{wire_name(fallback_name)}', which cannot name a package's directory: declare the package's name in its {MANIFEST_NAME}."
        )
        raise_validation_error(message=msg, error_type=ErrorType.INVALID_METHOD_FILES)
    return f"{manifest.address}/{fallback_name}"


def dependency_dir_name(*, address: str) -> str:
    """The directory a dependency tree is written as: the last segment of its address, the name a reference finds it by."""
    return address.rsplit("/", 1)[-1]


def add_dependency(*, dependencies: dict[str, RequestTree], address: str, tree: RequestTree, label: str) -> None:
    """Add a dependency tree under its address, refusing an address a reference could not tell from one already there.

    A reference matches a package by its address without regard to case, so two addresses differing only in case are
    one identity too.
    """
    for known in dependencies:
        if known.casefold() == address.casefold():
            msg = (
                f"{label} declares the address '{wire_name(address)}', which another dependency of the request declares too: a reference "
                "matches a package by its address without regard to case, so it could not tell them apart."
            )
            raise_validation_error(message=msg, error_type=ErrorType.INVALID_METHOD_FILES)
    dependencies[address] = tree


async def read_request_method(*, documents: TreeDocuments, blob_store: RunnerBlobStore) -> RequestMethod | None:
    """The method a request sends in `files`, with its `dependencies`, read in full, or None when it sends no `files`.

    Each dependency tree's manifest must declare the address it is keyed by.

    Raises (as problem documents): the refusals of `read_request_tree`, and a 422 `InvalidMethodFiles` for
    `dependencies` without `files` or a dependency keyed by another address than its manifest's.
    """
    if documents.files is None:
        if documents.dependencies:
            msg = "`dependencies` accompany the method's own `files`: send the method's tree in `files`, and its dependencies beside it."
            raise_validation_error(message=msg, error_type=ErrorType.INVALID_METHOD_FILES)
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
    tree = await read_request_tree(document=documents.files, blob_store=blob_store, label=FILES_LABEL, census=files_census)
    dependencies: dict[str, RequestTree] = {}
    for address, dependency_document in dependency_documents.items():
        label = f"The dependency '{wire_name(address)}'"
        dependency_tree = await read_request_tree(
            document=dependency_document, blob_store=blob_store, label=label, census=dependency_censuses[address]
        )
        declared = dependency_address_of(tree=dependency_tree, fallback_name=dependency_dir_name(address=address), label=label)
        if declared != address:
            msg = f"{label} is keyed by an address its {MANIFEST_NAME} does not declare: it declares '{declared}'."
            raise_validation_error(message=msg, error_type=ErrorType.INVALID_METHOD_FILES)
        add_dependency(dependencies=dependencies, address=address, tree=dependency_tree, label=label)
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
    `read_request_tree`, and a 422 `InvalidMethodFiles` for a shipped package with no manifest, or two declaring one address.
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
    tree = await read_request_tree(document=_base64_map_document(entries=own_entries), blob_store=None, label=ARCHIVE_LABEL)
    dependencies: dict[str, RequestTree] = {}
    for package_name, package_entries in vendored_entries.items():
        label = f"The package '{VENDORED_METHODS_PREFIX}{package_name}/' of {ARCHIVE_LABEL[0].lower()}{ARCHIVE_LABEL[1:]}"
        dependency_tree = await read_request_tree(document=_base64_map_document(entries=package_entries), blob_store=None, label=label)
        address = dependency_address_of(tree=dependency_tree, fallback_name=package_name, label=label)
        add_dependency(dependencies=dependencies, address=address, tree=dependency_tree, label=label)
    request_method = RequestMethod(tree=tree, dependencies=dependencies)
    ensure_method_within_limits(request_method=request_method, label=ARCHIVE_LABEL)
    return request_method


def with_resources(*, request_method: RequestMethod, resources: Mapping[str, bytes] | None) -> RequestMethod:
    """The method with the files `resources` sends joined to its tree, each at its path from the tree's root.

    A file the tree already holds with the same bytes changes nothing; other bytes under a path the tree holds, or a path
    that cannot name a file of a tree, are refused naming the path.

    Raises (as problem documents): a 422 `InvalidResourcePath` for two different files under one path or a path no tree
    could hold, and a 422 `MethodTreeTooLarge` for a tree the files take past this runner's limits.
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
            raise_validation_error(message=msg, error_type=ErrorType.INVALID_RESOURCE_PATH)
        contents[path] = data
    collisions = path_collisions(contents)
    if collisions:
        msg = f"The files sent in `resources` collide with the method's files: {', '.join(repr(path) for path in collisions)}."
        raise_validation_error(message=msg, error_type=ErrorType.INVALID_RESOURCE_PATH)
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


def ensure_python_allowed(*, request_method: RequestMethod, label: str) -> None:
    """Refuse a method shipping Python where it may not run, before anything of it is written.

    On a deployment that is not sandbox-hosted, any `.py` file is refused (403 `CustomCodeRequiresSandbox`): running it
    would import it in-process. On a sandbox-hosted deployment, the method's own tree declaring a Python structure class
    is refused (`MethodStructuresRefusedError`, a 403), naming each file by its tree path; a dependency tree is checked
    once written, by its address (`written_method`).
    """
    if not request_method.has_python:
        return
    if not is_pipe_func_sandbox_hosted():
        msg = f"{label} ships custom Python (.py); running it requires a sandbox-hosted deployment."
        raise_forbidden(message=msg, error_type=ErrorType.CUSTOM_CODE_REQUIRES_SANDBOX)
    ensure_no_structured_content_in_library_sources(sources_by_dir={Path(): _python_sources(tree=request_method.tree)})


async def record_request_method(*, request_method: RequestMethod, blob_store: RunnerBlobStore) -> None:
    """Hold every tree of a method read in full in the blob store, its files then its listing."""
    await blob_store.record_tree(tree=request_method.tree.tree, contents=request_method.tree.contents)
    for dependency in request_method.dependencies.values():
        await blob_store.record_tree(tree=dependency.tree, contents=dependency.contents)


def ensure_method_holds_a_bundle(*, request_method: RequestMethod, label: str) -> None:
    """Refuse a method whose own tree holds no `.mthds` bundle, with a 422 `InvalidBundle`."""
    if not request_method.tree.bundle_paths:
        msg = f"{label} holds no .mthds bundle of its own."
        if request_method.dependencies:
            msg += " The packages it carries are dependencies: the method's own bundles go in its own tree."
        raise_validation_error(message=msg, error_type=ErrorType.INVALID_BUNDLE)


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
            raise MethodEntryError(msg).with_error_code(CoreCode.METHOD_SYNTAX) from exc
        with translate_to_validate_bundle_error():
            blueprint = MthdsParser.make_pipelex_bundle_blueprint(mthds_content=content, mthds_source=tree_path)
        candidates.append(EntryCandidate(tree_path=tree_path, blueprint=blueprint))
    manifest = manifest_of(tree=tree, label=f"the method {method_label}")
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
    naming it by its address, as a fetched package is (`MethodStructuresRefusedError`, a 403).
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
