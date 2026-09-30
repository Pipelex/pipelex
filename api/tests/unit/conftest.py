from collections.abc import Callable
from pathlib import Path

import pytest
from pipelex.methods.fetching import FetchedMethodPackage, ensure_package_within_bounds
from pipelex.methods.method_ref import MethodRef
from pipelex.methods.package_locator import locate_package_in_clone
from pipelex.pipelex import Pipelex
from pipelex.system.runtime import IntegrationMode
from pipelex.test_extras.shared_pytest_plugins import needs_inference_in_pipelex
from pytest import FixtureRequest
from pytest_mock import MockerFixture

from api.api_config import get_api_config
from tests.unit._constants import STUB_METHOD_COMMIT_SHA, STUB_METHOD_MANIFEST


@pytest.fixture(autouse=True)
def reset_api_config_fixture(request: FixtureRequest):
    # Code to run before each test
    print("\n[magenta] Api setup[/magenta]")
    # The base runner is orchestrator-agnostic: with no orchestrator plugin installed and no
    # `boot_orchestrator` set, every pipeline (incl. dry-run validation) runs DIRECT in-process,
    # which is exactly what the hermetic suite needs. The former `temporal_enabled=False` knob is
    # gone — Temporal is now an external plugin, absent from this repo's deps entirely.
    pipelex_instance = Pipelex.make(
        integration_mode=IntegrationMode.PYTEST,
        needs_inference=needs_inference_in_pipelex(request),
    )
    # Drop the process-cached `[api]` config so a test that patches its env / loader cannot leak a
    # mutated config into later tests through the `@cache`d `get_api_config()` (the suite otherwise
    # relies on the packaged `direct` default — e.g. the `POST /start` override-policy 403 test).
    get_api_config.cache_clear()
    yield
    # Code to run after each test
    print("\n[magenta] Api teardown[/magenta]")
    get_api_config.cache_clear()
    pipelex_instance.teardown()


class _StubCloneCache:
    """A method clone cache whose network fetch is replaced by a local directory tree.

    Only the fetch is stubbed: package location by manifest identity and the bounds check run
    for real against the stub clone, so route tests exercise the true not-found / ambiguity
    behavior (and their status mapping) without touching the network.
    """

    def __init__(self, *, clone_root: Path, commit_sha: str) -> None:
        self._clone_root = clone_root
        self._commit_sha = commit_sha

    def get_or_fetch(self, *, ref: MethodRef, clone_url: str | None = None) -> FetchedMethodPackage:  # noqa: ARG002
        located = locate_package_in_clone(clone_root=self._clone_root, requested_address=ref.address)
        ensure_package_within_bounds(package_dir=located.package_dir, package_address=located.full_address)
        return FetchedMethodPackage(
            ref=ref,
            full_address=located.full_address,
            commit_sha=self._commit_sha,
            clone_dir=self._clone_root,
            package_dir=located.package_dir,
            manifest=located.manifest,
        )


@pytest.fixture
def install_method_package(mocker: MockerFixture, tmp_path: Path) -> Callable[..., Path]:
    """Factory fixture: present a fake fetched method package to the `method_ref` routes.

    Writes the given `{relative_path: text}` files (plus `STUB_METHOD_MANIFEST` as
    `METHODS.toml`, overridable) into a stub clone in the library-repo layout
    (`methods/documents/`), and patches `api.method_source.get_method_clone_cache` to serve
    it. Returns the package directory.
    """

    def _install(*, files: dict[str, str], manifest_toml: str = STUB_METHOD_MANIFEST, commit_sha: str = STUB_METHOD_COMMIT_SHA) -> Path:
        clone_root = tmp_path / "stub-clone"
        package_dir = clone_root / "methods" / "documents"
        package_dir.mkdir(parents=True, exist_ok=True)
        (package_dir / "METHODS.toml").write_text(manifest_toml, encoding="utf-8")
        for relative_path, content in files.items():
            target = package_dir / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        stub = _StubCloneCache(clone_root=clone_root, commit_sha=commit_sha)
        mocker.patch("api.method_source.get_method_clone_cache", return_value=stub)
        return package_dir

    return _install
