import pytest

from pipelex.core.concepts.concept import Concept
from pipelex.libraries.concept.concept_library import ConceptLibrary
from pipelex.libraries.concept.exceptions import ConceptLibraryError
from pipelex.libraries.domain.domain_library import DomainLibrary
from pipelex.libraries.exceptions import LibraryError
from pipelex.libraries.library import Library
from pipelex.libraries.library_factory import LibraryFactory
from pipelex.libraries.pipe.pipe_library import PipeLibrary


def _make_stub_concept(code: str, domain_code: str, refines: str | None = None) -> Concept:
    """Create a minimal Concept for testing."""
    return Concept(
        code=code,
        domain_code=domain_code,
        description="Test concept",
        structure_class_name="TextContent",
        refines=refines,
    )


def _make_child_library() -> Library:
    """Create a minimal child library (no native concepts needed)."""
    return Library(
        domain_library=DomainLibrary.make_empty(),
        concept_library=ConceptLibrary.make_empty(),
        pipe_library=PipeLibrary.make_empty(),
    )


class TestConceptValidationCrossPackageLibrary:
    """Tests for cross-package concept validation at the library level."""

    def test_validation_static_skips_cross_package_refines(self):
        """validation_static should not raise for cross-package refines even though target is not in root."""
        concept = _make_stub_concept(
            code="RefinedScore",
            domain_code="my_domain",
            refines="scoring_dep->scoring.WeightedScore",
        )
        # This should NOT raise, because cross-package refines are skipped
        library = ConceptLibrary(root={"my_domain.RefinedScore": concept})
        assert "my_domain.RefinedScore" in library.root

    def test_validation_static_still_catches_missing_local_refines(self):
        """validation_static still raises for missing local refines targets."""
        concept = _make_stub_concept(
            code="RefinedScore",
            domain_code="my_domain",
            refines="my_domain.MissingBase",
        )
        with pytest.raises(ConceptLibraryError, match="no concept with the code"):
            ConceptLibrary(root={"my_domain.RefinedScore": concept})

    def test_validate_concept_library_catches_missing_cross_package_target(self):
        """validate_concept_library_with_libraries raises when cross-package target is missing in loaded dep."""
        library = LibraryFactory.make_empty()
        # Add child library that is empty (target concept not present)
        child = _make_child_library()
        library.dependency_libraries["scoring_dep"] = child

        # Add concept with cross-package refines to main library
        concept = _make_stub_concept(
            code="RefinedScore",
            domain_code="my_domain",
            refines="scoring_dep->scoring.WeightedScore",
        )
        library.concept_library.add_new_concept(concept)

        with pytest.raises(LibraryError, match="was not found in dependency"):
            library.validate_concept_library_with_libraries()

    def test_validate_concept_library_passes_with_loaded_dependency(self):
        """validate_concept_library_with_libraries passes when target exists in child library."""
        library = LibraryFactory.make_empty()
        child = _make_child_library()
        target_concept = _make_stub_concept(code="WeightedScore", domain_code="scoring")
        child.concept_library.add_new_concept(target_concept)
        library.dependency_libraries["scoring_dep"] = child

        # Add concept with cross-package refines
        concept = _make_stub_concept(
            code="RefinedScore",
            domain_code="my_domain",
            refines="scoring_dep->scoring.WeightedScore",
        )
        library.concept_library.add_new_concept(concept)

        # Should not raise
        library.validate_concept_library_with_libraries()

    def test_validate_concept_library_skips_unloaded_dependency(self):
        """validate_concept_library_with_libraries skips validation for unloaded dependencies."""
        library = LibraryFactory.make_empty()
        # No child library registered for "unknown_dep"

        concept = _make_stub_concept(
            code="RefinedScore",
            domain_code="my_domain",
            refines="unknown_dep->scoring.WeightedScore",
        )
        library.concept_library.add_new_concept(concept)

        # Should not raise — skips validation for unloaded deps
        library.validate_concept_library_with_libraries()
