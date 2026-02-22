from pathlib import Path

from pipelex.hub import get_library_manager, set_current_library
from pipelex.libraries.library_manager_abstract import LibraryManagerAbstract

# Path to the physical test data
PACKAGES_DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent / "data" / "packages"


class TestLibraryIsolationIntegration:
    """Integration tests for per-package library isolation using physical test fixtures."""

    def _setup_library_for_path(self, mthds_paths: list[Path]) -> tuple[LibraryManagerAbstract, str]:
        """Set up a library manager with the hub's current library for the given paths."""
        library_manager = get_library_manager()
        library_id, _library = library_manager.open_library()
        set_current_library(library_id=library_id)
        library_manager.load_libraries(library_id=library_id, library_file_paths=mthds_paths)
        return library_manager, library_id

    def test_consumer_loads_with_isolated_dependency(self):
        """Consumer package loads with dependency in isolated child library."""
        consumer_mthds = [PACKAGES_DATA_DIR / "consumer_package" / "analysis.mthds"]
        manager, library_id = self._setup_library_for_path(consumer_mthds)
        library = manager.get_library(library_id)

        # scoring_dep should be registered as a child library
        child = library.get_dependency_library("scoring_dep")
        assert child is not None

        # Child should have the scoring concept
        scoring_concept = child.concept_library.get_optional_concept("pkg_test_scoring_dep.PkgTestWeightedScore")
        assert scoring_concept is not None
        assert scoring_concept.code == "PkgTestWeightedScore"

        # Main library should NOT have the concept under its native key
        # (native-key workaround was removed)
        assert not library.concept_library.is_concept_exists("pkg_test_scoring_dep.PkgTestWeightedScore")

        # But aliased lookup should still work
        aliased = library.concept_library.get_optional_concept("scoring_dep->pkg_test_scoring_dep.PkgTestWeightedScore")
        assert aliased is not None

        manager.teardown(library_id=library_id)

    def test_cross_package_pipe_lookup_works(self):
        """Cross-package pipe lookup via aliased key works after loading."""
        consumer_mthds = [PACKAGES_DATA_DIR / "consumer_package" / "analysis.mthds"]
        manager, library_id = self._setup_library_for_path(consumer_mthds)
        library = manager.get_library(library_id)

        # Cross-package pipe should be findable via aliased key
        pipe = library.pipe_library.get_optional_pipe("scoring_dep->pkg_test_compute_score")
        assert pipe is not None
        assert pipe.code == "pkg_test_compute_score"

        # Child library should also have the pipe
        child = library.get_dependency_library("scoring_dep")
        assert child is not None
        child_pipe = child.pipe_library.get_optional_pipe("pkg_test_compute_score")
        assert child_pipe is not None

        manager.teardown(library_id=library_id)

    def test_two_deps_same_concept_code_both_load(self):
        """Two dependencies with same concept code load cleanly via isolation."""
        multi_mthds = [PACKAGES_DATA_DIR / "multi_dep_consumer" / "multi.mthds"]
        manager, library_id = self._setup_library_for_path(multi_mthds)
        library = manager.get_library(library_id)

        # Both child libraries should exist
        scoring_child = library.get_dependency_library("scoring_dep")
        analytics_child = library.get_dependency_library("analytics_dep")
        assert scoring_child is not None
        assert analytics_child is not None

        # Both have PkgTestWeightedScore but in different domains
        scoring_concept = scoring_child.concept_library.get_optional_concept("pkg_test_scoring_dep.PkgTestWeightedScore")
        analytics_concept = analytics_child.concept_library.get_optional_concept("pkg_test_analytics_dep.PkgTestWeightedScore")
        assert scoring_concept is not None
        assert analytics_concept is not None
        assert scoring_concept.domain_code == "pkg_test_scoring_dep"
        assert analytics_concept.domain_code == "pkg_test_analytics_dep"

        # Both resolvable via resolve_concept
        resolved_scoring = library.resolve_concept("scoring_dep->pkg_test_scoring_dep.PkgTestWeightedScore")
        resolved_analytics = library.resolve_concept("analytics_dep->pkg_test_analytics_dep.PkgTestWeightedScore")
        assert resolved_scoring is not None
        assert resolved_analytics is not None
        assert resolved_scoring.domain_code != resolved_analytics.domain_code

        manager.teardown(library_id=library_id)

    def test_refinement_chain_across_packages(self):
        """Consumer with concept refining cross-package concept loads and validates."""
        refining_mthds = [PACKAGES_DATA_DIR / "refining_consumer" / "refining.mthds"]
        manager, library_id = self._setup_library_for_path(refining_mthds)
        library = manager.get_library(library_id)

        # Child library should exist
        scoring_child = library.get_dependency_library("scoring_dep")
        assert scoring_child is not None

        # The refining concept should exist in main library
        refining_concept = library.concept_library.get_optional_concept("pkg_test_refining.PkgTestRefinedScore")
        assert refining_concept is not None
        assert refining_concept.refines == "scoring_dep->pkg_test_scoring_dep.PkgTestWeightedScore"

        # resolve_concept should find the target through the child library
        target = library.resolve_concept("scoring_dep->pkg_test_scoring_dep.PkgTestWeightedScore")
        assert target is not None
        assert target.code == "PkgTestWeightedScore"

        manager.teardown(library_id=library_id)

    def test_concept_resolver_wired_after_dep_loading(self):
        """The concept resolver is wired to the library after dependency loading."""
        consumer_mthds = [PACKAGES_DATA_DIR / "consumer_package" / "analysis.mthds"]
        manager, library_id = self._setup_library_for_path(consumer_mthds)
        library = manager.get_library(library_id)

        # The concept resolver should be set (it's a private attribute)
        assert library.concept_library._concept_resolver is not None  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        manager.teardown(library_id=library_id)
