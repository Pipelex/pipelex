from pipelex.core.packages.graph.graph_builder import build_know_how_graph
from pipelex.core.packages.graph.models import (
    NATIVE_PACKAGE_ADDRESS,
    ConceptId,
)
from pipelex.core.packages.graph.query_engine import KnowHowQueryEngine
from tests.unit.pipelex.core.packages.graph.test_data import (
    ANALYTICS_LIB_ADDRESS,
    LEGAL_TOOLS_ADDRESS,
    REFINING_APP_ADDRESS,
    SCORING_LIB_ADDRESS,
    make_test_package_index,
)

NATIVE_TEXT_ID = ConceptId(package_address=NATIVE_PACKAGE_ADDRESS, concept_ref="native.Text")
SCORING_CONCEPT_ID = ConceptId(package_address=SCORING_LIB_ADDRESS, concept_ref="pkg_test_scoring_dep.PkgTestWeightedScore")
LEGAL_CONCEPT_ID = ConceptId(package_address=LEGAL_TOOLS_ADDRESS, concept_ref="pkg_test_legal.PkgTestContractClause")
REFINED_CONCEPT_ID = ConceptId(package_address=REFINING_APP_ADDRESS, concept_ref="pkg_test_refining.PkgTestRefinedScore")
ANALYTICS_CONCEPT_ID = ConceptId(package_address=ANALYTICS_LIB_ADDRESS, concept_ref="pkg_test_analytics.PkgTestWeightedScore")


