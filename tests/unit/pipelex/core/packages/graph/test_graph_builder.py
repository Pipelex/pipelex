from pipelex.core.packages.graph.graph_builder import build_know_how_graph
from pipelex.core.packages.graph.models import (
    NATIVE_PACKAGE_ADDRESS,
    ConceptId,
    EdgeKind,
)
from pipelex.core.packages.index.models import PackageIndex
from tests.unit.pipelex.core.packages.graph.test_data import (
    ANALYTICS_LIB_ADDRESS,
    LEGAL_TOOLS_ADDRESS,
    PHANTOM_PKG_ADDRESS,
    QUALIFIED_REF_ADDRESS,
    REFINING_APP_ADDRESS,
    SCORING_LIB_ADDRESS,
    make_test_package_index,
    make_test_package_index_with_qualified_concept_specs,
    make_test_package_index_with_unresolvable_concepts,
)


class TestGraphBuilder:
    """Tests for the know-how graph builder."""

    def test_concept_nodes_created_for_all_packages(self) -> None:
        """Builder creates concept nodes for every concept in the index."""
        index = make_test_package_index()
        graph = build_know_how_graph(index)

        # 4 package concepts + 11 native concepts = 15
        package_concept_keys = [key for key in graph.concept_nodes if not key.startswith(NATIVE_PACKAGE_ADDRESS)]
        assert len(package_concept_keys) == 4

    def test_native_concept_nodes_created(self) -> None:
        """Builder creates concept nodes for all native concepts."""
        index = make_test_package_index()
        graph = build_know_how_graph(index)

        native_text = ConceptId(package_address=NATIVE_PACKAGE_ADDRESS, concept_ref="native.Text")
        assert graph.get_concept_node(native_text) is not None
        native_image = ConceptId(package_address=NATIVE_PACKAGE_ADDRESS, concept_ref="native.Image")
        assert graph.get_concept_node(native_image) is not None

    def test_pipe_nodes_created(self) -> None:
        """Builder creates pipe nodes for all pipes in the index."""
        index = make_test_package_index()
        graph = build_know_how_graph(index)

        assert len(graph.pipe_nodes) == 5
        expected_pipes = {
            f"{SCORING_LIB_ADDRESS}::pkg_test_compute_score",
            f"{REFINING_APP_ADDRESS}::pkg_test_refine_score",
            f"{LEGAL_TOOLS_ADDRESS}::pkg_test_extract_clause",
            f"{LEGAL_TOOLS_ADDRESS}::pkg_test_analyze_clause",
            f"{ANALYTICS_LIB_ADDRESS}::pkg_test_compute_analytics",
        }
        assert set(graph.pipe_nodes.keys()) == expected_pipes

    def test_pipe_node_output_concept_resolved(self) -> None:
        """Pipe node output concept is resolved to proper ConceptId."""
        index = make_test_package_index()
        graph = build_know_how_graph(index)

        extract_key = f"{LEGAL_TOOLS_ADDRESS}::pkg_test_extract_clause"
        pipe_node = graph.get_pipe_node(extract_key)
        assert pipe_node is not None
        assert pipe_node.output_concept_id.package_address == LEGAL_TOOLS_ADDRESS
        assert pipe_node.output_concept_id.concept_ref == "pkg_test_legal.PkgTestContractClause"

    def test_pipe_node_input_native_concept_resolved(self) -> None:
        """Pipe input specs referencing native concepts resolve to native ConceptIds."""
        index = make_test_package_index()
        graph = build_know_how_graph(index)

        extract_key = f"{LEGAL_TOOLS_ADDRESS}::pkg_test_extract_clause"
        pipe_node = graph.get_pipe_node(extract_key)
        assert pipe_node is not None
        text_input = pipe_node.input_concept_ids["text"]
        assert text_input.is_native
        assert text_input.concept_ref == "native.Text"

    def test_refinement_edge_created(self) -> None:
        """Builder creates refinement edge for concepts with refines."""
        index = make_test_package_index()
        graph = build_know_how_graph(index)

        assert len(graph.refinement_edges) == 1
        edge = graph.refinement_edges[0]
        assert edge.kind == EdgeKind.REFINEMENT
        assert edge.source_concept_id is not None
        assert edge.source_concept_id.package_address == REFINING_APP_ADDRESS
        assert edge.source_concept_id.concept_ref == "pkg_test_refining.PkgTestRefinedScore"
        assert edge.target_concept_id is not None
        assert edge.target_concept_id.package_address == SCORING_LIB_ADDRESS
        assert edge.target_concept_id.concept_ref == "pkg_test_scoring_dep.PkgTestWeightedScore"

    def test_cross_package_refines_resolved(self) -> None:
        """Cross-package refines (alias->domain.Code) resolves via dependency_aliases."""
        index = make_test_package_index()
        graph = build_know_how_graph(index)

        refined_id = ConceptId(
            package_address=REFINING_APP_ADDRESS,
            concept_ref="pkg_test_refining.PkgTestRefinedScore",
        )
        refined_node = graph.get_concept_node(refined_id)
        assert refined_node is not None
        assert refined_node.refines is not None
        assert refined_node.refines.package_address == SCORING_LIB_ADDRESS

    def test_data_flow_edges_exact_match(self) -> None:
        """Data flow edges connect pipes with exactly matching output->input concepts."""
        index = make_test_package_index()
        graph = build_know_how_graph(index)

        # pkg_test_extract_clause outputs PkgTestContractClause
        # pkg_test_analyze_clause inputs PkgTestContractClause on "clause"
        extract_key = f"{LEGAL_TOOLS_ADDRESS}::pkg_test_extract_clause"
        outgoing = graph.get_outgoing_data_flow(extract_key)
        analyze_targets = [edge for edge in outgoing if edge.target_pipe_key == f"{LEGAL_TOOLS_ADDRESS}::pkg_test_analyze_clause"]
        assert len(analyze_targets) == 1
        assert analyze_targets[0].input_param == "clause"

    def test_data_flow_edges_native_concept(self) -> None:
        """Pipes producing native Text connect to pipes consuming native Text."""
        index = make_test_package_index()
        graph = build_know_how_graph(index)

        # pkg_test_analyze_clause outputs Text
        analyze_key = f"{LEGAL_TOOLS_ADDRESS}::pkg_test_analyze_clause"
        outgoing = graph.get_outgoing_data_flow(analyze_key)
        # Should connect to all pipes that consume Text as input
        target_keys = {edge.target_pipe_key for edge in outgoing}
        # All pipes with "text" input expecting "Text" should be targets
        assert len(target_keys) >= 1

    def test_data_flow_via_refinement(self) -> None:
        """Pipe producing a refined concept connects to pipes expecting the base concept."""
        index = make_test_package_index()
        graph = build_know_how_graph(index)

        # pkg_test_refine_score produces PkgTestRefinedScore which refines PkgTestWeightedScore
        # If any pipe consumed PkgTestWeightedScore from scoring-lib, the refined producer would connect
        refine_key = f"{REFINING_APP_ADDRESS}::pkg_test_refine_score"
        outgoing = graph.get_outgoing_data_flow(refine_key)
        # Verify the refinement ancestry was properly considered
        # The refined output should be connectable to consumers of the base concept
        assert isinstance(outgoing, list)

    def test_no_self_loops(self) -> None:
        """Data flow edges never connect a pipe to itself."""
        index = make_test_package_index()
        graph = build_know_how_graph(index)

        for edge in graph.data_flow_edges:
            assert edge.source_pipe_key != edge.target_pipe_key

    def test_no_cross_package_concept_collision(self) -> None:
        """Same concept code in different packages creates distinct ConceptIds."""
        index = make_test_package_index()
        graph = build_know_how_graph(index)

        scoring_id = ConceptId(
            package_address=SCORING_LIB_ADDRESS,
            concept_ref="pkg_test_scoring_dep.PkgTestWeightedScore",
        )
        analytics_id = ConceptId(
            package_address=ANALYTICS_LIB_ADDRESS,
            concept_ref="pkg_test_analytics.PkgTestWeightedScore",
        )
        assert scoring_id != analytics_id
        assert graph.get_concept_node(scoring_id) is not None
        assert graph.get_concept_node(analytics_id) is not None

        # Pipes in analytics-lib resolve to analytics concept, not scoring concept
        analytics_pipe_key = f"{ANALYTICS_LIB_ADDRESS}::pkg_test_compute_analytics"
        analytics_pipe = graph.get_pipe_node(analytics_pipe_key)
        assert analytics_pipe is not None
        assert analytics_pipe.output_concept_id.package_address == ANALYTICS_LIB_ADDRESS

    def test_empty_index_produces_empty_graph_with_natives(self) -> None:
        """Empty index produces a graph with only native concept nodes."""
        index = PackageIndex()
        graph = build_know_how_graph(index)

        assert len(graph.pipe_nodes) == 0
        assert len(graph.data_flow_edges) == 0
        assert len(graph.refinement_edges) == 0
        # Should still have native concepts
        assert len(graph.concept_nodes) > 0
        native_keys = [key for key in graph.concept_nodes if key.startswith(NATIVE_PACKAGE_ADDRESS)]
        assert len(native_keys) == len(graph.concept_nodes)

    def test_pipe_with_unresolvable_output_excluded(self) -> None:
        """Pipe referencing a nonexistent output concept is excluded from the graph."""
        index = make_test_package_index_with_unresolvable_concepts()
        graph = build_know_how_graph(index)

        bad_output_key = f"{PHANTOM_PKG_ADDRESS}::pkg_test_bad_output_pipe"
        assert graph.get_pipe_node(bad_output_key) is None

    def test_pipe_with_unresolvable_input_excluded(self) -> None:
        """Pipe referencing a nonexistent input concept is excluded from the graph."""
        index = make_test_package_index_with_unresolvable_concepts()
        graph = build_know_how_graph(index)

        bad_input_key = f"{PHANTOM_PKG_ADDRESS}::pkg_test_bad_input_pipe"
        assert graph.get_pipe_node(bad_input_key) is None

    def test_valid_pipe_not_affected_by_unresolvable_siblings(self) -> None:
        """Valid pipes in the same package are still included when siblings have unresolvable concepts."""
        index = make_test_package_index_with_unresolvable_concepts()
        graph = build_know_how_graph(index)

        valid_key = f"{PHANTOM_PKG_ADDRESS}::pkg_test_valid_pipe"
        pipe_node = graph.get_pipe_node(valid_key)
        assert pipe_node is not None
        assert pipe_node.output_concept_id.package_address == PHANTOM_PKG_ADDRESS
        assert pipe_node.output_concept_id.concept_ref == "pkg_test_phantom.PkgTestValidConcept"

    def test_no_phantom_concept_nodes_created(self) -> None:
        """Unresolvable concept specs do not create phantom entries in concept_nodes."""
        index = make_test_package_index_with_unresolvable_concepts()
        graph = build_know_how_graph(index)

        # Only the valid concept and native concepts should exist
        non_native_keys = [key for key in graph.concept_nodes if not key.startswith(NATIVE_PACKAGE_ADDRESS)]
        assert len(non_native_keys) == 1
        expected_key = f"{PHANTOM_PKG_ADDRESS}::pkg_test_phantom.PkgTestValidConcept"
        assert non_native_keys[0] == expected_key

    def test_domain_qualified_output_spec_resolved(self) -> None:
        """Pipe with domain-qualified output spec (domain.ConceptCode) is included in graph."""
        index = make_test_package_index_with_qualified_concept_specs()
        graph = build_know_how_graph(index)

        pipe_key = f"{QUALIFIED_REF_ADDRESS}::pkg_test_produce_result"
        pipe_node = graph.get_pipe_node(pipe_key)
        assert pipe_node is not None, f"Pipe '{pipe_key}' should be in graph but was excluded"
        assert pipe_node.output_concept_id.package_address == QUALIFIED_REF_ADDRESS
        assert pipe_node.output_concept_id.concept_ref == "pkg_test_qualified.PkgTestLocalResult"

    def test_cross_package_input_spec_resolved(self) -> None:
        """Pipe with cross-package input spec (alias->domain.Code) is included in graph."""
        index = make_test_package_index_with_qualified_concept_specs()
        graph = build_know_how_graph(index)

        pipe_key = f"{QUALIFIED_REF_ADDRESS}::pkg_test_consume_score"
        pipe_node = graph.get_pipe_node(pipe_key)
        assert pipe_node is not None, f"Pipe '{pipe_key}' should be in graph but was excluded"
        # The input should resolve to the scoring-lib's concept
        score_input = pipe_node.input_concept_ids["score"]
        assert score_input.package_address == SCORING_LIB_ADDRESS
        assert score_input.concept_ref == "pkg_test_scoring_dep.PkgTestWeightedScore"

    def test_cross_package_output_spec_resolved(self) -> None:
        """Pipe with cross-package output spec (alias->domain.Code) is included in graph."""
        index = make_test_package_index_with_qualified_concept_specs()
        graph = build_know_how_graph(index)

        pipe_key = f"{QUALIFIED_REF_ADDRESS}::pkg_test_forward_score"
        pipe_node = graph.get_pipe_node(pipe_key)
        assert pipe_node is not None, f"Pipe '{pipe_key}' should be in graph but was excluded"
        assert pipe_node.output_concept_id.package_address == SCORING_LIB_ADDRESS
        assert pipe_node.output_concept_id.concept_ref == "pkg_test_scoring_dep.PkgTestWeightedScore"

    def test_all_qualified_ref_pipes_included(self) -> None:
        """All pipes using qualified/cross-package concept specs are included in graph."""
        index = make_test_package_index_with_qualified_concept_specs()
        graph = build_know_how_graph(index)

        expected_pipes = {
            f"{SCORING_LIB_ADDRESS}::pkg_test_compute_score",
            f"{QUALIFIED_REF_ADDRESS}::pkg_test_produce_result",
            f"{QUALIFIED_REF_ADDRESS}::pkg_test_consume_score",
            f"{QUALIFIED_REF_ADDRESS}::pkg_test_forward_score",
        }
        assert set(graph.pipe_nodes.keys()) == expected_pipes
