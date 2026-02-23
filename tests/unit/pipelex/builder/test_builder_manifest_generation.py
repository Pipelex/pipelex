import shutil
from pathlib import Path

from mthds.packages.discovery import MANIFEST_FILENAME
from mthds.packages.manifest_parser import parse_methods_toml

from pipelex.builder.builder_loop import maybe_generate_manifest_for_output

# Path to the physical test data
PACKAGES_DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "packages"


class TestBuilderManifestGeneration:
    """Tests for post-build METHODS.toml generation."""

    def test_multiple_domains_generates_manifest(self, tmp_path: Path) -> None:
        """Output dir with multiple domains -> METHODS.toml generated."""
        # Copy two .mthds files with different domains
        shutil.copy(PACKAGES_DATA_DIR / "legal_tools" / "legal" / "contracts.mthds", tmp_path / "contracts.mthds")
        shutil.copy(PACKAGES_DATA_DIR / "legal_tools" / "scoring" / "scoring.mthds", tmp_path / "scoring.mthds")

        result = maybe_generate_manifest_for_output(output_dir=tmp_path)

        assert result is not None
        manifest_path = tmp_path / MANIFEST_FILENAME
        assert manifest_path.exists()

        content = manifest_path.read_text(encoding="utf-8")
        manifest = parse_methods_toml(content)
        assert manifest.version == "0.1.0"
        assert len(manifest.exports) >= 2

        # Check that main_pipe entries are exported
        exported_pipes: list[str] = []
        for domain_export in manifest.exports:
            exported_pipes.extend(domain_export.pipes)
        assert "pkg_test_extract_clause" in exported_pipes
        assert "pkg_test_compute_weighted_score" in exported_pipes

    def test_single_domain_no_manifest(self, tmp_path: Path) -> None:
        """Output dir with single domain -> no METHODS.toml generated."""
        shutil.copy(PACKAGES_DATA_DIR / "minimal_package" / "core.mthds", tmp_path / "core.mthds")

        result = maybe_generate_manifest_for_output(output_dir=tmp_path)

        assert result is None
        manifest_path = tmp_path / MANIFEST_FILENAME
        assert not manifest_path.exists()

    def test_exported_pipes_include_main_pipe(self, tmp_path: Path) -> None:
        """Exported pipes include main_pipe entries from each bundle."""
        shutil.copy(PACKAGES_DATA_DIR / "legal_tools" / "legal" / "contracts.mthds", tmp_path / "contracts.mthds")
        shutil.copy(PACKAGES_DATA_DIR / "legal_tools" / "scoring" / "scoring.mthds", tmp_path / "scoring.mthds")

        maybe_generate_manifest_for_output(output_dir=tmp_path)

        manifest_path = tmp_path / MANIFEST_FILENAME
        content = manifest_path.read_text(encoding="utf-8")
        manifest = parse_methods_toml(content)

        # Build a lookup of domain -> pipes
        domain_pipes: dict[str, list[str]] = {}
        for domain_export in manifest.exports:
            domain_pipes[domain_export.domain_path] = domain_export.pipes

        # contracts.mthds has main_pipe = "pkg_test_extract_clause"
        assert "pkg_test_extract_clause" in domain_pipes.get("pkg_test_legal.contracts", [])
        # scoring.mthds has main_pipe = "pkg_test_compute_weighted_score"
        assert "pkg_test_compute_weighted_score" in domain_pipes.get("pkg_test_scoring", [])
