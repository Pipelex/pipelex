"""A fetched package is read from its commit's git objects, never from the clone's working tree.

The clone cache is stubbed with a local git repository (`install_method_package` in conftest). These pin what the
commit holds against what the working tree holds: a file left uncommitted is no file of the package, a committed
symbolic link is refused, named by its path in the package and the package's address, and the tree's digest rides the
provenance.
"""

import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path

import pytest
from mthds.method_tree.digest import digest_of_contents
from pipelex.methods.exceptions import MethodPackageSymlinkError
from pipelex.methods.package_reason import MethodPackageReason
from pytest_mock import MockerFixture

from pipelex_api.exceptions import RequestMethodError
from pipelex_api.method_source import fetch_method_mthds_files, fetched_method
from tests.unit._constants import STUB_METHOD_ADDRESS, STUB_METHOD_MANIFEST, VALID_MTHDS
from tests.unit._problems import problem_of

_METHOD_REF = f"{STUB_METHOD_ADDRESS}@v0.1.0"


def _commit_all(*, package_dir: Path) -> None:
    clone_root = package_dir.parent.parent
    git_identity = ["-c", "user.name=stub", "-c", "user.email=stub@example.com", "-c", "commit.gpgsign=false"]
    for args in (["add", "--all"], [*git_identity, "commit", "--quiet", "-m", "more"]):
        subprocess.run(["git", "-C", str(clone_root), *args], check=True, capture_output=True)  # noqa: S603, S607


class TestMethodSourceGit:
    def test_the_package_is_its_commits_files_and_its_digest_rides_the_provenance(self, install_method_package: Callable[..., Path]) -> None:
        package_dir = install_method_package(files={"documents.mthds": VALID_MTHDS, "templates/invoice.html": "<h1>Invoice</h1>"})
        # Written after the commit, in the clone's working tree only.
        (package_dir / "uncommitted.txt").write_text("not in the commit", encoding="utf-8")
        (package_dir / "documents.mthds").write_text("edited after the commit", encoding="utf-8")

        fetched = fetched_method(_METHOD_REF)

        contents = fetched.request_method.tree.contents
        assert contents == {
            "METHODS.toml": STUB_METHOD_MANIFEST.encode("utf-8"),
            "documents.mthds": VALID_MTHDS.encode("utf-8"),
            "templates/invoice.html": b"<h1>Invoice</h1>",
        }
        assert fetched.request_method.dependencies == {}
        assert fetched.provenance.tree_digest == digest_of_contents(contents)
        assert fetched.label == f"'{STUB_METHOD_ADDRESS}'"

    def test_a_committed_symbolic_link_is_refused_by_tree_path_and_address(self, install_method_package: Callable[..., Path]) -> None:
        package_dir = install_method_package(files={"documents.mthds": VALID_MTHDS})
        (package_dir / "linked.mthds").symlink_to("documents.mthds")
        _commit_all(package_dir=package_dir)

        with pytest.raises(MethodPackageSymlinkError) as exc_info:
            fetched_method(_METHOD_REF)

        message = str(exc_info.value)
        assert "linked.mthds" in message
        assert STUB_METHOD_ADDRESS in message
        assert "pipelex-package-" not in message
        assert tempfile.gettempdir() not in message

    def test_a_fetched_mthds_file_past_its_limit_names_that_limit(self, install_method_package: Callable[..., Path], mocker: MockerFixture) -> None:
        """The tooling routes' limit on one `.mthds` file is its own reason, never the tree's per-file limit."""
        install_method_package(files={"documents.mthds": VALID_MTHDS})
        mocker.patch("pipelex_api.method_source.MAX_MTHDS_FILE_BYTES", len(VALID_MTHDS.encode("utf-8")) - 1)

        with pytest.raises(RequestMethodError) as exc_info:
            fetch_method_mthds_files(_METHOD_REF)

        assert problem_of(exc_info.value)["params"] == {
            "reason": MethodPackageReason.MTHDS_FILE_TOO_LARGE,
            "path": "documents.mthds",
            "limit": len(VALID_MTHDS.encode("utf-8")) - 1,
        }
