import shutil
from pathlib import Path

from pipelex.core.interpreter.interpreter import PipelexInterpreter
from pipelex.core.packages.discovery import find_package_manifest
from pipelex.core.packages.visibility import check_visibility_for_blueprints

# Path to the physical test data
PACKAGES_DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent / "data" / "packages"


class TestVisibilityIntegration:
    """Integration tests using physical METHODS.toml and .mthds files on disk."""

    def test_legal_tools_package_valid_refs(self):
        """Legal tools package: all cross-domain refs are to exported pipes -> no errors."""
        contracts_path = PACKAGES_DATA_DIR / "legal_tools" / "legal" / "contracts.mthds"
        scoring_path = PACKAGES_DATA_DIR / "legal_tools" / "scoring" / "scoring.mthds"

        manifest = find_package_manifest(contracts_path)
        assert manifest is not None

        contracts_bp = PipelexInterpreter.make_pipelex_bundle_blueprint(bundle_path=contracts_path)
        scoring_bp = PipelexInterpreter.make_pipelex_bundle_blueprint(bundle_path=scoring_path)

        errors = check_visibility_for_blueprints(manifest=manifest, blueprints=[contracts_bp, scoring_bp])
        assert errors == []

    def test_standalone_bundle_all_public(self):
        """Standalone bundle (no METHODS.toml) -> all pipes public, no errors."""
        bundle_path = PACKAGES_DATA_DIR / "standalone_bundle" / "my_pipe.mthds"

        manifest = find_package_manifest(bundle_path)
        assert manifest is None

        bundle_bp = PipelexInterpreter.make_pipelex_bundle_blueprint(bundle_path=bundle_path)
        errors = check_visibility_for_blueprints(manifest=None, blueprints=[bundle_bp])
        assert errors == []

    def test_modified_bundle_references_private_pipe(self, tmp_path: Path):
        """Modified bundle that references a private pipe -> visibility error."""
        # Copy the legal_tools package to tmp_path
        src_dir = PACKAGES_DATA_DIR / "legal_tools"
        dst_dir = tmp_path / "legal_tools"
        shutil.copytree(src_dir, dst_dir)

        # Modify contracts.mthds to reference the private helper pipe
        contracts_path = dst_dir / "legal" / "contracts.mthds"
        contracts_content = contracts_path.read_text(encoding="utf-8")
        contracts_content = contracts_content.replace(
            "pkg_test_scoring.pkg_test_compute_weighted_score",
            "pkg_test_scoring.pkg_test_private_helper",
        )
        # Add the pipe reference as a sequence step
        modified_content = """\
domain = "pkg_test_legal.contracts"
main_pipe = "pkg_test_extract_clause"

[concept.PkgTestContractClause]
description = "A clause extracted from a contract"

[pipe.pkg_test_extract_clause]
type = "PipeLLM"
description = "Extract the main clause from a contract"
output = "PkgTestContractClause"
prompt = "Extract the main clause from the following contract text: {{ text }}"

[pipe.pkg_test_extract_clause.inputs]
text = "Text"

[pipe.pkg_test_call_private]
type = "PipeSequence"
description = "Call a private pipe from another domain"
output = "Text"

[[pipe.pkg_test_call_private.steps]]
pipe = "pkg_test_scoring.pkg_test_private_helper"
"""
        contracts_path.write_text(modified_content, encoding="utf-8")

        scoring_path = dst_dir / "scoring" / "scoring.mthds"

        manifest = find_package_manifest(contracts_path)
        assert manifest is not None

        contracts_bp = PipelexInterpreter.make_pipelex_bundle_blueprint(bundle_path=contracts_path)
        scoring_bp = PipelexInterpreter.make_pipelex_bundle_blueprint(bundle_path=scoring_path)

        errors = check_visibility_for_blueprints(manifest=manifest, blueprints=[contracts_bp, scoring_bp])
        assert len(errors) == 1
        assert "pkg_test_private_helper" in errors[0].pipe_ref
        assert "[exports" in errors[0].message
