from typing import ClassVar

import pytest
from pydantic import ValidationError

from pipelex.core.packages.index.models import (
    ConceptEntry,
    DomainEntry,
    PackageIndex,
    PackageIndexEntry,
    PipeSignature,
)


class TestData:
    PIPE_SIG: ClassVar[PipeSignature] = PipeSignature(
        pipe_code="pkg_test_extract",
        pipe_type="PipeLLM",
        domain_code="pkg_test_legal",
        description="Extract clauses",
        input_specs={"text": "Text"},
        output_spec="PkgTestContractClause",
        is_exported=True,
    )

    CONCEPT_ENTRY: ClassVar[ConceptEntry] = ConceptEntry(
        concept_code="PkgTestContractClause",
        domain_code="pkg_test_legal",
        concept_ref="pkg_test_legal.PkgTestContractClause",
        description="A clause from a contract",
    )

    CONCEPT_WITH_REFINES: ClassVar[ConceptEntry] = ConceptEntry(
        concept_code="PkgTestRefinedScore",
        domain_code="pkg_test_refining",
        concept_ref="pkg_test_refining.PkgTestRefinedScore",
        description="A refined score",
        refines="scoring_dep->pkg_test_scoring_dep.PkgTestWeightedScore",
    )

    CONCEPT_WITH_STRUCTURE: ClassVar[ConceptEntry] = ConceptEntry(
        concept_code="PkgTestDetailedScore",
        domain_code="pkg_test_scoring",
        concept_ref="pkg_test_scoring.PkgTestDetailedScore",
        description="A detailed score with fields",
        structure_fields=["score_value", "confidence", "explanation"],
    )

    DOMAIN_ENTRY: ClassVar[DomainEntry] = DomainEntry(
        domain_code="pkg_test_legal",
        description="Legal analysis tools",
    )

    ENTRY: ClassVar[PackageIndexEntry] = PackageIndexEntry(
        address="github.com/pipelexlab/legal-tools",
        display_name="Legal Tools",
        version="1.0.0",
        description="Legal document analysis tools",
        authors=["PipelexLab"],
        license="MIT",
        domains=[DomainEntry(domain_code="pkg_test_legal", description="Legal tools")],
        concepts=[
            ConceptEntry(
                concept_code="PkgTestContractClause",
                domain_code="pkg_test_legal",
                concept_ref="pkg_test_legal.PkgTestContractClause",
                description="A clause from a contract",
            )
        ],
        pipes=[
            PipeSignature(
                pipe_code="pkg_test_extract",
                pipe_type="PipeLLM",
                domain_code="pkg_test_legal",
                description="Extract clauses",
                input_specs={"text": "Text"},
                output_spec="PkgTestContractClause",
                is_exported=True,
            )
        ],
        dependencies=["github.com/pipelexlab/scoring-lib"],
        dependency_aliases={"scoring_dep": "github.com/pipelexlab/scoring-lib"},
    )

    ENTRY_B: ClassVar[PackageIndexEntry] = PackageIndexEntry(
        address="github.com/pipelexlab/scoring-lib",
        version="2.0.0",
        description="Scoring library",
        pipes=[
            PipeSignature(
                pipe_code="pkg_test_score",
                pipe_type="PipeLLM",
                domain_code="pkg_test_scoring",
                description="Score items",
                input_specs={"item": "Text"},
                output_spec="PkgTestScoreResult",
                is_exported=True,
            )
        ],
    )


