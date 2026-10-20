"""A dependency the runtime fetched is checked against the lock of the method that calls it.

The calling method is a directory on disk, its `methods.lock` at its root beside its `METHODS.toml`. Its bundle calls a
package by address, which no store holds, so it is fetched on a miss, mocked to a local fixture package, and installed
into the (redirected) global methods directory. Nothing reaches the network.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from mthds.method_tree.lister import list_method_tree_at_root
from mthds.package.lock_file import LOCK_FILENAME
from mthds.package.manifest.parser import parse_methods_toml
from mthds.protocol.problem.registry import CoreCode

from pipelex.cli.installed_methods import PROVENANCE_FILENAME
from pipelex.errors.problem import ProblemView
from pipelex.interpreter_hub import get_library_manager
from pipelex.methods.exceptions import MethodLockInvalidError, MethodLockMismatchError
from pipelex.methods.fetching import FetchedMethodPackage
from pipelex.methods.method_ref import parse_method_ref
from tests.integration.pipelex.libraries.test_data import FetchedDependencyLockTestData

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture, MockType

DEP_ALIAS = FetchedDependencyLockTestData.DEP_ALIAS
OTHER_DIGEST = "sha256:" + "0" * 64


@pytest.fixture(name="global_methods_dir")
def global_methods_dir_fixture(tmp_path: Path, mocker: MockerFixture) -> Path:
    """Point the installed stores at empty temporary directories and enable fetch-on-miss."""
    global_dir = tmp_path / "global-methods"
    mocker.patch("pipelex.cli.installed_methods.GLOBAL_METHODS_DIR", global_dir)
    mocker.patch("pipelex.cli.installed_methods.PROJECT_METHODS_DIR", tmp_path / "project-methods")
    mocker.patch("pipelex.methods.fetch_on_miss.is_method_fetch_on_miss_enabled", return_value=True)
    return global_dir


def _write_dependency(*, package_dir: Path) -> str:
    """Write the dependency package into `package_dir` and return its tree digest."""
    package_dir.mkdir(parents=True)
    (package_dir / "METHODS.toml").write_text(FetchedDependencyLockTestData.DEP_MANIFEST, encoding="utf-8")
    (package_dir / "scoring.mthds").write_text(FetchedDependencyLockTestData.DEP_BUNDLE, encoding="utf-8")
    return list_method_tree_at_root(package_dir).digest


def _mock_fetch(*, tmp_path: Path, mocker: MockerFixture) -> tuple[MockType, str]:
    """Serve every fetch of the dependency from a local fixture package; return the mock and the fixture tree's digest."""
    package_dir = tmp_path / "fetched-dep"
    digest = _write_dependency(package_dir=package_dir)
    fetched = FetchedMethodPackage(
        ref=parse_method_ref(DEP_ALIAS),
        full_address=DEP_ALIAS,
        commit_sha="c" * 40,
        clone_dir=tmp_path,
        package_dir=package_dir,
        manifest=parse_methods_toml(FetchedDependencyLockTestData.DEP_MANIFEST),
    )
    return mocker.patch("pipelex.methods.fetch_on_miss.fetch_method_package", return_value=fetched), digest


def _write_caller(*, method_dir: Path, lock: str | None, pipe_ref: str = f"{DEP_ALIAS}->fom_lock_scoring.compute") -> Path:
    """Write the calling method, with its lock at its root when one is given, and return its directory."""
    method_dir.mkdir(parents=True)
    (method_dir / "METHODS.toml").write_text(FetchedDependencyLockTestData.CALLER_MANIFEST, encoding="utf-8")
    (method_dir / "caller.mthds").write_text(FetchedDependencyLockTestData.caller_calling(pipe_ref=pipe_ref), encoding="utf-8")
    if lock is not None:
        (method_dir / LOCK_FILENAME).write_text(lock, encoding="utf-8")
    return method_dir


def _load(*, method_dir: Path, methods_dirs: list[Path] | None = None) -> set[str]:
    """Load the calling method from its directory, as a run or a validation does, and return the dependency aliases loaded."""
    library_manager = get_library_manager()
    library_id, library = library_manager.open_library()
    try:
        library_manager.load_libraries(library_id=library_id, library_dirs=[method_dir], methods_dirs=methods_dirs)
        return set(library.dependency_libraries)
    finally:
        library_manager.teardown(library_id=library_id)


