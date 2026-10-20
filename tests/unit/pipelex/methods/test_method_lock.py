from collections.abc import Generator
from pathlib import Path

import pytest
from mthds.method_tree.lister import list_method_tree_at_root
from mthds.method_tree.models import MethodTree
from mthds.package.lock_file import LOCK_FILENAME
from mthds.protocol.problem.registry import CoreCode, ProblemDomain

from pipelex.core.method_trees.method_file_store import LOCAL_METHOD_FILES, HeldFile
from pipelex.errors.problem import ProblemView
from pipelex.methods.exceptions import MethodLockInvalidError, MethodLockMismatchError
from pipelex.methods.method_lock import FetchedDependency, ensure_fetched_tree_locked
from pipelex.methods.package_reason import MethodPackageReason
from tests.unit.pipelex.methods.test_data import MethodLockTestData

_HOLDER = "method-lock-tests"


@pytest.fixture(name="held_files")
def held_files_fixture() -> Generator[None, None, None]:
    yield
    LOCAL_METHOD_FILES.release(holder=_HOLDER)


def _tree(*, root: Path, lock: str | bytes | None) -> MethodTree:
    """The tree of a calling method on disk: a bundle, and the lock at its root when one is given."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "main.mthds").write_text(MethodLockTestData.BUNDLE, encoding="utf-8")
    if isinstance(lock, str):
        (root / LOCK_FILENAME).write_text(lock, encoding="utf-8")
    elif isinstance(lock, bytes):
        (root / LOCK_FILENAME).write_bytes(lock)
    return list_method_tree_at_root(root)


def _fetched(*, caller_trees: list[MethodTree], version: str = MethodLockTestData.FETCHED_VERSION) -> FetchedDependency:
    return FetchedDependency(address=MethodLockTestData.ADDRESS, version=version, caller_trees=tuple(caller_trees))


class TestMethodLock:
    def test_a_caller_without_a_lock_checks_nothing(self, tmp_path: Path) -> None:
        tree = _tree(root=tmp_path / "caller", lock=None)

        ensure_fetched_tree_locked(dependency=_fetched(caller_trees=[tree]), tree_digest=MethodLockTestData.FETCHED_DIGEST)

    def test_a_lock_that_does_not_name_the_address_checks_nothing(self, tmp_path: Path) -> None:
        lock = MethodLockTestData.lock_naming(address=MethodLockTestData.OTHER_ADDRESS, digest=MethodLockTestData.LOCKED_DIGEST)
        tree = _tree(root=tmp_path / "caller", lock=lock)

        ensure_fetched_tree_locked(dependency=_fetched(caller_trees=[tree]), tree_digest=MethodLockTestData.FETCHED_DIGEST)

    @pytest.mark.parametrize("locked_address", [MethodLockTestData.ADDRESS, MethodLockTestData.ADDRESS_IN_OTHER_CASE])
    def test_a_fetched_tree_the_lock_records_passes(self, tmp_path: Path, locked_address: str) -> None:
        """The address is compared without regard to case, as the installed stores and a fetch match it."""
        lock = MethodLockTestData.lock_naming(address=locked_address, digest=MethodLockTestData.FETCHED_DIGEST)
        tree = _tree(root=tmp_path / "caller", lock=lock)

        ensure_fetched_tree_locked(dependency=_fetched(caller_trees=[tree]), tree_digest=MethodLockTestData.FETCHED_DIGEST)

    def test_a_fetched_tree_the_lock_does_not_record_is_refused(self, tmp_path: Path) -> None:
        lock = MethodLockTestData.lock_naming(
            address=MethodLockTestData.ADDRESS, digest=MethodLockTestData.LOCKED_DIGEST, version=MethodLockTestData.FETCHED_VERSION
        )
        tree = _tree(root=tmp_path / "caller", lock=lock)

        with pytest.raises(MethodLockMismatchError) as exc_info:
            ensure_fetched_tree_locked(dependency=_fetched(caller_trees=[tree]), tree_digest=MethodLockTestData.FETCHED_DIGEST)

        problem = exc_info.value.to_problem(view=ProblemView.OPERATOR)
        assert problem.code == CoreCode.SECURITY_INTEGRITY_MISMATCH
        assert problem.domain == ProblemDomain.METHOD
        assert problem.params is not None
        assert problem.params.as_wire() == {"dependency": MethodLockTestData.ADDRESS}
        # The operator reads the address, the digest the lock records and the digest of what was fetched.
        message = exc_info.value.message
        assert MethodLockTestData.ADDRESS in message
        assert MethodLockTestData.LOCKED_DIGEST in message
        assert MethodLockTestData.FETCHED_DIGEST in message
        assert str(tmp_path) not in message

    def test_a_lock_naming_another_version_is_checked_all_the_same(self, tmp_path: Path) -> None:
        """The lock verifies what was fetched, never chooses it: another version than the locked one is refused, both named."""
        lock = MethodLockTestData.lock_naming(address=MethodLockTestData.ADDRESS, digest=MethodLockTestData.LOCKED_DIGEST)
        tree = _tree(root=tmp_path / "caller", lock=lock)

        with pytest.raises(MethodLockMismatchError) as exc_info:
            ensure_fetched_tree_locked(dependency=_fetched(caller_trees=[tree]), tree_digest=MethodLockTestData.FETCHED_DIGEST)

        message = exc_info.value.message
        assert f"version {MethodLockTestData.LOCKED_VERSION}" in message
        assert f"version {MethodLockTestData.FETCHED_VERSION}" in message

    def test_every_calling_tree_s_lock_is_checked(self, tmp_path: Path) -> None:
        """Two methods of one load call the dependency: the lock of either refuses a tree it does not record."""
        matching = MethodLockTestData.lock_naming(address=MethodLockTestData.ADDRESS, digest=MethodLockTestData.FETCHED_DIGEST)
        differing = MethodLockTestData.lock_naming(address=MethodLockTestData.ADDRESS, digest=MethodLockTestData.LOCKED_DIGEST)
        trees = [_tree(root=tmp_path / "first", lock=matching), _tree(root=tmp_path / "second", lock=differing)]

        with pytest.raises(MethodLockMismatchError):
            ensure_fetched_tree_locked(dependency=_fetched(caller_trees=trees), tree_digest=MethodLockTestData.FETCHED_DIGEST)

    @pytest.mark.usefixtures("held_files")
    def test_the_lock_of_a_tree_held_in_memory_is_read_from_the_store(self) -> None:
        """Files submitted beside content strings make a tree with no directory, whose lock the method file store holds."""
        lock = MethodLockTestData.lock_naming(address=MethodLockTestData.ADDRESS, digest=MethodLockTestData.LOCKED_DIGEST)
        tree = LOCAL_METHOD_FILES.hold_files(
            holder=_HOLDER,
            files={LOCK_FILENAME: HeldFile.of_bytes(data=lock.encode()), "notes.md": HeldFile.of_bytes(data=b"notes\n")},
        )
        assert tree.directory is None

        with pytest.raises(MethodLockMismatchError):
            ensure_fetched_tree_locked(dependency=_fetched(caller_trees=[tree]), tree_digest=MethodLockTestData.FETCHED_DIGEST)

    @pytest.mark.parametrize(
        ("lock", "finding"),
        [
            (MethodLockTestData.legacy_lock_naming(address=MethodLockTestData.ADDRESS), "predates tree digests"),
            ('["github.com/invented/locked-lib/scoring"\nversion = "1.0.0"\n', "Invalid TOML"),
            (b'["github.com/invented/locked-lib/scoring"]\nversion = "\xff"\n', "not UTF-8"),
        ],
    )
    def test_a_lock_that_cannot_be_read_is_refused(self, tmp_path: Path, lock: str | bytes, finding: str) -> None:
        tree = _tree(root=tmp_path / "caller", lock=lock)

        with pytest.raises(MethodLockInvalidError) as exc_info:
            ensure_fetched_tree_locked(dependency=_fetched(caller_trees=[tree]), tree_digest=MethodLockTestData.FETCHED_DIGEST)

        assert finding in exc_info.value.message
        problem = exc_info.value.to_problem(view=ProblemView.CALLER)
        assert problem.code == CoreCode.METHOD_PACKAGE_INVALID
        assert problem.params is not None
        assert problem.params.as_wire() == {"reason": MethodPackageReason.LOCK_INVALID, "path": LOCK_FILENAME}
