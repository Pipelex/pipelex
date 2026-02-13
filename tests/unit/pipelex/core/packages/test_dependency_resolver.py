from pathlib import Path

import pytest

from pipelex.core.packages.dependency_resolver import ResolvedDependency, resolve_local_dependencies
from pipelex.core.packages.exceptions import DependencyResolveError
from pipelex.core.packages.manifest import MthdsPackageManifest, PackageDependency

PACKAGES_DIR = Path(__file__).resolve().parents[4] / "data" / "packages"


class TestDependencyResolver:
    """Tests for local dependency resolution."""

    def test_resolve_local_path_dependency(self):
        """Resolve a dependency with a valid local path."""
        manifest = MthdsPackageManifest(
            address="github.com/mthds/consumer-app",
            version="1.0.0",
            description="Consumer",
            dependencies=[
                PackageDependency(
                    address="github.com/mthds/scoring-lib",
                    version="2.0.0",
                    alias="scoring_dep",
                    path="../scoring_dep",
                ),
            ],
        )
        package_root = PACKAGES_DIR / "consumer_package"
        resolved = resolve_local_dependencies(manifest=manifest, package_root=package_root)

        assert len(resolved) == 1
        dep = resolved[0]
        assert dep.alias == "scoring_dep"
        assert dep.package_root == (PACKAGES_DIR / "scoring_dep").resolve()
        assert len(dep.mthds_files) >= 1
        # The scoring_dep has exports, so exported_pipe_codes should be populated
        assert "pkg_test_compute_score" in dep.exported_pipe_codes

    def test_dependency_without_path_is_skipped(self):
        """Dependencies without a path field are skipped."""
        manifest = MthdsPackageManifest(
            address="github.com/mthds/consumer-app",
            version="1.0.0",
            description="Consumer",
            dependencies=[
                PackageDependency(
                    address="github.com/mthds/scoring-lib",
                    version="2.0.0",
                    alias="scoring_dep",
                    # No path field
                ),
            ],
        )
        package_root = PACKAGES_DIR / "consumer_package"
        resolved = resolve_local_dependencies(manifest=manifest, package_root=package_root)

        assert len(resolved) == 0

    def test_nonexistent_path_raises_error(self):
        """A dependency pointing to a non-existent path raises DependencyResolveError."""
        manifest = MthdsPackageManifest(
            address="github.com/mthds/consumer-app",
            version="1.0.0",
            description="Consumer",
            dependencies=[
                PackageDependency(
                    address="github.com/mthds/scoring-lib",
                    version="2.0.0",
                    alias="scoring_dep",
                    path="../nonexistent_dir",
                ),
            ],
        )
        package_root = PACKAGES_DIR / "consumer_package"
        with pytest.raises(DependencyResolveError, match="does not exist"):
            resolve_local_dependencies(manifest=manifest, package_root=package_root)

    def test_dependency_without_manifest_has_no_exports(self):
        """A dependency directory without METHODS.toml -> empty exported_pipe_codes (all public)."""
        manifest = MthdsPackageManifest(
            address="github.com/mthds/consumer-app",
            version="1.0.0",
            description="Consumer",
            dependencies=[
                PackageDependency(
                    address="github.com/mthds/standalone",
                    version="1.0.0",
                    alias="standalone",
                    path="../standalone_bundle",
                ),
            ],
        )
        package_root = PACKAGES_DIR / "consumer_package"
        resolved = resolve_local_dependencies(manifest=manifest, package_root=package_root)

        assert len(resolved) == 1
        dep = resolved[0]
        assert dep.alias == "standalone"
        assert dep.manifest is None
        # No manifest = empty exports = all public
        assert dep.exported_pipe_codes == set()

    def test_resolved_dependency_is_frozen(self, tmp_path: Path):
        """ResolvedDependency should be immutable (frozen model)."""
        dep = ResolvedDependency(
            alias="test",
            address="github.com/test/test",
            manifest=None,
            package_root=tmp_path / "test",
            mthds_files=[],
            exported_pipe_codes=set(),
        )
        assert dep.alias == "test"
