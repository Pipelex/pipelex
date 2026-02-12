import pytest

from pipelex.core.packages.exceptions import ManifestParseError, ManifestValidationError
from pipelex.core.packages.manifest_parser import parse_methods_toml, serialize_manifest_to_toml
from tests.unit.pipelex.core.packages.test_data import (
    EMPTY_EXPORTS_DEPS_TOML,
    FULL_MANIFEST_TOML,
    INVALID_DOMAIN_PATH_EXPORTS_TOML,
    INVALID_PIPE_NAME_EXPORTS_TOML,
    INVALID_TOML_SYNTAX,
    MINIMAL_MANIFEST_TOML,
    MISSING_PACKAGE_SECTION_TOML,
    MISSING_REQUIRED_FIELDS_TOML,
    MULTI_LEVEL_EXPORTS_TOML,
    NON_TABLE_DEPENDENCY_TOML,
    ManifestTestData,
)


class TestManifestParser:
    """Tests for METHODS.toml parsing and serialization."""

    def test_parse_full_manifest(self):
        """Parse a well-formed TOML with nested exports sub-tables."""
        manifest = parse_methods_toml(FULL_MANIFEST_TOML)
        assert manifest.address == ManifestTestData.FULL_MANIFEST.address
        assert manifest.version == ManifestTestData.FULL_MANIFEST.version
        assert manifest.description == ManifestTestData.FULL_MANIFEST.description
        assert manifest.authors == ManifestTestData.FULL_MANIFEST.authors
        assert manifest.license == ManifestTestData.FULL_MANIFEST.license
        assert manifest.mthds_version == ManifestTestData.FULL_MANIFEST.mthds_version
        assert len(manifest.dependencies) == 1
        assert manifest.dependencies[0].alias == "scoring_lib"
        assert manifest.dependencies[0].address == "github.com/pipelexlab/scoring-lib"
        assert len(manifest.exports) == 2
        domain_paths = {exp.domain_path for exp in manifest.exports}
        assert "legal.contracts" in domain_paths
        assert "scoring" in domain_paths

    def test_parse_minimal_manifest(self):
        """Parse a manifest with only required fields."""
        manifest = parse_methods_toml(MINIMAL_MANIFEST_TOML)
        assert manifest.address == ManifestTestData.MINIMAL_MANIFEST.address
        assert manifest.version == ManifestTestData.MINIMAL_MANIFEST.version
        assert manifest.dependencies == []
        assert manifest.exports == []

    def test_parse_empty_exports_and_deps(self):
        """Parse a manifest with empty exports and dependencies sections."""
        manifest = parse_methods_toml(EMPTY_EXPORTS_DEPS_TOML)
        assert manifest.dependencies == []
        assert manifest.exports == []

    def test_parse_multi_level_nested_exports(self):
        """Parse manifest with multi-level nested exports like [exports.legal.contracts.shareholder]."""
        manifest = parse_methods_toml(MULTI_LEVEL_EXPORTS_TOML)
        domain_paths = {exp.domain_path for exp in manifest.exports}
        assert "legal.contracts.shareholder" in domain_paths
        assert "legal.contracts" in domain_paths
        assert "scoring" in domain_paths

        # Check pipes for each domain
        shareholder_exports = next(exp for exp in manifest.exports if exp.domain_path == "legal.contracts.shareholder")
        assert shareholder_exports.pipes == ["extract_shareholder_clause"]

        contracts_exports = next(exp for exp in manifest.exports if exp.domain_path == "legal.contracts")
        assert contracts_exports.pipes == ["extract_clause"]

    def test_parse_invalid_toml_syntax(self):
        """TOML syntax error should raise ManifestParseError."""
        with pytest.raises(ManifestParseError, match="Invalid TOML syntax"):
            parse_methods_toml(INVALID_TOML_SYNTAX)

    def test_parse_missing_package_section(self):
        """Missing [package] section should raise ManifestValidationError."""
        with pytest.raises(ManifestValidationError, match="must contain a \\[package\\] section"):
            parse_methods_toml(MISSING_PACKAGE_SECTION_TOML)

    def test_parse_missing_required_fields(self):
        """Missing required fields in [package] should raise ManifestValidationError."""
        with pytest.raises(ManifestValidationError, match="validation failed"):
            parse_methods_toml(MISSING_REQUIRED_FIELDS_TOML)

    def test_parse_non_table_dependency_raises(self):
        """A dependency whose value is not a table should raise ManifestValidationError."""
        with pytest.raises(ManifestValidationError, match="expected a table"):
            parse_methods_toml(NON_TABLE_DEPENDENCY_TOML)

    @pytest.mark.parametrize(
        ("topic", "toml_content"),
        [
            ("invalid domain path", INVALID_DOMAIN_PATH_EXPORTS_TOML),
            ("invalid pipe name", INVALID_PIPE_NAME_EXPORTS_TOML),
        ],
    )
    def test_parse_invalid_exports_raises(self, topic: str, toml_content: str):
        """Invalid domain paths or pipe names in [exports] should raise ManifestValidationError."""
        _ = topic  # Used for test identification
        with pytest.raises(ManifestValidationError, match="Invalid exports"):
            parse_methods_toml(toml_content)

    def test_serialize_roundtrip(self):
        """Serialize a manifest to TOML and parse it back — roundtrip check."""
        original = ManifestTestData.FULL_MANIFEST
        toml_str = serialize_manifest_to_toml(original)
        parsed = parse_methods_toml(toml_str)
        assert parsed.address == original.address
        assert parsed.version == original.version
        assert parsed.description == original.description
        assert len(parsed.dependencies) == len(original.dependencies)
        assert len(parsed.exports) == len(original.exports)

    def test_serialize_minimal_manifest(self):
        """Serialize a minimal manifest with no deps/exports."""
        manifest = ManifestTestData.MINIMAL_MANIFEST
        toml_str = serialize_manifest_to_toml(manifest)
        assert "[package]" in toml_str
        assert 'address = "github.com/pipelexlab/minimal"' in toml_str
        assert "[dependencies]" not in toml_str
        assert "[exports" not in toml_str