class TestFetchedDependencyLock:
    @pytest.mark.usefixtures("global_methods_dir")
    @pytest.mark.parametrize("lock_kind", ["no lock", "lock naming another address", "lock recording the fetched tree"])
    def test_a_fetched_dependency_the_lock_does_not_contradict_loads(self, tmp_path: Path, mocker: MockerFixture, lock_kind: str) -> None:
        fetch_mock, digest = _mock_fetch(tmp_path=tmp_path, mocker=mocker)
        lock: str | None
        match lock_kind:
            case "no lock":
                lock = None
            case "lock naming another address":
                lock = FetchedDependencyLockTestData.lock_naming(address="github.com/invented/other-lib/ranking", digest=OTHER_DIGEST)
            case _:
                lock = FetchedDependencyLockTestData.lock_naming(address=DEP_ALIAS, digest=digest)
        method_dir = _write_caller(method_dir=tmp_path / "caller", lock=lock)

        assert _load(method_dir=method_dir) == {DEP_ALIAS}
        assert fetch_mock.call_count == 1

    @pytest.mark.usefixtures("global_methods_dir")
    @pytest.mark.parametrize("pipe_ref", [f"{DEP_ALIAS}->fom_lock_scoring.compute", f"{DEP_ALIAS}@v0.1.0->fom_lock_scoring.compute"])
    def test_a_fetched_dependency_whose_tree_the_lock_does_not_record_is_refused(self, tmp_path: Path, mocker: MockerFixture, pipe_ref: str) -> None:
        """A reference pinning a tag is looked up in the lock by its address alone, as the installed stores are."""
        _fetch_mock, digest = _mock_fetch(tmp_path=tmp_path, mocker=mocker)
        lock = FetchedDependencyLockTestData.lock_naming(address=DEP_ALIAS, digest=OTHER_DIGEST)
        method_dir = _write_caller(method_dir=tmp_path / "caller", lock=lock, pipe_ref=pipe_ref)

        with pytest.raises(MethodLockMismatchError) as exc_info:
            _load(method_dir=method_dir)

        problem = exc_info.value.to_problem(view=ProblemView.CALLER)
        assert problem.code == CoreCode.SECURITY_INTEGRITY_MISMATCH
        assert problem.params is not None
        assert problem.params.as_wire() == {"dependency": DEP_ALIAS}
        assert OTHER_DIGEST in exc_info.value.message
        assert digest in exc_info.value.message

    def test_the_copy_an_earlier_fetch_installed_is_checked_too(self, global_methods_dir: Path, tmp_path: Path, mocker: MockerFixture) -> None:
        """A first load with no lock installs the fetched copy; a second, locked to another tree, finds it installed and is refused."""
        fetch_mock, _digest = _mock_fetch(tmp_path=tmp_path, mocker=mocker)
        assert _load(method_dir=_write_caller(method_dir=tmp_path / "unlocked-caller", lock=None)) == {DEP_ALIAS}
        assert (global_methods_dir / "scoring" / PROVENANCE_FILENAME).is_file()

        lock = FetchedDependencyLockTestData.lock_naming(address=DEP_ALIAS, digest=OTHER_DIGEST)
        with pytest.raises(MethodLockMismatchError):
            _load(method_dir=_write_caller(method_dir=tmp_path / "locked-caller", lock=lock))
        assert fetch_mock.call_count == 1

    @pytest.mark.usefixtures("global_methods_dir")
    def test_a_lock_that_cannot_be_read_refuses_a_fetched_dependency(self, tmp_path: Path, mocker: MockerFixture) -> None:
        _mock_fetch(tmp_path=tmp_path, mocker=mocker)
        method_dir = _write_caller(method_dir=tmp_path / "caller", lock=FetchedDependencyLockTestData.legacy_lock_naming(address=DEP_ALIAS))

        with pytest.raises(MethodLockInvalidError):
            _load(method_dir=method_dir)

    @pytest.mark.usefixtures("global_methods_dir")
    def test_a_shipped_dependency_is_not_checked(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """A package the method ships travels with its lock, from its author: the runtime fetched nothing to verify."""
        fetch_mock, _digest = _mock_fetch(tmp_path=tmp_path, mocker=mocker)
        methods_dir = tmp_path / "shipped-methods"
        _write_dependency(package_dir=methods_dir / "scoring")
        lock = FetchedDependencyLockTestData.lock_naming(address=DEP_ALIAS, digest=OTHER_DIGEST)
        method_dir = _write_caller(method_dir=tmp_path / "caller", lock=lock)

        assert _load(method_dir=method_dir, methods_dirs=[methods_dir]) == {DEP_ALIAS}
        fetch_mock.assert_not_called()

    def test_a_copy_installed_without_a_fetch_provenance_is_not_checked(
        self, global_methods_dir: Path, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        """A copy another installer wrote, such as `mthds install`, which verifies the lock itself, is not the runtime's fetch."""
        fetch_mock, _digest = _mock_fetch(tmp_path=tmp_path, mocker=mocker)
        _write_dependency(package_dir=global_methods_dir / "scoring")
        lock = FetchedDependencyLockTestData.lock_naming(address=DEP_ALIAS, digest=OTHER_DIGEST)
        method_dir = _write_caller(method_dir=tmp_path / "caller", lock=lock)

        assert _load(method_dir=method_dir) == {DEP_ALIAS}
        fetch_mock.assert_not_called()
