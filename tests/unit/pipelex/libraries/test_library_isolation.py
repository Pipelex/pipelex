from pytest_mock import MockerFixture

from pipelex.core.concepts.concept import Concept
from pipelex.libraries.concept.concept_library import ConceptLibrary
from pipelex.libraries.domain.domain_library import DomainLibrary
from pipelex.libraries.library import Library
from pipelex.libraries.library_factory import LibraryFactory
from pipelex.libraries.pipe.pipe_library import PipeLibrary


def _make_stub_concept(code: str, domain_code: str) -> Concept:
    """Create a minimal Concept for testing."""
    return Concept(
        code=code,
        domain_code=domain_code,
        description="Test concept",
        structure_class_name="TextContent",
    )


def _make_child_library() -> Library:
    """Create a minimal child library (no native concepts needed)."""
    return Library(
        domain_library=DomainLibrary.make_empty(),
        concept_library=ConceptLibrary.make_empty(),
        pipe_library=PipeLibrary.make_empty(),
    )


class TestLibraryIsolation:
    """Tests for per-package library isolation via dependency_libraries."""

    def test_dependency_library_created(self):
        """dependency_libraries field exists and starts empty on a fresh Library."""
        library = LibraryFactory.make_empty()
        assert library.dependency_libraries == {}

    def test_register_and_get_dependency_library(self):
        """get_dependency_library() retrieves a registered child library."""
        library = LibraryFactory.make_empty()
        child = _make_child_library()
        library.dependency_libraries["scoring_dep"] = child
        assert library.get_dependency_library("scoring_dep") is child

    def test_get_dependency_library_returns_none_for_missing(self):
        """get_dependency_library() returns None for unknown alias."""
        library = LibraryFactory.make_empty()
        assert library.get_dependency_library("unknown") is None

    def test_concept_isolation_no_native_key_in_main(self):
        """Concepts in child library are NOT in main concept_library with native keys."""
        library = LibraryFactory.make_empty()
        child = _make_child_library()
        concept = _make_stub_concept(code="WeightedScore", domain_code="scoring")
        child.concept_library.add_new_concept(concept)
        library.dependency_libraries["scoring_dep"] = child

        # The concept should NOT be in the main library with its native key
        assert not library.concept_library.is_concept_exists("scoring.WeightedScore")

    def test_cross_package_lookup_via_alias(self):
        """Cross-package concept lookup via aliased key in main library works."""
        library = LibraryFactory.make_empty()
        child = _make_child_library()
        concept = _make_stub_concept(code="WeightedScore", domain_code="scoring")
        child.concept_library.add_new_concept(concept)
        library.dependency_libraries["scoring_dep"] = child

        # Add aliased entry to main library (as _load_single_dependency does)
        library.concept_library.add_dependency_concept(alias="scoring_dep", concept=concept)

        result = library.concept_library.get_required_concept("scoring_dep->scoring.WeightedScore")
        assert result.code == "WeightedScore"

    def test_resolve_concept_routes_through_child(self):
        """resolve_concept() routes cross-package refs through child library."""
        library = LibraryFactory.make_empty()
        child = _make_child_library()
        concept = _make_stub_concept(code="WeightedScore", domain_code="scoring")
        child.concept_library.add_new_concept(concept)
        library.dependency_libraries["scoring_dep"] = child

        resolved = library.resolve_concept("scoring_dep->scoring.WeightedScore")
        assert resolved is not None
        assert resolved.code == "WeightedScore"
        assert resolved.concept_ref == "scoring.WeightedScore"

    def test_resolve_concept_returns_none_for_missing_alias(self):
        """resolve_concept() returns None when alias has no child library."""
        library = LibraryFactory.make_empty()
        assert library.resolve_concept("unknown_dep->scoring.WeightedScore") is None

    def test_resolve_concept_returns_none_for_missing_concept_in_child(self):
        """resolve_concept() returns None when concept not in child library."""
        library = LibraryFactory.make_empty()
        child = _make_child_library()
        library.dependency_libraries["scoring_dep"] = child
        assert library.resolve_concept("scoring_dep->scoring.Missing") is None

    def test_resolve_concept_local_ref(self):
        """resolve_concept() falls back to main library for local refs."""
        library = LibraryFactory.make_empty()
        concept = _make_stub_concept(code="LocalConcept", domain_code="local")
        library.concept_library.add_new_concept(concept)

        resolved = library.resolve_concept("local.LocalConcept")
        assert resolved is not None
        assert resolved.code == "LocalConcept"

    def test_teardown_cleans_children(self):
        """teardown() clears dependency_libraries."""
        library = LibraryFactory.make_empty()
        child = _make_child_library()
        concept = _make_stub_concept(code="WeightedScore", domain_code="scoring")
        child.concept_library.add_new_concept(concept)
        library.dependency_libraries["scoring_dep"] = child

        library.teardown()
        assert library.dependency_libraries == {}

    def test_concept_name_collision_two_deps(self):
        """Two deps with same concept code in different domains cause no conflict."""
        library = LibraryFactory.make_empty()

        # First dep: scoring_dep with PkgTestWeightedScore in scoring domain
        child_scoring = _make_child_library()
        scoring_concept = _make_stub_concept(code="PkgTestWeightedScore", domain_code="pkg_test_scoring_dep")
        child_scoring.concept_library.add_new_concept(scoring_concept)
        library.dependency_libraries["scoring_dep"] = child_scoring

        # Second dep: analytics_dep with PkgTestWeightedScore in analytics domain
        child_analytics = _make_child_library()
        analytics_concept = _make_stub_concept(code="PkgTestWeightedScore", domain_code="pkg_test_analytics_dep")
        child_analytics.concept_library.add_new_concept(analytics_concept)
        library.dependency_libraries["analytics_dep"] = child_analytics

        # Add aliased entries to main library
        library.concept_library.add_dependency_concept(alias="scoring_dep", concept=scoring_concept)
        library.concept_library.add_dependency_concept(alias="analytics_dep", concept=analytics_concept)

        # Both resolve correctly through their own child libraries
        resolved_scoring = library.resolve_concept("scoring_dep->pkg_test_scoring_dep.PkgTestWeightedScore")
        resolved_analytics = library.resolve_concept("analytics_dep->pkg_test_analytics_dep.PkgTestWeightedScore")
        assert resolved_scoring is not None
        assert resolved_analytics is not None
        assert resolved_scoring.domain_code == "pkg_test_scoring_dep"
        assert resolved_analytics.domain_code == "pkg_test_analytics_dep"

    def test_has_unresolved_cross_package_deps_with_child_library(self, mocker: MockerFixture):
        """_has_unresolved_cross_package_deps returns False when alias has child library."""
        library = LibraryFactory.make_empty()
        child = _make_child_library()
        library.dependency_libraries["scoring_dep"] = child

        mock_pipe = mocker.MagicMock()
        mock_pipe.pipe_dependencies.return_value = ["scoring_dep->pkg_test_scoring_dep.pkg_test_compute_score"]

        # Even though the pipe isn't in the main pipe library, the alias has a child library
        assert library._has_unresolved_cross_package_deps(mock_pipe) is False  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

    def test_has_unresolved_cross_package_deps_without_child_library(self, mocker: MockerFixture):
        """_has_unresolved_cross_package_deps returns True when alias has no child library."""
        library = LibraryFactory.make_empty()

        mock_pipe = mocker.MagicMock()
        mock_pipe.pipe_dependencies.return_value = ["unknown_dep->domain.pipe"]

        assert library._has_unresolved_cross_package_deps(mock_pipe) is True  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
