import pytest
from pytest_mock import MockerFixture

from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_factory import ConceptFactory, DomainAndConceptCode
from pipelex.core.concepts.exceptions import ConceptFactoryError
from pipelex.core.qualified_ref import QualifiedRef
from pipelex.libraries.concept.concept_library import ConceptLibrary
from pipelex.libraries.concept.exceptions import ConceptLibraryError
from pipelex.libraries.pipe.exceptions import PipeLibraryError
from pipelex.libraries.pipe.pipe_library import PipeLibrary


def _make_stub_concept(code: str, domain_code: str) -> Concept:
    """Create a minimal Concept for testing."""
    return Concept(
        code=code,
        domain_code=domain_code,
        description="Test concept",
        structure_class_name="TextContent",
    )


class TestCrossPackageLoading:
    """Tests for cross-package pipe and concept loading/lookup."""

    def test_pipe_library_add_dependency_pipe(self, mocker: MockerFixture):
        """add_dependency_pipe() stores pipe with aliased key."""
        library = PipeLibrary.make_empty()
        mock_pipe = mocker.MagicMock()
        mock_pipe.code = "compute_score"
        library.add_dependency_pipe(alias="scoring_lib", pipe=mock_pipe)
        assert "scoring_lib->compute_score" in library.root

    def test_pipe_library_get_optional_cross_package_ref(self, mocker: MockerFixture):
        """get_optional_pipe() resolves 'alias->domain.pipe_code' to 'alias->pipe_code'."""
        library = PipeLibrary.make_empty()
        mock_pipe = mocker.MagicMock()
        mock_pipe.code = "compute_score"
        library.add_dependency_pipe(alias="scoring_lib", pipe=mock_pipe)

        result = library.get_optional_pipe("scoring_lib->scoring.compute_score")
        assert result is not None
        assert result.code == "compute_score"

    def test_pipe_library_get_optional_cross_package_direct_key(self, mocker: MockerFixture):
        """get_optional_pipe() resolves direct 'alias->pipe_code' key."""
        library = PipeLibrary.make_empty()
        mock_pipe = mocker.MagicMock()
        mock_pipe.code = "compute_score"
        library.add_dependency_pipe(alias="scoring_lib", pipe=mock_pipe)

        result = library.get_optional_pipe("scoring_lib->compute_score")
        assert result is not None
        assert result.code == "compute_score"

    def test_pipe_library_duplicate_dependency_pipe_raises(self, mocker: MockerFixture):
        """add_dependency_pipe() raises on duplicate."""
        library = PipeLibrary.make_empty()
        mock_pipe = mocker.MagicMock()
        mock_pipe.code = "compute_score"
        library.add_dependency_pipe(alias="scoring_lib", pipe=mock_pipe)
        with pytest.raises(PipeLibraryError, match="already exists"):
            library.add_dependency_pipe(alias="scoring_lib", pipe=mock_pipe)

    def test_concept_library_add_dependency_concept(self):
        """add_dependency_concept() stores concept with aliased key."""
        library = ConceptLibrary.make_empty()
        concept = _make_stub_concept(code="WeightedScore", domain_code="scoring")
        library.add_dependency_concept(alias="scoring_lib", concept=concept)
        assert "scoring_lib->scoring.WeightedScore" in library.root

    def test_concept_library_get_required_cross_package_ref(self):
        """get_required_concept() resolves cross-package refs."""
        library = ConceptLibrary.make_empty()
        concept = _make_stub_concept(code="WeightedScore", domain_code="scoring")
        library.add_dependency_concept(alias="scoring_lib", concept=concept)

        result = library.get_required_concept("scoring_lib->scoring.WeightedScore")
        assert result.code == "WeightedScore"

    def test_concept_library_cross_package_not_found(self):
        """get_required_concept() raises when cross-package concept not loaded."""
        library = ConceptLibrary.make_empty()
        with pytest.raises(ConceptLibraryError, match="not found"):
            library.get_required_concept("unknown_lib->domain.Missing")

    def test_concept_library_duplicate_dependency_concept_raises(self):
        """add_dependency_concept() raises on duplicate aliased key."""
        library = ConceptLibrary.make_empty()
        concept = _make_stub_concept(code="WeightedScore", domain_code="scoring")
        library.add_dependency_concept(alias="scoring_lib", concept=concept)
        with pytest.raises(ConceptLibraryError, match="already exists"):
            library.add_dependency_concept(alias="scoring_lib", concept=concept)

    def test_concept_factory_cross_package_domain_and_code(self):
        """ConceptFactory resolves cross-package refs to aliased domain codes."""
        result = ConceptFactory.make_domain_and_concept_code_from_concept_ref_or_code(
            concept_ref_or_code="scoring_lib->scoring.WeightedScore",
        )
        assert isinstance(result, DomainAndConceptCode)
        assert result.domain_code == "scoring_lib->scoring"
        assert result.concept_code == "WeightedScore"

    def test_concept_factory_cross_package_requires_domain(self):
        """Cross-package concept ref without domain raises error."""
        with pytest.raises(ConceptFactoryError, match="must include a domain"):
            ConceptFactory.make_domain_and_concept_code_from_concept_ref_or_code(
                concept_ref_or_code="scoring_lib->WeightedScore",
            )

    def test_concept_factory_make_refine_cross_package(self):
        """make_refine() passes through cross-package refs unchanged."""
        result = ConceptFactory.make_refine(
            refine="scoring_lib->scoring.BaseScore",
            domain_code="my_domain",
        )
        assert result == "scoring_lib->scoring.BaseScore"

    def test_qualified_ref_has_cross_package_prefix(self):
        """QualifiedRef.has_cross_package_prefix detects '->' syntax."""
        assert QualifiedRef.has_cross_package_prefix("lib->domain.pipe") is True
        assert QualifiedRef.has_cross_package_prefix("domain.pipe") is False

    def test_qualified_ref_split_cross_package_ref(self):
        """QualifiedRef.split_cross_package_ref splits correctly."""
        alias, remainder = QualifiedRef.split_cross_package_ref("scoring_lib->scoring.compute_score")
        assert alias == "scoring_lib"
        assert remainder == "scoring.compute_score"
