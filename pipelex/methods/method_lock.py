"""Check a dependency the runtime fetched against the `methods.lock` of the method that calls it.

A method's `methods.lock` (`mthds/docs/spec/lock-format.md`) records, for each remote dependency, the version it was
locked at and the tree digest of the package's tree (`mthds/docs/spec/method-tree.md`, "The Tree Digest"). It lies at the
root of the method's tree, beside `METHODS.toml`, and it is a file of that tree, so it travels with the method wherever
the method goes: in a tree a caller sends, in a package fetched by `method_ref`, and in a method's directory on disk.

When a load resolves a package a bundle calls by address to a copy the runtime fetched, whether it fetched it for this
load or an earlier fetch installed it (the copy carries the fetch's provenance), the tree the load lists for that package
is checked against the lock at the root of every tree whose bundles call it. A later batch of the same library calling a
package an earlier batch already loaded from such a copy is checked against the same tree, since it runs that tree. A
lock that does not name the package's address, or no lock at all, checks nothing; a lock naming it with another digest
refuses the load (`MethodLockMismatchError`, the core code `security.integrity_mismatch`), whatever version it names,
since the lock verifies what was fetched and never chooses it. A package the method ships with itself is not checked: it
travels with the lock, from the same author, so there is nothing fetched to verify.

The lock is read with the `mthds` package's own parser, and only when a dependency resolves to a copy the runtime
fetched, so a lock that cannot be read refuses only a load that needs it (`MethodLockInvalidError`,
`method.package_invalid` with the reason `lock_invalid`): a lock the tree lists whose bytes cannot be read, or changed
since the tree was listed, and a lock written before tree digests among them, as the standard requires.
"""

from collections.abc import Iterable
from typing import NamedTuple

from mthds.method_tree.digest import sha256_hex
from mthds.method_tree.models import MethodTree
from mthds.package.exceptions import LockFileError
from mthds.package.lock_file import LOCK_FILENAME, LockedPackage, parse_lock_file

from pipelex.core.method_trees.method_file_store import LOCAL_METHOD_FILES
from pipelex.methods.exceptions import MethodLockInvalidError, MethodLockMismatchError


class FetchedCopy(NamedTuple):
    """A copy of a dependency the runtime fetched, for this load or an earlier one, as the reference calling it found it.

    Attributes:
        address: The package's address as a lock keys it, without any ``@<tag>``.
        version: The version the copy's manifest declares.
        pinned_tag: The tag the reference pins, None for a reference pinning none.
        fetched_tag: The tag the copy was fetched at, as its provenance records it, None for a fetch of the default branch.
    """

    address: str
    version: str
    pinned_tag: str | None
    fetched_tag: str | None


class FetchedTree(NamedTuple):
    """The tree a load listed, and so loaded, for a fetched copy of a dependency."""

    copy: FetchedCopy
    tree_digest: str


def _unreadable_lock(*, address: str, reason: str) -> MethodLockInvalidError:
    return MethodLockInvalidError(f"The method's {LOCK_FILENAME} {reason}, so it cannot verify the dependency '{address}' this runtime fetched.")


def _lock_bytes(*, tree: MethodTree, address: str) -> bytes | None:
    """The bytes of the lock at the root of `tree`, as the tree was listed, or None when the tree holds none.

    A tree listed from a directory is read there, and its bytes are checked against the hash the listing recorded; a tree
    of files held in memory, such as the files submitted beside a method's content strings, is read from the method file
    store, which holds it for the load and checks the same hash.

    Raises:
        MethodLockInvalidError: The tree lists a lock whose bytes cannot be read, or changed since the tree was listed.
    """
    lock_file = next((tree_file for tree_file in tree.files if tree_file.path == LOCK_FILENAME), None)
    if lock_file is None:
        return None
    if tree.directory is None:
        held_bytes = LOCAL_METHOD_FILES.read_held_file(tree_digest=tree.digest, tree_path=LOCK_FILENAME)
        if held_bytes is None:
            raise _unreadable_lock(address=address, reason="is listed in the method's tree but not held for this load, or changed since")
        return held_bytes
    try:
        lock_bytes = tree.file_location(LOCK_FILENAME).read_bytes()
    except OSError as exc:
        raise _unreadable_lock(address=address, reason="cannot be read") from exc
    if sha256_hex(lock_bytes) != lock_file.sha256:
        raise _unreadable_lock(address=address, reason="changed since the method's tree was listed")
    return lock_bytes


