from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.core.packages.manifest import DomainExports, MthdsPackageManifest
from pipelex.core.packages.visibility import PackageVisibilityChecker
from pipelex.core.qualified_ref import QualifiedRef
from pipelex.pipe_controllers.sequence.pipe_sequence_blueprint import PipeSequenceBlueprint
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint


def _make_llm_pipe(description: str = "test", output: str = "Text", prompt: str = "test") -> PipeLLMBlueprint:
    return PipeLLMBlueprint(
        type="PipeLLM",
        description=description,
        output=output,
        prompt=prompt,
    )


def _make_manifest_with_exports(exports: list[DomainExports]) -> MthdsPackageManifest:
    return MthdsPackageManifest(
        address="github.com/org/test",
        version="1.0.0",
        description="Test package",
        exports=exports,
    )


class TestPackageVisibilityChecker:
    """Tests for cross-domain pipe visibility enforcement."""

    def test_no_manifest_no_violations(self):
        """No manifest -> all pipes public, no violations."""
        bundle = PipelexBundleBlueprint(
            domain="alpha",
            pipe={"my_pipe": _make_llm_pipe()},
        )
        checker = PackageVisibilityChecker(manifest=None, bundles=[bundle])
        errors = checker.validate_all_pipe_references()
        assert errors == []

    def test_cross_domain_ref_to_exported_pipe_passes(self):
        """Cross-domain ref to an exported pipe should pass."""
        manifest = _make_manifest_with_exports(
            [
                DomainExports(domain_path="beta", pipes=["do_beta"]),
            ]
        )
        ref = QualifiedRef.parse_pipe_ref("beta.do_beta")
        checker = PackageVisibilityChecker(manifest=manifest, bundles=[])
        assert checker.is_pipe_accessible_from(ref, "alpha") is True

    def test_cross_domain_ref_to_main_pipe_passes(self):
        """Cross-domain ref to a main_pipe (not in exports) should pass (auto-export)."""
        manifest = _make_manifest_with_exports([])  # No explicit exports
        bundle_beta = PipelexBundleBlueprint(
            domain="beta",
            main_pipe="beta_main",
            pipe={"beta_main": _make_llm_pipe()},
        )
        ref = QualifiedRef.parse_pipe_ref("beta.beta_main")
        checker = PackageVisibilityChecker(manifest=manifest, bundles=[bundle_beta])
        assert checker.is_pipe_accessible_from(ref, "alpha") is True

    def test_cross_domain_ref_to_non_exported_pipe_fails(self):
        """Cross-domain ref to a non-exported pipe should produce a VisibilityError."""
        manifest = _make_manifest_with_exports(
            [
                DomainExports(domain_path="beta", pipes=["public_pipe"]),
            ]
        )
        bundle_beta = PipelexBundleBlueprint(
            domain="beta",
            pipe={
                "public_pipe": _make_llm_pipe(),
                "private_pipe": _make_llm_pipe(),
            },
        )
        ref = QualifiedRef.parse_pipe_ref("beta.private_pipe")
        checker = PackageVisibilityChecker(manifest=manifest, bundles=[bundle_beta])
        assert checker.is_pipe_accessible_from(ref, "alpha") is False

    def test_same_domain_ref_to_non_exported_pipe_passes(self):
        """Same-domain ref to a non-exported pipe should always pass."""
        manifest = _make_manifest_with_exports(
            [
                DomainExports(domain_path="alpha", pipes=["exported_only"]),
            ]
        )
        ref = QualifiedRef.parse_pipe_ref("alpha.internal_pipe")
        checker = PackageVisibilityChecker(manifest=manifest, bundles=[])
        assert checker.is_pipe_accessible_from(ref, "alpha") is True

    def test_bare_ref_passes(self):
        """Bare ref (no domain qualifier) should always pass."""
        manifest = _make_manifest_with_exports([])
        ref = QualifiedRef(domain_path=None, local_code="some_pipe")
        checker = PackageVisibilityChecker(manifest=manifest, bundles=[])
        assert checker.is_pipe_accessible_from(ref, "alpha") is True

    def test_validate_all_detects_violations(self):
        """validate_all_pipe_references finds cross-domain violations in bundles."""
        manifest = _make_manifest_with_exports(
            [
                DomainExports(domain_path="pkg_test_scoring", pipes=["pkg_test_compute_weighted_score"]),
            ]
        )
        # Bundle in legal.contracts that references a non-exported scoring pipe
        bundle_legal = PipelexBundleBlueprint(
            domain="pkg_test_legal.contracts",
            pipe={
                "pkg_test_orchestrate": PipeSequenceBlueprint(
                    type="PipeSequence",
                    description="Orchestrate",
                    output="Text",
                    steps=[
                        SubPipeBlueprint(pipe="pkg_test_scoring.pkg_test_private_helper"),
                    ],
                ),
            },
        )
        bundle_scoring = PipelexBundleBlueprint(
            domain="pkg_test_scoring",
            main_pipe="pkg_test_compute_weighted_score",
            pipe={
                "pkg_test_compute_weighted_score": _make_llm_pipe(),
                "pkg_test_private_helper": _make_llm_pipe(),
            },
        )
        checker = PackageVisibilityChecker(manifest=manifest, bundles=[bundle_legal, bundle_scoring])
        errors = checker.validate_all_pipe_references()
        assert len(errors) == 1
        assert errors[0].pipe_ref == "pkg_test_scoring.pkg_test_private_helper"
        assert "[exports" in errors[0].message

    def test_validate_all_no_violations_when_all_exported(self):
        """validate_all_pipe_references returns empty when all refs are exported."""
        manifest = _make_manifest_with_exports(
            [
                DomainExports(domain_path="pkg_test_scoring", pipes=["pkg_test_compute_weighted_score"]),
            ]
        )
        bundle_legal = PipelexBundleBlueprint(
            domain="pkg_test_legal.contracts",
            pipe={
                "pkg_test_orchestrate": PipeSequenceBlueprint(
                    type="PipeSequence",
                    description="Orchestrate",
                    output="Text",
                    steps=[
                        SubPipeBlueprint(pipe="pkg_test_scoring.pkg_test_compute_weighted_score"),
                    ],
                ),
            },
        )
        checker = PackageVisibilityChecker(manifest=manifest, bundles=[bundle_legal])
        errors = checker.validate_all_pipe_references()
        assert errors == []
