import re
from datetime import datetime, timezone
from typing import Any, ClassVar

import pytest

from pipelex.graph.graphspec import (
    EdgeKind,
    EdgeSpec,
    GraphSpec,
    IOSpec,
    NodeIOSpec,
    NodeKind,
    NodeSpec,
    NodeStatus,
    PipelineRef,
)
from pipelex.graph.mermaidflow.mermaidflow_factory import MermaidflowFactory

from .conftest import make_graph_config


class TestDashedEdgeRendering:
    """Tests for dashed-edge rendering logic across BATCH_ITEM, BATCH_AGGREGATE, and PARALLEL_COMBINE edge kinds."""

    GRAPH_ID: ClassVar[str] = "dashed_edge_test:001"
    CREATED_AT: ClassVar[datetime] = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)

    def _make_graph(
        self,
        nodes: list[dict[str, Any]],
        edges: list[dict[str, Any]] | None = None,
    ) -> GraphSpec:
        """Helper to create a GraphSpec with nodes and edges."""
        node_specs: list[NodeSpec] = []
        for node_dict in nodes:
            node_specs.append(NodeSpec(**node_dict))

        edge_specs: list[EdgeSpec] = []
        if edges:
            for edge_dict in edges:
                edge_specs.append(EdgeSpec(**edge_dict))

        return GraphSpec(
            graph_id=self.GRAPH_ID,
            created_at=self.CREATED_AT,
            pipeline_ref=PipelineRef(),
            nodes=node_specs,
            edges=edge_specs,
        )

    def _extract_dashed_edges(self, mermaid_code: str) -> list[str]:
        """Extract all dashed-edge lines from mermaid code.

        Returns:
            Lines containing dashed arrows (-.-> or -."label".->).
        """
        return [line.strip() for line in mermaid_code.split("\n") if ".->" in line]

    def _build_controller_graph_with_dashed_edge(
        self,
        edge_kind: EdgeKind,
        edge_label: str | None = None,
    ) -> GraphSpec:
        """Build a graph with a controller, two children, and a dashed edge between their stuffs.

        The controller contains two child pipes. The dashed edge connects
        source_stuff from child_a to target_stuff owned by the controller (for aggregate/combine)
        or child_b (for batch_item).

        Args:
            edge_kind: The kind of dashed edge to create.
            edge_label: Optional label for the dashed edge.

        Returns:
            A GraphSpec with the dashed-edge scenario.
        """
        controller = {
            "node_id": "ctrl_1",
            "kind": NodeKind.CONTROLLER,
            "pipe_code": "batch_ctrl",
            "status": NodeStatus.SUCCEEDED,
            "node_io": NodeIOSpec(
                inputs=[],
                outputs=[IOSpec(name="ctrl_output", concept="OutputList", digest="ctrl_out_digest")],
            ),
        }
        child_a = {
            "node_id": "child_a",
            "kind": NodeKind.OPERATOR,
            "pipe_code": "pipe_a",
            "status": NodeStatus.SUCCEEDED,
            "node_io": NodeIOSpec(
                inputs=[],
                outputs=[IOSpec(name="source_stuff", concept="Text", digest="source_digest")],
            ),
        }
        child_b = {
            "node_id": "child_b",
            "kind": NodeKind.OPERATOR,
            "pipe_code": "pipe_b",
            "status": NodeStatus.SUCCEEDED,
            "node_io": NodeIOSpec(
                inputs=[IOSpec(name="target_stuff", concept="Text", digest="target_digest")],
                outputs=[],
            ),
        }
        contains_a = {
            "edge_id": "edge_contains_a",
            "source": "ctrl_1",
            "target": "child_a",
            "kind": EdgeKind.CONTAINS,
        }
        contains_b = {
            "edge_id": "edge_contains_b",
            "source": "ctrl_1",
            "target": "child_b",
            "kind": EdgeKind.CONTAINS,
        }

        # For BATCH_AGGREGATE and PARALLEL_COMBINE, target is the controller's output stuff
        # For BATCH_ITEM, target is child_b's input stuff
        target_stuff_digest: str
        match edge_kind:
            case EdgeKind.BATCH_ITEM:
                target_stuff_digest = "target_digest"
            case EdgeKind.BATCH_AGGREGATE | EdgeKind.PARALLEL_COMBINE:
                target_stuff_digest = "ctrl_out_digest"
            case EdgeKind.CONTROL | EdgeKind.DATA | EdgeKind.CONTAINS | EdgeKind.SELECTED_OUTCOME:
                msg = f"Unexpected edge kind for dashed edge test: {edge_kind}"
                raise ValueError(msg)

        dashed_edge: dict[str, Any] = {
            "edge_id": "edge_dashed",
            "source": "child_a",
            "target": "ctrl_1",
            "kind": edge_kind,
            "source_stuff_digest": "source_digest",
            "target_stuff_digest": target_stuff_digest,
        }
        if edge_label:
            dashed_edge["label"] = edge_label

        return self._make_graph(
            nodes=[controller, child_a, child_b],
            edges=[contains_a, contains_b, dashed_edge],
        )

    @pytest.mark.parametrize(
        ("topic", "edge_kind"),
        [
            ("BATCH_ITEM", EdgeKind.BATCH_ITEM),
            ("BATCH_AGGREGATE", EdgeKind.BATCH_AGGREGATE),
            ("PARALLEL_COMBINE", EdgeKind.PARALLEL_COMBINE),
        ],
    )
    def test_dashed_edge_rendered_for_each_kind(self, topic: str, edge_kind: EdgeKind) -> None:
        """Verify that each dashed-edge kind produces at least one dashed arrow."""
        graph = self._build_controller_graph_with_dashed_edge(edge_kind=edge_kind)
        graph_config = make_graph_config()
        result = MermaidflowFactory.make_from_graphspec(graph, graph_config)

        dashed_lines = self._extract_dashed_edges(result.mermaid_code)
        assert len(dashed_lines) >= 1, f"Expected at least one dashed edge for {topic}, got none"

    @pytest.mark.parametrize(
        ("topic", "edge_kind"),
        [
            ("BATCH_ITEM", EdgeKind.BATCH_ITEM),
            ("BATCH_AGGREGATE", EdgeKind.BATCH_AGGREGATE),
            ("PARALLEL_COMBINE", EdgeKind.PARALLEL_COMBINE),
        ],
    )
    def test_dashed_edge_with_label(self, topic: str, edge_kind: EdgeKind) -> None:
        """Verify that labeled dashed edges include the label in the mermaid syntax."""
        graph = self._build_controller_graph_with_dashed_edge(edge_kind=edge_kind, edge_label="my_label")
        graph_config = make_graph_config()
        result = MermaidflowFactory.make_from_graphspec(graph, graph_config)

        dashed_lines = self._extract_dashed_edges(result.mermaid_code)
        labeled = [line for line in dashed_lines if "my_label" in line]
        assert len(labeled) >= 1, f"Expected a labeled dashed edge for {topic}, got: {dashed_lines}"

    @pytest.mark.parametrize(
        ("topic", "edge_kind"),
        [
            ("BATCH_ITEM", EdgeKind.BATCH_ITEM),
            ("BATCH_AGGREGATE", EdgeKind.BATCH_AGGREGATE),
            ("PARALLEL_COMBINE", EdgeKind.PARALLEL_COMBINE),
        ],
    )
    def test_dashed_edge_without_label(self, topic: str, edge_kind: EdgeKind) -> None:
        """Verify that unlabeled dashed edges use plain dashed arrow syntax."""
        graph = self._build_controller_graph_with_dashed_edge(edge_kind=edge_kind)
        graph_config = make_graph_config()
        result = MermaidflowFactory.make_from_graphspec(graph, graph_config)

        dashed_lines = self._extract_dashed_edges(result.mermaid_code)
        # Unlabeled edges use `-.->` without a label string
        plain_dashed = [line for line in dashed_lines if ".->" in line and '-."' not in line]
        assert len(plain_dashed) >= 1, f"Expected a plain dashed edge for {topic}, got: {dashed_lines}"

    def test_all_edge_kinds_use_same_dashed_syntax(self) -> None:
        """Verify that all three dashed-edge kinds produce structurally identical dashed arrow syntax.

        This test catches divergence if one copy of the logic is modified but not the others.
        """
        results_by_kind: dict[str, list[str]] = {}
        for edge_kind in (EdgeKind.BATCH_ITEM, EdgeKind.BATCH_AGGREGATE, EdgeKind.PARALLEL_COMBINE):
            graph = self._build_controller_graph_with_dashed_edge(edge_kind=edge_kind, edge_label="test_label")
            graph_config = make_graph_config()
            result = MermaidflowFactory.make_from_graphspec(graph, graph_config)

            dashed_lines = self._extract_dashed_edges(result.mermaid_code)
            # Extract just the arrow operator from each line (e.g., `-."test_label".->` or `-.->`)
            # by replacing stuff IDs (s_XXX) with a placeholder
            normalized = [re.sub(r"s_[a-f0-9]+", "ID", line) for line in dashed_lines]
            results_by_kind[edge_kind] = normalized

        # All three should produce the same normalized patterns
        kinds = list(results_by_kind.keys())
        for index_kind in range(1, len(kinds)):
            assert results_by_kind[kinds[0]] == results_by_kind[kinds[index_kind]], (
                f"Dashed edge syntax differs between {kinds[0]} and {kinds[index_kind]}: "
                f"{results_by_kind[kinds[0]]} vs {results_by_kind[kinds[index_kind]]}"
            )

    def test_missing_stuff_resolved_on_the_fly(self) -> None:
        """Verify that stuff nodes not in the normal stuff_registry get rendered on-the-fly for dashed edges.

        Creates a scenario where the target stuff only exists on the controller's output
        (not registered through normal pipe IOSpec), so it must be resolved from all_stuff_info.
        """
        controller = {
            "node_id": "ctrl_1",
            "kind": NodeKind.CONTROLLER,
            "pipe_code": "batch_ctrl",
            "status": NodeStatus.SUCCEEDED,
            "node_io": NodeIOSpec(
                inputs=[],
                outputs=[IOSpec(name="aggregated_output", concept="OutputList", digest="agg_digest")],
            ),
        }
        child = {
            "node_id": "child_1",
            "kind": NodeKind.OPERATOR,
            "pipe_code": "child_pipe",
            "status": NodeStatus.SUCCEEDED,
            "node_io": NodeIOSpec(
                inputs=[],
                outputs=[IOSpec(name="item_output", concept="Text", digest="item_digest")],
            ),
        }
        contains = {
            "edge_id": "edge_contains",
            "source": "ctrl_1",
            "target": "child_1",
            "kind": EdgeKind.CONTAINS,
        }
        aggregate_edge = {
            "edge_id": "edge_agg",
            "source": "child_1",
            "target": "ctrl_1",
            "kind": EdgeKind.BATCH_AGGREGATE,
            "source_stuff_digest": "item_digest",
            "target_stuff_digest": "agg_digest",
        }
        graph = self._make_graph(
            nodes=[controller, child],
            edges=[contains, aggregate_edge],
        )
        graph_config = make_graph_config()
        result = MermaidflowFactory.make_from_graphspec(graph, graph_config)

        # The aggregated_output stuff should be rendered (resolved on the fly)
        assert "aggregated_output" in result.mermaid_code
        # And there should be a dashed edge connecting them
        dashed_lines = self._extract_dashed_edges(result.mermaid_code)
        assert len(dashed_lines) >= 1, "Expected a dashed edge for aggregate, got none"
