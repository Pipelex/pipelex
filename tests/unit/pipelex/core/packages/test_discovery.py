from pathlib import Path

import pytest

from pipelex.core.packages.discovery import MANIFEST_FILENAME, find_package_manifest
from pipelex.core.packages.exceptions import ManifestParseError

# Path to the physical test data
PACKAGES_DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent / "data" / "packages"


class TestManifestDiscovery:
    """Tests for METHODS.toml walk-up discovery."""

    def test_find_manifest_from_bundle_in_subdir(self):
        """Find METHODS.toml from a bundle path like legal/contracts.mthds."""
        bundle_path = PACKAGES_DATA_DIR / "legal_tools" / "legal" / "contracts.mthds"
        manifest = find_package_manifest(bundle_path)
        assert manifest is not None
        assert manifest.address == "github.com/pipelexlab/legal-tools"
        assert manifest.version == "1.0.0"

    def test_find_manifest_from_bundle_in_same_dir(self):
        """Find METHODS.toml when bundle is in the same directory as manifest."""
        bundle_path = PACKAGES_DATA_DIR / "minimal_package" / "core.mthds"
        manifest = find_package_manifest(bundle_path)
        assert manifest is not None
        assert manifest.address == "github.com/pipelexlab/minimal"

    def test_standalone_bundle_no_manifest(self):
        """Standalone bundle with no METHODS.toml returns None."""
        bundle_path = PACKAGES_DATA_DIR / "standalone_bundle" / "my_pipe.mthds"
        # This will walk up until it finds the repo's .git directory
        manifest = find_package_manifest(bundle_path)
        assert manifest is None

    def test_git_boundary_stops_search(self, tmp_path: Path):
        """Discovery stops at .git/ directory boundary."""
        # Create structure: tmp_path/METHODS.toml (above git boundary)
        #                   tmp_path/project/.git/
        #                   tmp_path/project/bundle.mthds
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (project_dir / ".git").mkdir()
        bundle_path = project_dir / "bundle.mthds"
        bundle_path.touch()

        # Put a METHODS.toml above the .git boundary (should NOT be found)
        manifest_content = '[package]\naddress = "github.com/org/above-git"\nversion = "1.0.0"\n'
        (tmp_path / MANIFEST_FILENAME).write_text(manifest_content)

        result = find_package_manifest(bundle_path)
        assert result is None

    def test_manifest_in_parent_found(self, tmp_path: Path):
        """METHODS.toml two levels up from bundle is found."""
        # tmp_path/METHODS.toml
        # tmp_path/sub/deep/bundle.mthds
        manifest_content = '[package]\naddress = "github.com/org/deep"\nversion = "2.0.0"\n'
        (tmp_path / MANIFEST_FILENAME).write_text(manifest_content)
        deep_dir = tmp_path / "sub" / "deep"
        deep_dir.mkdir(parents=True)
        bundle_path = deep_dir / "bundle.mthds"
        bundle_path.touch()

        result = find_package_manifest(bundle_path)
        assert result is not None
        assert result.address == "github.com/org/deep"
        assert result.version == "2.0.0"

    def test_malformed_manifest_raises(self, tmp_path: Path):
        """Malformed METHODS.toml raises ManifestParseError."""
        (tmp_path / MANIFEST_FILENAME).write_text("[broken\n")
        bundle_path = tmp_path / "bundle.mthds"
        bundle_path.touch()

        with pytest.raises(ManifestParseError):
            find_package_manifest(bundle_path)