class TestIndexModels:
    """Tests for package index data models."""

    def test_pipe_signature_is_frozen(self) -> None:
        """PipeSignature fields cannot be mutated."""
        with pytest.raises(ValidationError):
            TestData.PIPE_SIG.pipe_code = "changed"  # type: ignore[misc]

    def test_concept_entry_without_refines(self) -> None:
        """ConceptEntry can be created without refines or structure_fields."""
        entry = TestData.CONCEPT_ENTRY
        assert entry.concept_code == "PkgTestContractClause"
        assert entry.refines is None
        assert entry.structure_fields == []

    def test_concept_entry_with_refines(self) -> None:
        """ConceptEntry stores cross-package refines references."""
        entry = TestData.CONCEPT_WITH_REFINES
        assert entry.refines == "scoring_dep->pkg_test_scoring_dep.PkgTestWeightedScore"

    def test_concept_entry_with_structure_fields(self) -> None:
        """ConceptEntry stores structure field names."""
        entry = TestData.CONCEPT_WITH_STRUCTURE
        assert entry.structure_fields == ["score_value", "confidence", "explanation"]

    def test_domain_entry_with_description(self) -> None:
        """DomainEntry stores domain code and optional description."""
        entry = TestData.DOMAIN_ENTRY
        assert entry.domain_code == "pkg_test_legal"
        assert entry.description == "Legal analysis tools"

    def test_domain_entry_without_description(self) -> None:
        """DomainEntry allows None description."""
        entry = DomainEntry(domain_code="pkg_test_minimal", description=None)
        assert entry.description is None

    def test_package_index_entry_fields(self) -> None:
        """PackageIndexEntry stores all expected metadata."""
        entry = TestData.ENTRY
        assert entry.address == "github.com/pipelexlab/legal-tools"
        assert entry.display_name == "Legal Tools"
        assert entry.version == "1.0.0"
        assert entry.description == "Legal document analysis tools"
        assert entry.authors == ["PipelexLab"]
        assert entry.license == "MIT"
        assert len(entry.domains) == 1
        assert len(entry.concepts) == 1
        assert len(entry.pipes) == 1
        assert entry.dependencies == ["github.com/pipelexlab/scoring-lib"]
        assert entry.dependency_aliases == {"scoring_dep": "github.com/pipelexlab/scoring-lib"}

    def test_package_index_entry_is_frozen(self) -> None:
        """PackageIndexEntry fields cannot be mutated."""
        with pytest.raises(ValidationError):
            TestData.ENTRY.version = "2.0.0"  # type: ignore[misc]

    def test_pipe_signature_input_output(self) -> None:
        """PipeSignature stores input specs and output spec as strings."""
        sig = TestData.PIPE_SIG
        assert sig.input_specs == {"text": "Text"}
        assert sig.output_spec == "PkgTestContractClause"

    def test_package_index_add_and_get(self) -> None:
        """PackageIndex.add_entry stores and get_entry retrieves by address."""
        index = PackageIndex()
        index.add_entry(TestData.ENTRY)
        result = index.get_entry("github.com/pipelexlab/legal-tools")
        assert result is not None
        assert result.address == "github.com/pipelexlab/legal-tools"

    def test_package_index_get_nonexistent(self) -> None:
        """PackageIndex.get_entry returns None for unknown address."""
        index = PackageIndex()
        assert index.get_entry("github.com/nonexistent") is None

    def test_package_index_remove(self) -> None:
        """PackageIndex.remove_entry removes and returns True, or False if not found."""
        index = PackageIndex()
        index.add_entry(TestData.ENTRY)
        assert index.remove_entry("github.com/pipelexlab/legal-tools") is True
        assert index.get_entry("github.com/pipelexlab/legal-tools") is None
        assert index.remove_entry("github.com/pipelexlab/legal-tools") is False

    def test_package_index_replace_entry(self) -> None:
        """PackageIndex.add_entry replaces an existing entry with the same address."""
        index = PackageIndex()
        index.add_entry(TestData.ENTRY)
        updated = PackageIndexEntry(
            address="github.com/pipelexlab/legal-tools",
            version="2.0.0",
            description="Updated",
        )
        index.add_entry(updated)
        result = index.get_entry("github.com/pipelexlab/legal-tools")
        assert result is not None
        assert result.version == "2.0.0"

    def test_package_index_all_concepts(self) -> None:
        """PackageIndex.all_concepts returns concepts from all entries."""
        index = PackageIndex()
        index.add_entry(TestData.ENTRY)
        index.add_entry(TestData.ENTRY_B)
        all_concepts = index.all_concepts()
        assert len(all_concepts) == 1  # Only ENTRY has a concept
        assert all_concepts[0][0] == "github.com/pipelexlab/legal-tools"
        assert all_concepts[0][1].concept_code == "PkgTestContractClause"

    def test_package_index_all_pipes(self) -> None:
        """PackageIndex.all_pipes returns pipes from all entries."""
        index = PackageIndex()
        index.add_entry(TestData.ENTRY)
        index.add_entry(TestData.ENTRY_B)
        all_pipes = index.all_pipes()
        assert len(all_pipes) == 2
        pipe_codes = {pipe.pipe_code for _, pipe in all_pipes}
        assert pipe_codes == {"pkg_test_extract", "pkg_test_score"}
