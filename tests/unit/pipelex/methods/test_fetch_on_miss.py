"""Unit tests for resolve_address_based_method: hit, miss-and-fetch, disabled, and failure diagnostics."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from mthds.package.discovery import MANIFEST_FILENAME
from mthds.package.manifest.parser import parse_methods_toml

from pipelex.cli.installed_methods import PROVENANCE_FILENAME, install_method_package
from pipelex.methods.exceptions import (
    MethodDependencyFetchError,
    MethodFetchDisabledError,
    MethodFetchError,
    MethodInstallError,
    MethodStructuresRefusedError,
)
from pipelex.methods.fetch_on_miss import resolve_address_based_method
from pipelex.methods.fetching import FetchedMethodPackage, MethodProvenance
from pipelex.methods.method_ref import parse_method_ref

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture

FULL_ADDRESS = "github.com/pipelex-tests/fom-methods/scoring"
COMMIT_SHA = "b" * 40

MANIFEST = """\
[package]
name = "scoring"
address = "github.com/pipelex-tests/fom-methods"
version = "0.1.0"
description = "A test package for fetch-on-miss tests"
main_pipe = "compute"

[exports.scoring]
pipes = ["compute"]
"""


def _make_package_dir(base: Path) -> Path:
    package_dir = base / "fetched-pkg"
    package_dir.mkdir(parents=True)
    (package_dir / MANIFEST_FILENAME).write_text(MANIFEST, encoding="utf-8")
    (package_dir / "scoring.mthds").write_text("# placeholder", encoding="utf-8")
    return package_dir


def _make_fetched(package_dir: Path, *, ref_str: str = f"{FULL_ADDRESS}@v0.1.0") -> FetchedMethodPackage:
    ref = parse_method_ref(ref_str)
    return FetchedMethodPackage(
        ref=ref,
        full_address=FULL_ADDRESS,
        commit_sha=COMMIT_SHA,
        clone_dir=package_dir.parent,
        package_dir=package_dir,
        manifest=parse_methods_toml(MANIFEST),
    )


@pytest.fixture(name="isolated_methods_dirs")
def isolated_methods_dirs_fixture(tmp_path: Path, mocker: MockerFixture) -> Path:
    """Point the global and project methods directories at empty tmp locations."""
    global_dir = tmp_path / "global-methods"
    mocker.patch("pipelex.cli.installed_methods.GLOBAL_METHODS_DIR", global_dir)
    mocker.patch("pipelex.cli.installed_methods.PROJECT_METHODS_DIR", tmp_path / "project-methods")
    return global_dir


class TestResolveAddressBasedMethod:
    def test_installed_hit_returns_without_fetching(self, isolated_methods_dirs: Path, tmp_path: Path, mocker: MockerFixture) -> None:
        """An installed method short-circuits the fetch entirely."""
        package_dir = _make_package_dir(tmp_path)
        install_method_package(package_dir=package_dir, name="scoring", methods_dir=isolated_methods_dirs)
        fetch_mock = mocker.patch("pipelex.methods.fetch_on_miss.fetch_method_package")

        resolved = resolve_address_based_method(full_address=FULL_ADDRESS)

        assert resolved.path == (isolated_methods_dirs / "scoring").resolve()
        fetch_mock.assert_not_called()

    def test_tag_pinned_reference_uses_the_installed_copy(self, isolated_methods_dirs: Path, tmp_path: Path, mocker: MockerFixture) -> None:
        """A `@tag` reference resolves against the installed store by tagless address (installed wins)."""
        package_dir = _make_package_dir(tmp_path)
        install_method_package(package_dir=package_dir, name="scoring", methods_dir=isolated_methods_dirs)
        fetch_mock = mocker.patch("pipelex.methods.fetch_on_miss.fetch_method_package")

        resolved = resolve_address_based_method(full_address=f"{FULL_ADDRESS}@v9.9.9")

        assert resolved.path == (isolated_methods_dirs / "scoring").resolve()
        fetch_mock.assert_not_called()

    @pytest.mark.usefixtures("isolated_methods_dirs")
    def test_miss_with_fetch_disabled_raises_the_disabled_diagnostic(self, mocker: MockerFixture) -> None:
        """A miss with fetch-on-miss disabled names the address, the switch, and the manual remedy."""
        mocker.patch("pipelex.methods.fetch_on_miss.is_method_fetch_on_miss_enabled", return_value=False)
        fetch_mock = mocker.patch("pipelex.methods.fetch_on_miss.fetch_method_package")

        with pytest.raises(MethodFetchDisabledError) as exc_info:
            resolve_address_based_method(full_address=FULL_ADDRESS)

        message = str(exc_info.value)
        assert FULL_ADDRESS in message
        assert "PIPELEX_METHODS_FETCH_ON_MISS" in message
        assert "fetch_on_miss" in message
        assert "install the method manually" in message
        fetch_mock.assert_not_called()

    @pytest.mark.usefixtures("isolated_methods_dirs")
    def test_miss_with_failing_fetch_raises_the_failure_diagnostic(self, mocker: MockerFixture) -> None:
        """A failed fetch surfaces as a diagnostic naming the address, with the fetch error as cause."""
        mocker.patch("pipelex.methods.fetch_on_miss.is_method_fetch_on_miss_enabled", return_value=True)
        fetch_error = MethodFetchError("Failed to fetch method 'github.com/...': clone timed out")
        mocker.patch("pipelex.methods.fetch_on_miss.fetch_method_package", side_effect=fetch_error)

        with pytest.raises(MethodDependencyFetchError) as exc_info:
            resolve_address_based_method(full_address=f"{FULL_ADDRESS}@v0.1.0")

        message = str(exc_info.value)
        assert f"{FULL_ADDRESS}@v0.1.0" in message
        assert "fetching it failed" in message
        assert "clone timed out" in message
        assert exc_info.value.__cause__ is fetch_error

    @pytest.mark.usefixtures("isolated_methods_dirs")
    def test_miss_with_unfetchable_address_raises_a_diagnostic(self) -> None:
        """An address-based alias that is not a fetchable reference gets a diagnostic, not a silent pass."""
        with pytest.raises(MethodDependencyFetchError, match="cannot be fetched"):
            resolve_address_based_method(full_address="example.com/foo/bar")

    def test_miss_fetches_installs_and_returns_the_method(self, isolated_methods_dirs: Path, tmp_path: Path, mocker: MockerFixture) -> None:
        """The full miss path: fetch, install with provenance, return — and the next resolve hits the install."""
        mocker.patch("pipelex.methods.fetch_on_miss.is_method_fetch_on_miss_enabled", return_value=True)
        package_dir = _make_package_dir(tmp_path)
        fetched = _make_fetched(package_dir)
        fetch_mock = mocker.patch("pipelex.methods.fetch_on_miss.fetch_method_package", return_value=fetched)

        resolved = resolve_address_based_method(full_address=f"{FULL_ADDRESS}@v0.1.0")

        assert resolved.path == (isolated_methods_dirs / "scoring").resolve()
        assert (resolved.path / "scoring.mthds").read_text(encoding="utf-8") == "# placeholder"
        assert resolved.provenance is not None
        assert resolved.provenance.commit_sha == COMMIT_SHA
        assert resolved.provenance.tag == "v0.1.0"
        assert (resolved.path / PROVENANCE_FILENAME).is_file()
        assert fetch_mock.call_count == 1

        resolved_again = resolve_address_based_method(full_address=FULL_ADDRESS)
        assert resolved_again.path == resolved.path
        assert fetch_mock.call_count == 1

    def test_bare_name_collision_across_addresses_is_a_loud_error(self, isolated_methods_dirs: Path, tmp_path: Path, mocker: MockerFixture) -> None:
        """Two packages sharing the bare name never silently load or overwrite each other — the collision names both addresses."""
        package_dir = _make_package_dir(tmp_path)
        install_method_package(package_dir=package_dir, name="scoring", full_address=FULL_ADDRESS, methods_dir=isolated_methods_dirs)

        other_address = "github.com/other-org/other-methods/scoring"
        other_manifest = MANIFEST.replace("github.com/pipelex-tests/fom-methods", "github.com/other-org/other-methods")
        other_dir = tmp_path / "other-pkg"
        other_dir.mkdir()
        (other_dir / MANIFEST_FILENAME).write_text(other_manifest, encoding="utf-8")
        (other_dir / "scoring.mthds").write_text("# other", encoding="utf-8")
        other_fetched = FetchedMethodPackage(
            ref=parse_method_ref(other_address),
            full_address=other_address,
            commit_sha=COMMIT_SHA,
            clone_dir=tmp_path,
            package_dir=other_dir,
            manifest=parse_methods_toml(other_manifest),
        )
        mocker.patch("pipelex.methods.fetch_on_miss.is_method_fetch_on_miss_enabled", return_value=True)
        mocker.patch("pipelex.methods.fetch_on_miss.fetch_method_package", return_value=other_fetched)

        with pytest.raises(MethodInstallError) as exc_info:
            resolve_address_based_method(full_address=other_address)

        message = str(exc_info.value)
        assert other_address in message
        assert FULL_ADDRESS in message
        assert str(isolated_methods_dirs / "scoring") in message
        installed_bundle = (isolated_methods_dirs / "scoring" / "scoring.mthds").read_text(encoding="utf-8")
        assert installed_bundle == "# placeholder", "the first package's install was not overwritten"

    @pytest.mark.usefixtures("isolated_methods_dirs")
    def test_sandbox_hosted_fetch_refuses_structures_and_the_refusal_surfaces_unwrapped(self, mocker: MockerFixture) -> None:
        """On a sandbox-hosted deployment the fetch hard-refuses structure-declaring packages, and the rule-naming error is not swallowed."""
        mocker.patch("pipelex.methods.fetch_on_miss.is_method_fetch_on_miss_enabled", return_value=True)
        mocker.patch("pipelex.methods.fetch_on_miss.is_pipe_func_sandbox_hosted", return_value=True)
        refusal = MethodStructuresRefusedError("hosted execution accepts MTHDS concepts and sandboxed PipeFuncs, not in-process Python")
        fetch_mock = mocker.patch("pipelex.methods.fetch_on_miss.fetch_method_package", side_effect=refusal)

        with pytest.raises(MethodStructuresRefusedError) as exc_info:
            resolve_address_based_method(full_address=FULL_ADDRESS)

        assert exc_info.value is refusal
        assert fetch_mock.call_args.kwargs["refuse_structures"] is True

    @pytest.mark.usefixtures("isolated_methods_dirs")
    def test_fetched_provenance_records_the_bare_address_fetch(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """A bare-address fetch records provenance with no tag."""
        mocker.patch("pipelex.methods.fetch_on_miss.is_method_fetch_on_miss_enabled", return_value=True)
        package_dir = _make_package_dir(tmp_path)
        fetched = _make_fetched(package_dir, ref_str=FULL_ADDRESS)
        mocker.patch("pipelex.methods.fetch_on_miss.fetch_method_package", return_value=fetched)

        resolved = resolve_address_based_method(full_address=FULL_ADDRESS)

        assert resolved.provenance == MethodProvenance(address=FULL_ADDRESS, tag=None, commit_sha=COMMIT_SHA)
