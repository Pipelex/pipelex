from pathlib import Path

from pipelex.core.interpreter.interpreter import PipelexInterpreter
from pipelex.core.packages.dependency_resolver import resolve_local_dependencies
from pipelex.core.packages.discovery import find_package_manifest
from pipelex.core.packages.manifest import MthdsPackageManifest
from pipelex.core.packages.visibility import check_visibility_for_blueprints

# Path to the physical test data
PACKAGES_DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent / "data" / "packages"


class TestCrossPackageIntegration:
    """Integration tests for cross-package dependency resolution using physical test fixtures."""

    def test_consumer_package_visibility_passes(self):
        """Consumer package with cross-package refs passes visibility checks."""
        analysis_path = PACKAGES_DATA_DIR / "consumer_package" / "analysis.mthds"

        manifest = find_package_manifest(analysis_path)
        assert manifest is not None
        assert len(manifest.dependencies) == 1
        assert manifest.dependencies[0].alias == "scoring_dep"
        assert manifest.dependencies[0].path == "../scoring_dep"

        analysis_bp = PipelexInterpreter.make_pipelex_bundle_blueprint(bundle_path=analysis_path)

        # Visibility check should pass: the cross-package ref alias is known
        errors = check_visibility_for_blueprints(manifest=manifest, blueprints=[analysis_bp])
        assert errors == []

    def test_resolve_consumer_dependencies(self):
        """Resolve the consumer package's dependency to scoring_dep."""
        analysis_path = PACKAGES_DATA_DIR / "consumer_package" / "analysis.mthds"
        package_root = PACKAGES_DATA_DIR / "consumer_package"

        manifest = find_package_manifest(analysis_path)
        assert manifest is not None

        resolved = resolve_local_dependencies(manifest=manifest, package_root=package_root)
        assert len(resolved) == 1

        dep = resolved[0]
        assert dep.alias == "scoring_dep"
        assert dep.manifest is not None
        assert dep.manifest.address == "github.com/mthds/scoring-lib"
        assert len(dep.mthds_files) >= 1
        assert dep.exported_pipe_codes is not None
        assert "pkg_test_compute_score" in dep.exported_pipe_codes

    def test_scoring_dep_manifest_parsed_correctly(self):
        """Verify the scoring_dep METHODS.toml is parsed correctly."""
        scoring_manifest_path = PACKAGES_DATA_DIR / "scoring_dep" / "scoring.mthds"
        manifest = find_package_manifest(scoring_manifest_path)
        assert manifest is not None
        assert manifest.address == "github.com/mthds/scoring-lib"
        assert manifest.version == "2.0.0"
        assert len(manifest.exports) == 1
        assert manifest.exports[0].domain_path == "pkg_test_scoring_dep"
        assert "pkg_test_compute_score" in manifest.exports[0].pipes

    def test_consumer_bundle_parses_with_cross_package_refs(self):
        """Consumer bundle with cross-package pipe refs should parse without errors."""
        analysis_path = PACKAGES_DATA_DIR / "consumer_package" / "analysis.mthds"
        blueprint = PipelexInterpreter.make_pipelex_bundle_blueprint(bundle_path=analysis_path)

        assert blueprint.domain == "pkg_test_consumer_analysis"
        assert blueprint.pipe is not None
        assert "pkg_test_analyze_item" in blueprint.pipe

    def test_unknown_alias_in_consumer_produces_error(self):
        """If a cross-package ref uses an unknown alias, visibility check produces an error."""
        analysis_path = PACKAGES_DATA_DIR / "consumer_package" / "analysis.mthds"

        # Create a manifest without the scoring_dep dependency
        manifest_no_deps = MthdsPackageManifest(
            address="github.com/mthds/consumer-app",
            version="1.0.0",
            description="Consumer with no deps declared",
        )

        analysis_bp = PipelexInterpreter.make_pipelex_bundle_blueprint(bundle_path=analysis_path)

        errors = check_visibility_for_blueprints(manifest=manifest_no_deps, blueprints=[analysis_bp])
        # Should have an error for unknown alias "scoring_dep"
        cross_package_errors = [err for err in errors if "scoring_dep" in err.message]
        assert len(cross_package_errors) >= 1
        assert "[dependencies]" in cross_package_errors[0].message