def _locked_entries(*, tree: MethodTree, address: str) -> list[LockedPackage]:
    """The entries the lock at the root of `tree` records for `address`, compared without regard to case.

    Raises:
        MethodLockInvalidError: The lock cannot be read, is not UTF-8 text, does not parse, or holds an entry the lock
            format refuses.
    """
    lock_bytes = _lock_bytes(tree=tree, address=address)
    if lock_bytes is None:
        return []
    try:
        lock_text = lock_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _unreadable_lock(address=address, reason="is not UTF-8 text") from exc
    try:
        lock = parse_lock_file(lock_text)
    except LockFileError as exc:
        msg = f"The method's {LOCK_FILENAME} cannot verify the dependency '{address}' this runtime fetched: {exc.message}"
        raise MethodLockInvalidError(msg) from exc
    folded = address.casefold()
    return [locked for locked_address, locked in lock.packages.items() if locked_address.casefold() == folded]


def _unique_trees(*, trees: Iterable[MethodTree]) -> list[MethodTree]:
    """The trees once each, by digest: two trees of one digest hold the same lock."""
    unique: dict[str, MethodTree] = {}
    for tree in trees:
        unique.setdefault(tree.digest, tree)
    return list(unique.values())


def _tag_names_version(*, tag: str, version: str) -> bool:
    """Whether a tag names a version, written bare or with a leading ``v``, as a shipped copy's tag is matched."""
    return tag in {version, f"v{version}"}


def _mismatch_message(*, fetched_tree: FetchedTree, locked: LockedPackage) -> str:
    """The operator's account of a fetched tree a lock does not record, with the remedy that fits how the copy was found."""
    copy = fetched_tree.copy
    msg = (
        f"The dependency '{copy.address}' differs from the method's {LOCK_FILENAME}: the lock records the tree digest {locked.digest} at "
        f"version {locked.version}, and this runtime fetched version {copy.version}, whose tree digest is {fetched_tree.tree_digest}."
    )
    if copy.pinned_tag is not None and copy.fetched_tag != copy.pinned_tag:
        # The reference pins a tag, but an installed copy an earlier fetch made at another tag answered it.
        fetched_at = f"the tag {copy.fetched_tag}" if copy.fetched_tag is not None else "the repository's default branch"
        msg += (
            f" The reference pins the tag {copy.pinned_tag}, but an installed copy of version {copy.version}, fetched earlier at "
            f"{fetched_at}, was used in place of the pinned version: remove that installed copy so the pinned tag is fetched."
        )
        if not _tag_names_version(tag=copy.pinned_tag, version=locked.version):
            msg += f" The pinned tag does not name the locked version {locked.version} either: pin the reference to it, or lock the method again."
    elif copy.version != locked.version:
        if copy.pinned_tag is None:
            msg += " The lock records another version than the one fetched"
        else:
            msg += f" The reference pins the tag {copy.pinned_tag}, another version than the lock records"
        msg += f": pin the reference to the locked version, or lock the method again to record version {copy.version}."
    return msg


def ensure_fetched_tree_locked(*, fetched_tree: FetchedTree, caller_trees: Iterable[MethodTree]) -> None:
    """Refuse a fetched dependency's tree when a lock of a method calling it records another tree digest for its address.

    Args:
        fetched_tree: The tree the load listed for the copy the runtime fetched.
        caller_trees: The trees of the bundles calling the dependency, whose locks are checked.

    Raises:
        MethodLockInvalidError: A calling method's lock cannot be read.
        MethodLockMismatchError: A calling method's lock records another tree digest for the dependency's address.
    """
    address = fetched_tree.copy.address
    for caller_tree in _unique_trees(trees=caller_trees):
        for locked in _locked_entries(tree=caller_tree, address=address):
            if locked.digest == fetched_tree.tree_digest:
                continue
            msg = _mismatch_message(fetched_tree=fetched_tree, locked=locked)
            raise MethodLockMismatchError(msg).with_params(dependency=address)
