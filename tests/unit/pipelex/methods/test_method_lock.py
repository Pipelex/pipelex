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
from pipelex.methods.method_lock import FetchedCopy, FetchedTree, ensure_fetched_tree_locked
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


def _fetched(
    *,
    version: str = MethodLockTestData.FETCHED_VERSION,
    pinned_tag: str | None = None,
    fetched_tag: str | None = None,
) -> FetchedTree:
    """The tree listed for a copy of the dependency this runtime fetched, at `version`, as a reference pinning `pinned_tag` found it."""
    copy = FetchedCopy(address=MethodLockTestData.ADDRESS, version=version, pinned_tag=pinned_tag, fetched_tag=fetched_tag)
    return FetchedTree(copy=copy, tree_digest=MethodLockTestData.FETCHED_DIGEST)


class TestMethodLock:
    def test_a_caller_without_a_lock_checks_nothing(self, tmp_path: Path) -> None:
        tree = _tree(root=tmp_path / "caller", lock=None)

        ensure_fetched_tree_locked(fetched_tree=_fetched(), caller_trees=[tree])

    def test_a_lock_that_does_not_name_the_address_checks_nothing(self, tmp_path: Path) -> None:
        lock = MethodLockTestData.lock_naming(address=MethodLockTestData.OTHER_ADDRESS, digest=MethodLockTestData.LOCKED_DIGEST)
        tree = _tree(root=tmp_path / "caller", lock=lock)

        ensure_fetched_tree_locked(fetched_tree=_fetched(), caller_trees=[tree])

    @pytest.mark.parametrize("locked_address", [MethodLockTestData.ADDRESS, MethodLockTestData.ADDRESS_IN_OTHER_CASE])
    def test_a_fetched_tree_the_lock_records_passes(self, tmp_path: Path, locked_address: str) -> None:
        """The address is compared without regard to case, as the installed stores and a fetch match it."""
        lock = MethodLockTestData.lock_naming(address=locked_address, digest=MethodLockTestData.FETCHED_DIGEST)
        tree = _tree(root=tmp_path / "caller", lock=lock)

        ensure_fetched_tree_locked(fetched_tree=_fetched(), caller_trees=[tree])

    def test_a_fetched_tree_the_lock_does_not_record_is_refused(self, tmp_path: Path) -> None:
        lock = MethodLockTestData.lock_naming(
            address=MethodLockTestData.ADDRESS, digest=MethodLockTestData.LOCKED_DIGEST, version=MethodLockTestData.FETCHED_VERSION
        )
        tree = _tree(root=tmp_path / "caller", lock=lock)

        with pytest.raises(MethodLockMismatchError) as exc_info:
            ensure_fetched_tree_locked(fetched_tree=_fetched(), caller_trees=[tree])

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

    @pytest.mark.parametrize(
        ("topic", "fetched", "present", "absent"),
        MethodLockTestData.MISMATCH_MESSAGE_CASES,
    )
    def test_the_refusal_names_the_remedy_that_fits_how_the_copy_was_found(
        self, tmp_path: Path, topic: str, fetched: tuple[str, str | None, str | None], present: list[str], absent: list[str]
    ) -> None:
        """The lock verifies what was fetched, never chooses it: another version than the locked one is refused, both named,
        and the remedy is the one that fits, an installed copy used in place of a pinned tag being named as such.
        """
        lock = MethodLockTestData.lock_naming(address=MethodLockTestData.ADDRESS, digest=MethodLockTestData.LOCKED_DIGEST)
        tree = _tree(root=tmp_path / "caller", lock=lock)
        version, pinned_tag, fetched_tag = fetched

        with pytest.raises(MethodLockMismatchError) as exc_info:
            ensure_fetched_tree_locked(fetched_tree=_fetched(version=version, pinned_tag=pinned_tag, fetched_tag=fetched_tag), caller_trees=[tree])

        message = exc_info.value.message
        assert f"at version {MethodLockTestData.LOCKED_VERSION}" in message, topic
        assert f"fetched version {version}" in message, topic
        for fragment in present:
            assert fragment in message, (topic, fragment, message)
        for fragment in absent:
            assert fragment not in message, (topic, fragment, message)

    def test_every_calling_tree_s_lock_is_checked(self, tmp_path: Path) -> None:
        """Two methods of one load call the dependency: the lock of either refuses a tree it does not record."""
        matching = MethodLockTestData.lock_naming(address=MethodLockTestData.ADDRESS, digest=MethodLockTestData.FETCHED_DIGEST)
        differing = MethodLockTestData.lock_naming(address=MethodLockTestData.ADDRESS, digest=MethodLockTestData.LOCKED_DIGEST)
        trees = [_tree(root=tmp_path / "first", lock=matching), _tree(root=tmp_path / "second", lock=differing)]

        with pytest.raises(MethodLockMismatchError):
            ensure_fetched_tree_locked(fetched_tree=_fetched(), caller_trees=trees)

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
            ensure_fetched_tree_locked(fetched_tree=_fetched(), caller_trees=[tree])

    def test_a_lock_listed_in_a_tree_no_longer_held_is_refused(self) -> None:
        """A lock the tree lists is never skipped as absent: when the store no longer holds its bytes, the check refuses."""
        lock = MethodLockTestData.lock_naming(address=MethodLockTestData.ADDRESS, digest=MethodLockTestData.FETCHED_DIGEST)
        tree = LOCAL_METHOD_FILES.hold_files(holder=_HOLDER, files={LOCK_FILENAME: HeldFile.of_bytes(data=lock.encode())})
        LOCAL_METHOD_FILES.release(holder=_HOLDER)

        with pytest.raises(MethodLockInvalidError) as exc_info:
            ensure_fetched_tree_locked(fetched_tree=_fetched(), caller_trees=[tree])

        assert "not held for this load" in exc_info.value.message

    @pytest.mark.parametrize(
        ("is_removed", "finding"),
        [
            (True, "cannot be read"),
            (False, "changed since the method's tree was listed"),
        ],
    )
    def test_a_lock_on_disk_that_moved_after_the_listing_is_refused(self, tmp_path: Path, is_removed: bool, finding: str) -> None:
        """The lock read is the one the tree listed: removed or rewritten since, it is refused, never skipped or trusted."""
        lock = MethodLockTestData.lock_naming(address=MethodLockTestData.ADDRESS, digest=MethodLockTestData.FETCHED_DIGEST)
        tree = _tree(root=tmp_path / "caller", lock=lock)
        lock_path = tmp_path / "caller" / LOCK_FILENAME
        if is_removed:
            lock_path.unlink()
        else:
            lock_path.write_text(
                MethodLockTestData.lock_naming(address=MethodLockTestData.OTHER_ADDRESS, digest=MethodLockTestData.LOCKED_DIGEST),
                encoding="utf-8",
            )

        with pytest.raises(MethodLockInvalidError) as exc_info:
            ensure_fetched_tree_locked(fetched_tree=_fetched(), caller_trees=[tree])

        assert finding in exc_info.value.message
        assert str(tmp_path) not in exc_info.value.message
        problem = exc_info.value.to_problem(view=ProblemView.CALLER)
        assert problem.code == CoreCode.METHOD_PACKAGE_INVALID

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
            ensure_fetched_tree_locked(fetched_tree=_fetched(), caller_trees=[tree])

        assert finding in exc_info.value.message
        problem = exc_info.value.to_problem(view=ProblemView.CALLER)
        assert problem.code == CoreCode.METHOD_PACKAGE_INVALID
        assert problem.params is not None
        assert problem.params.as_wire() == {"reason": MethodPackageReason.LOCK_INVALID, "path": LOCK_FILENAME}
