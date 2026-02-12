from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.core.packages.manifest import MthdsPackageManifest, PackageDependency
from pipelex.core.packages.visibility import PackageVisibilityChecker
from pipelex.core.qualified_ref import QualifiedRef
from pipelex.pipe_controllers.sequence.pipe_sequence_blueprint import PipeSequenceBlueprint
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint


class TestCrossPackageRefs:
    """Tests for cross-package '->' reference detection."""

    def test_has_cross_package_prefix(self):
        """Detect '->' in raw reference strings."""
        assert QualifiedRef.has_cross_package_prefix("my_lib->scoring.compute") is True
        assert QualifiedRef.has_cross_package_prefix("scoring.compute") is False
        assert QualifiedRef.has_cross_package_prefix("compute") is False

    def test_split_cross_package_ref(self):
        """Split 'alias->domain.pipe' correctly."""
        alias, remainder = QualifiedRef.split_cross_package_ref("my_lib->scoring.compute")
        assert alias == "my_lib"
        assert remainder == "scoring.compute"

    def test_known_alias_emits_warning_not_error(self):
        """Cross-package ref with alias in dependencies -> warning emitted, no error."""
        manifest = MthdsPackageManifest(
            address="github.com/org/test",
            version="1.0.0",
            description="Test package",
            dependencies=[
                PackageDependency(
                    address="github.com/org/scoring-lib",
                    version="1.0.0",
                    alias="scoring_lib",
                ),
            ],
        )
        bundle = PipelexBundleBlueprint(
            domain="my_domain",
            pipe={
                "my_pipe": PipeSequenceBlueprint(
                    type="PipeSequence",
                    description="Test",
                    output="Text",
                    steps=[
                        SubPipeBlueprint(pipe="scoring_lib->scoring.compute_score"),
                    ],
                ),
            },
        )
        checker = PackageVisibilityChecker(manifest=manifest, bundles=[bundle])
        errors = checker.validate_cross_package_references()
        # Known alias -> no error (only warning emitted via log)
        assert errors == []

    def test_unknown_alias_produces_error(self):
        """Cross-package ref with alias NOT in dependencies -> error."""
        manifest = MthdsPackageManifest(
            address="github.com/org/test",
            version="1.0.0",
            description="Test package",
        )
        bundle = PipelexBundleBlueprint(
            domain="my_domain",
            pipe={
                "my_pipe": PipeSequenceBlueprint(
                    type="PipeSequence",
                    description="Test",
                    output="Text",
                    steps=[
                        SubPipeBlueprint(pipe="unknown_lib->scoring.compute_score"),
                    ],
                ),
            },
        )
        checker = PackageVisibilityChecker(manifest=manifest, bundles=[bundle])
        errors = checker.validate_cross_package_references()
        assert len(errors) == 1
        assert "unknown_lib" in errors[0].message
        assert "[dependencies]" in errors[0].message

    def test_no_cross_package_refs_no_warnings(self):
        """No '->' refs at all -> no warnings or errors."""
        manifest = MthdsPackageManifest(
            address="github.com/org/test",
            version="1.0.0",
            description="Test package",
        )
        bundle = PipelexBundleBlueprint(
            domain="my_domain",
            pipe={
                "my_pipe": PipeSequenceBlueprint(
                    type="PipeSequence",
                    description="Test",
                    output="Text",
                    steps=[
                        SubPipeBlueprint(pipe="scoring.compute_score"),
                    ],
                ),
            },
        )
        checker = PackageVisibilityChecker(manifest=manifest, bundles=[bundle])
        errors = checker.validate_cross_package_references()
        assert errors == []