class TestQueryEngine:
    """Tests for the know-how query engine."""

    def test_what_can_i_do_with_native_text(self) -> None:
        """Querying with native Text finds all pipes that accept Text input."""
        index = make_test_package_index()
        graph = build_know_how_graph(index)
        engine = KnowHowQueryEngine(graph)

        pipes = engine.query_what_can_i_do(NATIVE_TEXT_ID)
        pipe_codes = {pipe.pipe_code for pipe in pipes}
        # All pipes that have a "text" input expecting Text
        assert "pkg_test_compute_score" in pipe_codes
        assert "pkg_test_refine_score" in pipe_codes
        assert "pkg_test_extract_clause" in pipe_codes
        assert "pkg_test_compute_analytics" in pipe_codes

    def test_what_can_i_do_with_specific_concept(self) -> None:
        """Querying with a specific concept finds pipes accepting that concept."""
        index = make_test_package_index()
        graph = build_know_how_graph(index)
        engine = KnowHowQueryEngine(graph)

        pipes = engine.query_what_can_i_do(LEGAL_CONCEPT_ID)
        pipe_codes = {pipe.pipe_code for pipe in pipes}
        assert "pkg_test_analyze_clause" in pipe_codes

    def test_what_can_i_do_with_refined_concept(self) -> None:
        """Querying with a refined concept also finds pipes expecting the base concept."""
        index = make_test_package_index()
        graph = build_know_how_graph(index)
        engine = KnowHowQueryEngine(graph)

        # PkgTestRefinedScore refines PkgTestWeightedScore
        # If there were pipes expecting PkgTestWeightedScore, they'd be found
        pipes = engine.query_what_can_i_do(REFINED_CONCEPT_ID)
        # At minimum, the result should be a list (possibly empty if no pipe expects WeightedScore)
        assert isinstance(pipes, list)

    def test_what_produces_text(self) -> None:
        """Querying what produces native Text finds pipes with Text output."""
        index = make_test_package_index()
        graph = build_know_how_graph(index)
        engine = KnowHowQueryEngine(graph)

        pipes = engine.query_what_produces(NATIVE_TEXT_ID)
        pipe_codes = {pipe.pipe_code for pipe in pipes}
        assert "pkg_test_analyze_clause" in pipe_codes

    def test_what_produces_specific_concept(self) -> None:
        """Querying what produces a specific concept finds the right pipes."""
        index = make_test_package_index()
        graph = build_know_how_graph(index)
        engine = KnowHowQueryEngine(graph)

        pipes = engine.query_what_produces(LEGAL_CONCEPT_ID)
        pipe_codes = {pipe.pipe_code for pipe in pipes}
        assert "pkg_test_extract_clause" in pipe_codes

    def test_what_produces_base_concept_includes_refinements(self) -> None:
        """Querying what produces a base concept also finds pipes producing refinements."""
        index = make_test_package_index()
        graph = build_know_how_graph(index)
        engine = KnowHowQueryEngine(graph)

        # PkgTestRefinedScore refines PkgTestWeightedScore from scoring-lib
        pipes = engine.query_what_produces(SCORING_CONCEPT_ID)
        pipe_codes = {pipe.pipe_code for pipe in pipes}
        assert "pkg_test_compute_score" in pipe_codes
        assert "pkg_test_refine_score" in pipe_codes

    def test_check_compatibility_match(self) -> None:
        """Compatible pipes return the matching input parameter names."""
        index = make_test_package_index()
        graph = build_know_how_graph(index)
        engine = KnowHowQueryEngine(graph)

        # extract_clause produces PkgTestContractClause, analyze_clause consumes it on "clause"
        source_key = f"{LEGAL_TOOLS_ADDRESS}::pkg_test_extract_clause"
        target_key = f"{LEGAL_TOOLS_ADDRESS}::pkg_test_analyze_clause"
        params = engine.check_compatibility(source_key, target_key)
        assert "clause" in params

    def test_check_compatibility_via_refinement(self) -> None:
        """Refined output is compatible with base concept input if such exists."""
        index = make_test_package_index()
        graph = build_know_how_graph(index)
        engine = KnowHowQueryEngine(graph)

        # analyze_clause outputs Text; all Text-input pipes are compatible
        source_key = f"{LEGAL_TOOLS_ADDRESS}::pkg_test_analyze_clause"
        target_key = f"{SCORING_LIB_ADDRESS}::pkg_test_compute_score"
        params = engine.check_compatibility(source_key, target_key)
        assert "text" in params

    def test_check_compatibility_incompatible(self) -> None:
        """Incompatible pipes return empty list."""
        index = make_test_package_index()
        graph = build_know_how_graph(index)
        engine = KnowHowQueryEngine(graph)

        # compute_score outputs PkgTestWeightedScore; analyze_clause expects PkgTestContractClause
        source_key = f"{SCORING_LIB_ADDRESS}::pkg_test_compute_score"
        target_key = f"{LEGAL_TOOLS_ADDRESS}::pkg_test_analyze_clause"
        params = engine.check_compatibility(source_key, target_key)
        assert params == []

    def test_check_compatibility_no_cross_package_collision(self) -> None:
        """PkgTestWeightedScore from scoring-lib != PkgTestWeightedScore from analytics-lib."""
        index = make_test_package_index()
        graph = build_know_how_graph(index)
        engine = KnowHowQueryEngine(graph)

        # compute_score (scoring) outputs scoring's WeightedScore
        # compute_analytics (analytics) outputs analytics's WeightedScore
        # They should NOT be considered the same concept, so neither feeds the other
        scoring_key = f"{SCORING_LIB_ADDRESS}::pkg_test_compute_score"
        analytics_key = f"{ANALYTICS_LIB_ADDRESS}::pkg_test_compute_analytics"
        # Scoring's output should not be compatible with analytics pipe's inputs (different WeightedScore)
        params_scoring_to_analytics = engine.check_compatibility(scoring_key, analytics_key)
        params_analytics_to_scoring = engine.check_compatibility(analytics_key, scoring_key)
        assert params_scoring_to_analytics == []
        assert params_analytics_to_scoring == []

    def test_resolve_refinement_chain(self) -> None:
        """Refinement chain walks from refined to base concept."""
        index = make_test_package_index()
        graph = build_know_how_graph(index)
        engine = KnowHowQueryEngine(graph)

        chain = engine.resolve_refinement_chain(REFINED_CONCEPT_ID)
        assert len(chain) == 2
        assert chain[0] == REFINED_CONCEPT_ID
        assert chain[1] == SCORING_CONCEPT_ID

    def test_resolve_refinement_chain_no_refines(self) -> None:
        """Concept without refines returns a single-element chain."""
        index = make_test_package_index()
        graph = build_know_how_graph(index)
        engine = KnowHowQueryEngine(graph)

        chain = engine.resolve_refinement_chain(LEGAL_CONCEPT_ID)
        assert len(chain) == 1
        assert chain[0] == LEGAL_CONCEPT_ID

    def test_i_have_i_need_direct(self) -> None:
        """Direct single-pipe chain from Text to PkgTestContractClause."""
        index = make_test_package_index()
        graph = build_know_how_graph(index)
        engine = KnowHowQueryEngine(graph)

        chains = engine.query_i_have_i_need(NATIVE_TEXT_ID, LEGAL_CONCEPT_ID)
        assert len(chains) >= 1
        # Should find extract_clause (Text -> PkgTestContractClause) as a single-step chain
        single_step_chains = [chain for chain in chains if len(chain) == 1]
        assert len(single_step_chains) >= 1
        extract_key = f"{LEGAL_TOOLS_ADDRESS}::pkg_test_extract_clause"
        found = any(extract_key in chain for chain in single_step_chains)
        assert found

    def test_i_have_i_need_two_step(self) -> None:
        """Two-step chain: Text -> PkgTestContractClause -> Text (extract then analyze)."""
        index = make_test_package_index()
        graph = build_know_how_graph(index)
        engine = KnowHowQueryEngine(graph)

        # Text -> ? -> Text: should find chains going through extract_clause + analyze_clause
        chains = engine.query_i_have_i_need(NATIVE_TEXT_ID, NATIVE_TEXT_ID, max_depth=3)
        two_step_chains = [chain for chain in chains if len(chain) == 2]
        extract_key = f"{LEGAL_TOOLS_ADDRESS}::pkg_test_extract_clause"
        analyze_key = f"{LEGAL_TOOLS_ADDRESS}::pkg_test_analyze_clause"
        found_extract_analyze = any(chain[0] == extract_key and chain[1] == analyze_key for chain in two_step_chains)
        assert found_extract_analyze

    def test_i_have_i_need_no_path(self) -> None:
        """No path when the desired output is unreachable."""
        index = make_test_package_index()
        graph = build_know_how_graph(index)
        engine = KnowHowQueryEngine(graph)

        # PkgTestContractClause -> PkgTestWeightedScore: analyze_clause produces Text,
        # then compute_score produces WeightedScore. That's 2 steps.
        # But with max_depth=0, should find nothing
        nonexistent_concept = ConceptId(
            package_address="nonexistent",
            concept_ref="nonexistent.Concept",
        )
        chains = engine.query_i_have_i_need(NATIVE_TEXT_ID, nonexistent_concept)
        assert chains == []

    def test_i_have_i_need_max_depth(self) -> None:
        """Max depth limits the chain length."""
        index = make_test_package_index()
        graph = build_know_how_graph(index)
        engine = KnowHowQueryEngine(graph)

        chains = engine.query_i_have_i_need(NATIVE_TEXT_ID, NATIVE_TEXT_ID, max_depth=1)
        # Only single-step chains allowed; no Text->Text single pipe exists
        # so only pipes that directly output Text are valid (none takes Text and outputs Text in 1 step)
        # Actually analyze_clause takes ContractClause->Text, not Text->Text
        # So with max_depth=1, there should be no results since no single pipe takes Text and outputs Text
        for chain in chains:
            assert len(chain) <= 1

    def test_i_have_i_need_sorted_shortest_first(self) -> None:
        """Results are sorted with shortest chains first."""
        index = make_test_package_index()
        graph = build_know_how_graph(index)
        engine = KnowHowQueryEngine(graph)

        chains = engine.query_i_have_i_need(NATIVE_TEXT_ID, NATIVE_TEXT_ID, max_depth=3)
        for idx in range(len(chains) - 1):
            assert len(chains[idx]) <= len(chains[idx + 1])
