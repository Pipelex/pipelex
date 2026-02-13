import shutil
from pathlib import Path

import pytest

from pipelex.core.packages.exceptions import IndexBuildError
from pipelex.core.packages.index.index_builder import (
    build_index_entry_from_package,
    build_index_from_cache,
    build_index_from_project,
)

PACKAGES_DATA_DIR = Path(__file__).resolve().parents[5] / "data" / "packages"


class TestIndexBuilder:
    """Tests for the package index builder."""

    def test_build_entry_from_legal_tools(self) -> None:
        """Build index entry from legal_tools test package with multi-domain exports."""
        entry = build_index_entry_from_package(PACKAGES_DATA_DIR / "legal_tools")

        assert entry.address == "github.com/pipelexlab/legal-tools"
        assert entry.version == "1.0.0"
        assert entry.description == "Legal document analysis tools"
        assert entry.authors == ["PipelexLab"]
        assert entry.license == "MIT"

    def test_build_entry_extracts_domains(self) -> None:
        """Builder discovers all domains from .mthds files."""
        entry = build_index_entry_from_package(PACKAGES_DATA_DIR / "legal_tools")

        domain_codes = {dom.domain_code for dom in entry.domains}
        assert "pkg_test_legal.contracts" in domain_codes
        assert "pkg_test_scoring" in domain_codes

    def test_build_entry_extracts_concepts(self) -> None:
        """Builder extracts concept entries from blueprints."""
        entry = build_index_entry_from_package(PACKAGES_DATA_DIR / "legal_tools")

        concept_codes = {concept.concept_code for concept in entry.concepts}
        assert "PkgTestContractClause" in concept_codes
        assert "PkgTestScoreResult" in concept_codes

    def test_build_entry_concept_ref_includes_domain(self) -> None:
        """Concept entries have domain-qualified concept_ref."""
        entry = build_index_entry_from_package(PACKAGES_DATA_DIR / "legal_tools")

        clause = next(concept for concept in entry.concepts if concept.concept_code == "PkgTestContractClause")
        assert clause.concept_ref == "pkg_test_legal.contracts.PkgTestContractClause"
        assert clause.domain_code == "pkg_test_legal.contracts"

    def test_build_entry_extracts_pipe_signatures(self) -> None:
        """Builder extracts pipe signatures with input/output specs."""
        entry = build_index_entry_from_package(PACKAGES_DATA_DIR / "legal_tools")

        pipe_codes = {pipe.pipe_code for pipe in entry.pipes}
        assert "pkg_test_extract_clause" in pipe_codes
        assert "pkg_test_analyze_contract" in pipe_codes
        assert "pkg_test_compute_weighted_score" in pipe_codes

    def test_build_entry_pipe_input_output_specs(self) -> None:
        """Pipe signatures carry input and output concept specs as strings."""
        entry = build_index_entry_from_package(PACKAGES_DATA_DIR / "legal_tools")

        extract = next(pipe for pipe in entry.pipes if pipe.pipe_code == "pkg_test_extract_clause")
        assert extract.input_specs == {"text": "Text"}
        assert extract.output_spec == "PkgTestContractClause"
        assert extract.pipe_type == "PipeLLM"

    def test_build_entry_pipe_export_status(self) -> None:
        """Exported pipes are marked, non-exported pipes are not."""
        entry = build_index_entry_from_package(PACKAGES_DATA_DIR / "scoring_dep")

        exported_pipe = next(pipe for pipe in entry.pipes if pipe.pipe_code == "pkg_test_compute_score")
        assert exported_pipe.is_exported is True

        internal_pipe = next(pipe for pipe in entry.pipes if pipe.pipe_code == "pkg_test_internal_helper")
        assert internal_pipe.is_exported is False

    def test_build_entry_main_pipe_auto_exported(self) -> None:
        """main_pipe is auto-exported even if not in exports list."""
        entry = build_index_entry_from_package(PACKAGES_DATA_DIR / "scoring_dep")

        compute = next(pipe for pipe in entry.pipes if pipe.pipe_code == "pkg_test_compute_score")
        assert compute.is_exported is True

    def test_build_entry_minimal_package(self) -> None:
        """Build index entry from a minimal package with no exports section."""
        entry = build_index_entry_from_package(PACKAGES_DATA_DIR / "minimal_package")

        assert entry.address == "github.com/pipelexlab/minimal"
        assert entry.version == "0.1.0"
        assert len(entry.pipes) == 1
        # No exports section = all pipes are public
        assert entry.pipes[0].is_exported is True
        assert entry.pipes[0].pipe_code == "pkg_test_hello"

    def test_build_entry_dependencies_listed(self) -> None:
        """Builder extracts dependency addresses from manifest."""
        entry = build_index_entry_from_package(PACKAGES_DATA_DIR / "legal_tools")
        assert "github.com/pipelexlab/scoring-lib" in entry.dependencies

    def test_build_entry_concept_with_refines(self) -> None:
        """Builder captures cross-package refines on concepts."""
        entry = build_index_entry_from_package(PACKAGES_DATA_DIR / "refining_consumer")

        refined = next(concept for concept in entry.concepts if concept.concept_code == "PkgTestRefinedScore")
        assert refined.refines == "scoring_dep->pkg_test_scoring_dep.PkgTestWeightedScore"

    def test_build_entry_no_manifest_raises(self) -> None:
        """Building from a directory without METHODS.toml raises IndexBuildError."""
        with pytest.raises(IndexBuildError, match=r"No METHODS\.toml found"):
            build_index_entry_from_package(PACKAGES_DATA_DIR / "standalone_bundle")

    def test_build_entry_nonexistent_dir_raises(self) -> None:
        """Building from a nonexistent directory raises IndexBuildError."""
        with pytest.raises(IndexBuildError):
            build_index_entry_from_package(PACKAGES_DATA_DIR / "nonexistent")

    def test_build_index_from_empty_cache(self, tmp_path: Path) -> None:
        """build_index_from_cache returns empty index for nonexistent cache."""
        index = build_index_from_cache(cache_root=tmp_path / "no_cache")
        assert len(index.entries) == 0

    def test_build_index_from_cache_with_packages(self, tmp_path: Path) -> None:
        """build_index_from_cache discovers packages in the cache layout."""
        # Set up cache layout: cache_root/address/version/
        cache_root = tmp_path / "cache"
        pkg_dir = cache_root / "github.com" / "pipelexlab" / "scoring-lib" / "2.0.0"
        pkg_dir.mkdir(parents=True)
        src = PACKAGES_DATA_DIR / "scoring_dep"
        for item in src.iterdir():
            if item.is_file():
                shutil.copy(item, pkg_dir / item.name)

        index = build_index_from_cache(cache_root=cache_root)
        assert len(index.entries) == 1
        entry = index.get_entry("github.com/mthds/scoring-lib")
        assert entry is not None
        assert entry.version == "2.0.0"

    def test_build_index_from_project(self) -> None:
        """build_index_from_project indexes the project itself."""
        index = build_index_from_project(PACKAGES_DATA_DIR / "minimal_package")

        assert len(index.entries) == 1
        entry = index.get_entry("github.com/pipelexlab/minimal")
        assert entry is not None
        assert entry.version == "0.1.0"

    def test_build_index_from_project_no_manifest(self, tmp_path: Path) -> None:
        """build_index_from_project returns empty index when no manifest exists."""
        index = build_index_from_project(tmp_path)
        assert len(index.entries) == 0
