from pathlib import Path

import pytest
from semantic_version import Version  # type: ignore[import-untyped]

from pipelex.core.packages.dependency_resolver import (
    DependencyResolveError,
    resolve_all_dependencies,
    resolve_remote_dependency,
)
from pipelex.core.packages.manifest import MthdsPackageManifest, PackageDependency
from pipelex.core.packages.package_cache import is_cached
from pipelex.core.packages.vcs_resolver import clone_at_version, list_remote_version_tags

PACKAGES_DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent / "data" / "packages"


class TestVCSResolverIntegration:
    """Layer 3 integration tests for VCS resolver + cache using a local bare git repo."""

    def test_list_remote_tags(self, bare_git_repo_url: str):
        """Both tagged versions are found in the bare repo."""
        version_tags = list_remote_version_tags(bare_git_repo_url)
        versions = {ver for ver, _tag in version_tags}
        assert Version("1.0.0") in versions
        assert Version("1.1.0") in versions

    def test_clone_at_version(self, bare_git_repo_url: str, tmp_path: Path):
        """Cloning at v1.0.0 produces a directory with METHODS.toml."""
        dest = tmp_path / "cloned"
        clone_at_version(bare_git_repo_url, "v1.0.0", dest)

        assert (dest / "METHODS.toml").is_file()
        content = (dest / "METHODS.toml").read_text()
        assert 'version = "1.0.0"' in content

    def test_resolve_remote_dependency_mvs(self, bare_git_repo_url: str, tmp_path: Path):
        """Constraint ^1.0.0 selects v1.0.0 via MVS."""
        dep = PackageDependency(
            address="github.com/mthds-test/vcs-fixture",
            version="^1.0.0",
            alias="vcs_fixture",
        )
        resolved = resolve_remote_dependency(
            dep,
            cache_root=tmp_path / "cache",
            fetch_url_override=bare_git_repo_url,
        )
        assert resolved.alias == "vcs_fixture"
        assert resolved.manifest is not None
        assert resolved.manifest.version == "1.0.0"
        assert resolved.package_root.is_dir()

    def test_resolve_remote_dependency_higher_constraint(self, bare_git_repo_url: str, tmp_path: Path):
        """Constraint >=1.1.0 selects v1.1.0."""
        dep = PackageDependency(
            address="github.com/mthds-test/vcs-fixture",
            version=">=1.1.0",
            alias="vcs_fixture",
        )
        resolved = resolve_remote_dependency(
            dep,
            cache_root=tmp_path / "cache",
            fetch_url_override=bare_git_repo_url,
        )
        assert resolved.manifest is not None
        assert resolved.manifest.version == "1.1.0"

    def test_resolve_remote_dependency_no_match(self, bare_git_repo_url: str, tmp_path: Path):
        """Constraint ^2.0.0 raises DependencyResolveError (no matching version)."""
        dep = PackageDependency(
            address="github.com/mthds-test/vcs-fixture",
            version="^2.0.0",
            alias="vcs_fixture",
        )
        with pytest.raises(DependencyResolveError, match="No version satisfying"):
            resolve_remote_dependency(
                dep,
                cache_root=tmp_path / "cache",
                fetch_url_override=bare_git_repo_url,
            )

    def test_cache_hit_on_second_resolve(self, bare_git_repo_url: str, tmp_path: Path):
        """Second resolve uses cache (same directory, no second clone)."""
        cache_dir = tmp_path / "cache"
        dep = PackageDependency(
            address="github.com/mthds-test/vcs-fixture",
            version="^1.0.0",
            alias="vcs_fixture",
        )

        # First resolve: clones and caches
        resolved_first = resolve_remote_dependency(
            dep,
            cache_root=cache_dir,
            fetch_url_override=bare_git_repo_url,
        )
        assert is_cached("github.com/mthds-test/vcs-fixture", "1.0.0", cache_root=cache_dir)

        # Second resolve: should use cache (same result)
        resolved_second = resolve_remote_dependency(
            dep,
            cache_root=cache_dir,
            fetch_url_override=bare_git_repo_url,
        )
        assert resolved_first.package_root == resolved_second.package_root

    def test_resolve_all_mixed_local_and_remote(self, bare_git_repo_url: str, tmp_path: Path):
        """Manifest with one local path dep + one remote dep resolves both."""
        manifest = MthdsPackageManifest(
            address="github.com/mthds/consumer-app",
            version="1.0.0",
            description="Consumer with mixed deps",
            dependencies=[
                PackageDependency(
                    address="github.com/mthds/scoring-lib",
                    version="2.0.0",
                    alias="scoring_dep",
                    path="../scoring_dep",
                ),
                PackageDependency(
                    address="github.com/mthds-test/vcs-fixture",
                    version="^1.0.0",
                    alias="vcs_fixture",
                ),
            ],
        )
        package_root = PACKAGES_DATA_DIR / "consumer_package"

        resolved = resolve_all_dependencies(
            manifest=manifest,
            package_root=package_root,
            cache_root=tmp_path / "cache",
            fetch_url_overrides={"github.com/mthds-test/vcs-fixture": bare_git_repo_url},
        )

        assert len(resolved) == 2
        aliases = {dep.alias for dep in resolved}
        assert "scoring_dep" in aliases
        assert "vcs_fixture" in aliases
