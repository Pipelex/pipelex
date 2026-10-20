"""Check a dependency the runtime fetched against the `methods.lock` of the method that calls it.

A method's `methods.lock` (`mthds/docs/spec/lock-format.md`) records, for each remote dependency, the version it was
locked at and the tree digest of the package's tree (`mthds/docs/spec/method-tree.md`, "The Tree Digest"). It lies at the
root of the method's tree, beside `METHODS.toml`, and it is a file of that tree, so it travels with the method wherever
the method goes: in a tree a caller sends, in a package fetched by `method_ref`, and in a method's directory on disk.

When a load resolves a package a bundle calls by address from a copy the runtime fetched, whether it fetched it for this
load or an earlier fetch installed it (the copy carries the fetch's provenance), the tree the load lists for that package
is checked against the lock at the root of every tree whose bundles call it. A lock that does not name the package's
address, or no lock at all, checks nothing; a lock naming it with another digest refuses the load
(`MethodLockMismatchError`, the core code `security.integrity_mismatch`), whatever version it names, since the lock
verifies what was fetched and never chooses it. A package the method ships with itself is not checked: it travels with
the lock, from the same author, so there is nothing fetched to verify.

The lock is read with the `mthds` package's own parser, and only when there is a fetched dependency to check, so a lock
that cannot be read refuses only a load that needs it (`MethodLockInvalidError`, `method.package_invalid` with the reason
`lock_invalid`), a lock written before tree digests among them, as the standard requires.
"""

from collections.abc import Iterable
from typing import NamedTuple

from mthds.method_tree.models import MethodTree
from mthds.package.exceptions import LockFileError
from mthds.package.lock_file import LOCK_FILENAME, LockedPackage, parse_lock_file

from pipelex.core.method_trees.method_file_store import LOCAL_METHOD_FILES
from pipelex.methods.exceptions import MethodLockInvalidError, MethodLockMismatchError


class FetchedDependency(NamedTuple):
    """A dependency the runtime fetched for a load: its address, its version, and the trees of the bundles that call it."""

    address: str
    version: str
    caller_trees: tuple[MethodTree, ...]


def _lock_bytes(*, tree: MethodTree) -> bytes | None:
    """The bytes of the lock at the root of `tree`, or None when the tree holds none.

    A tree listed from a directory is read there; a tree of files held in memory, such as the files submitted beside a
    method's content strings, is read from the method file store, which holds it for the load.
    """
    if LOCK_FILENAME not in tree.members:
        return None
    if tree.directory is not None:
        return tree.file_location(LOCK_FILENAME).read_bytes()
    return LOCAL_METHOD_FILES.read_held_file(tree_digest=tree.digest, tree_path=LOCK_FILENAME)


def _locked_entries(*, tree: MethodTree, address: str) -> list[LockedPackage]:
    """The entries the lock at the root of `tree` records for `address`, compared without regard to case.

    Raises:
        MethodLockInvalidError: The lock is not UTF-8 text, does not parse, or holds an entry the lock format refuses.
    """
    lock_bytes = _lock_bytes(tree=tree)
    if lock_bytes is None:
        return []
    try:
        lock_text = lock_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        msg = f"The method's {LOCK_FILENAME} is not UTF-8 text, so it cannot verify the dependency '{address}' this runtime fetched."
        raise MethodLockInvalidError(msg) from exc
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


def ensure_fetched_tree_locked(*, dependency: FetchedDependency, tree_digest: str) -> None:
    """Refuse a fetched dependency whose tree digest differs from one a lock of the methods calling it records.

    Args:
        dependency: The dependency the runtime fetched, with the trees of the bundles that call it.
        tree_digest: The digest of the dependency's tree, as the load listed it.

    Raises:
        MethodLockInvalidError: A calling method's lock cannot be read.
        MethodLockMismatchError: A calling method's lock records another tree digest for the dependency's address.
    """
    for caller_tree in _unique_trees(trees=dependency.caller_trees):
        for locked in _locked_entries(tree=caller_tree, address=dependency.address):
            if locked.digest == tree_digest:
                continue
            msg = (
                f"The dependency '{dependency.address}' differs from the method's {LOCK_FILENAME}: the lock records the tree digest "
                f"{locked.digest} at version {locked.version}, and this runtime fetched version {dependency.version}, whose tree "
                f"digest is {tree_digest}."
            )
            if dependency.version != locked.version:
                msg += (
                    f" The lock records another version than the one fetched: pin the reference to the locked version, or lock the "
                    f"method again to record version {dependency.version}."
                )
            raise MethodLockMismatchError(msg).with_params(dependency=dependency.address)
