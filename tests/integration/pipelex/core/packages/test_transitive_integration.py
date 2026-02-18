from pathlib import Path

from pipelex.core.packages.dependency_resolver import resolve_all_dependencies
from pipelex.core.packages.lock_file import generate_lock_file
from pipelex.core.packages.manifest import MthdsPackageManifest, PackageDependency


class TestTransitiveIntegration:
    """Integration tests for transitive dependency resolution using local bare git repos."""

    def test_transitive_chain_resolves(
        self,
        transitive_url_overrides: dict[str, str],
        tmp_path: Path,
    ) -> None:
        """Resolve dependent-pkg and assert vcs-fixture is also transitively resolved."""
        manifest = MthdsPackageManifest(
            address="github.com/mthds-test/consumer",
            version="1.0.0",
            description="Consumer with transitive deps",
            dependencies=[
                PackageDependency(
                    address="github.com/mthds-test/dependent-pkg",
                    version="^1.0.0",
                    alias="dependent_pkg",
                ),
            ],
        )

        resolved = resolve_all_dependencies(
            manifest=manifest,
            package_root=tmp_path,
            cache_root=tmp_path / "cache",
            fetch_url_overrides=transitive_url_overrides,
        )

        addresses = {dep.address for dep in resolved}
        assert "github.com/mthds-test/dependent-pkg" in addresses
        assert "github.com/mthds-test/vcs-fixture" in addresses

    def test_lock_includes_transitive(
        self,
        transitive_url_overrides: dict[str, str],
        tmp_path: Path,
    ) -> None:
        """Generate lock from transitive resolution; both addresses appear in lock file."""
        manifest = MthdsPackageManifest(
            address="github.com/mthds-test/consumer",
            version="1.0.0",
            description="Consumer with transitive deps",
            dependencies=[
                PackageDependency(
                    address="github.com/mthds-test/dependent-pkg",
                    version="^1.0.0",
                    alias="dependent_pkg",
                ),
            ],
        )

        resolved = resolve_all_dependencies(
            manifest=manifest,
            package_root=tmp_path,
            cache_root=tmp_path / "cache",
            fetch_url_overrides=transitive_url_overrides,
        )

        lock = generate_lock_file(manifest, resolved)
        assert "github.com/mthds-test/dependent-pkg" in lock.packages
        assert "github.com/mthds-test/vcs-fixture" in lock.packages
