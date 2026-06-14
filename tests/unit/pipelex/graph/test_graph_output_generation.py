"""Tests for graph output generation from an assembled GraphSpec.

Validates that generate_graph_outputs and save_graph_outputs_to_dir produce
the expected output files (GraphSpec JSON, Mermaid MMD, Mermaid HTML, ReactFlow HTML).
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from pipelex.graph.graph_config import GraphConfig, GraphsInclusionConfig
from pipelex.graph.graph_factory import generate_graph_outputs, save_graph_outputs_to_dir
from pipelex.graph.graphspec import EdgeKind, EdgeSpec, GraphSpec, IOSpec, NodeIOSpec, NodeKind, NodeSpec, NodeStatus, PipelineRef, TimingSpec
from tests.unit.pipelex.graph.conftest import make_graph_config

_T0 = datetime(2025, 7, 1, 12, 0, 0, tzinfo=timezone.utc)


def _make_sequence_graphspec() -> GraphSpec:
    """Build a minimal sequence GraphSpec: parent + 2 children with CONTAINS and DATA edges."""
    parent_id = "node_seq"
    child_1_id = "node_step_one"
    child_2_id = "node_step_two"

    nodes = [
        NodeSpec(
            node_id=parent_id,
            kind=NodeKind.CONTROLLER,
            pipe_code="my_sequence",
            pipe_type="PipeSequence",
            status=NodeStatus.SUCCEEDED,
            timing=TimingSpec(started_at=_T0, ended_at=_T0 + timedelta(seconds=10)),
        ),
        NodeSpec(
            node_id=child_1_id,
            kind=NodeKind.OPERATOR,
            pipe_code="step_one",
            pipe_type="PipeLLM",
            status=NodeStatus.SUCCEEDED,
            timing=TimingSpec(started_at=_T0 + timedelta(seconds=1), ended_at=_T0 + timedelta(seconds=4)),
            node_io=NodeIOSpec(
                outputs=[IOSpec(name="output_text", digest="digest_a")],
            ),
        ),
        NodeSpec(
            node_id=child_2_id,
            kind=NodeKind.OPERATOR,
            pipe_code="step_two",
            pipe_type="PipeLLM",
            status=NodeStatus.SUCCEEDED,
            timing=TimingSpec(started_at=_T0 + timedelta(seconds=5), ended_at=_T0 + timedelta(seconds=9)),
            node_io=NodeIOSpec(
                inputs=[IOSpec(name="input_text", digest="digest_a")],
                outputs=[IOSpec(name="output_text", digest="digest_b")],
            ),
        ),
    ]
    edges = [
        EdgeSpec(
            edge_id="edge_0",
            source=parent_id,
            target=child_1_id,
            kind=EdgeKind.CONTAINS,
        ),
        EdgeSpec(
            edge_id="edge_1",
            source=parent_id,
            target=child_2_id,
            kind=EdgeKind.CONTAINS,
        ),
        EdgeSpec(
            edge_id="edge_2",
            source=child_1_id,
            target=child_2_id,
            kind=EdgeKind.DATA,
            label="input_text",
        ),
    ]
    return GraphSpec(
        graph_id="output_test_graph",
        created_at=_T0,
        pipeline_ref=PipelineRef(domain="test_domain", main_pipe="my_sequence"),
        nodes=nodes,
        edges=edges,
    )


def _enable_all_outputs(graph_config: GraphConfig) -> GraphConfig:
    """Return a copy of the config with all graph output types enabled."""
    return graph_config.model_copy(
        update={
            "graphs_inclusion": GraphsInclusionConfig(
                graphspec_json=True,
                mermaidflow_mmd=True,
                mermaidflow_html=True,
                reactflow_html=True,
            ),
        },
    )


@pytest.mark.asyncio(loop_scope="class")
class TestGraphOutputGeneration:
    """Verify that graph output generation produces valid content and files."""

    async def test_generate_all_outputs(self) -> None:
        """All four output types are generated when enabled."""
        graph_spec = _make_sequence_graphspec()
        config = _enable_all_outputs(make_graph_config())

        outputs = await generate_graph_outputs(graph_spec, graph_config=config, pipe_code="my_sequence")

        assert outputs.graphspec_json is not None
        assert "output_test_graph" in outputs.graphspec_json
        assert "my_sequence" in outputs.graphspec_json

        assert outputs.mermaidflow_mmd is not None
        assert len(outputs.mermaidflow_mmd) > 0

        assert outputs.mermaidflow_html is not None
        assert "<!DOCTYPE html>" in outputs.mermaidflow_html or "<html" in outputs.mermaidflow_html

        assert outputs.reactflow_html is not None
        assert "<!DOCTYPE html>" in outputs.reactflow_html

    async def test_save_outputs_to_dir(self, tmp_path: Path) -> None:
        """save_graph_outputs_to_dir writes all output files to disk."""
        graph_spec = _make_sequence_graphspec()
        config = _enable_all_outputs(make_graph_config())

        outputs = await generate_graph_outputs(graph_spec, graph_config=config, pipe_code="my_sequence")
        output_dir = tmp_path / "graph_output"
        saved_files = save_graph_outputs_to_dir(outputs, output_dir=output_dir)

        assert output_dir.is_dir()
        assert "graphspec_json" in saved_files
        assert "mermaidflow_mmd" in saved_files
        assert "mermaidflow_html" in saved_files
        assert "reactflow_html" in saved_files

        assert (output_dir / "graphspec.json").is_file()
        assert (output_dir / "mermaidflow.mmd").is_file()
        assert (output_dir / "mermaidflow.html").is_file()
        assert (output_dir / "reactflow.html").is_file()

        # Verify saved content is non-empty
        for file_path in saved_files.values():
            assert file_path.stat().st_size > 0

    async def test_graphspec_json_only(self) -> None:
        """Only GraphSpec JSON is generated when other outputs are disabled."""
        graph_spec = _make_sequence_graphspec()
        config = make_graph_config()
        config = config.model_copy(
            update={
                "graphs_inclusion": GraphsInclusionConfig(
                    graphspec_json=True,
                    mermaidflow_mmd=False,
                    mermaidflow_html=False,
                    reactflow_html=False,
                ),
            },
        )

        outputs = await generate_graph_outputs(graph_spec, graph_config=config, pipe_code="my_sequence")

        assert outputs.graphspec_json is not None
        assert outputs.mermaidflow_mmd is None
        assert outputs.mermaidflow_html is None
        assert outputs.reactflow_html is None

    async def test_mermaid_mmd_contains_node_labels(self) -> None:
        """Mermaid MMD output references the pipe codes from the graph."""
        graph_spec = _make_sequence_graphspec()
        config = make_graph_config()
        config = config.model_copy(
            update={
                "graphs_inclusion": GraphsInclusionConfig(
                    graphspec_json=False,
                    mermaidflow_mmd=True,
                    mermaidflow_html=False,
                    reactflow_html=False,
                ),
            },
        )

        outputs = await generate_graph_outputs(graph_spec, graph_config=config, pipe_code="my_sequence")

        assert outputs.mermaidflow_mmd is not None
        assert "step_one" in outputs.mermaidflow_mmd
        assert "step_two" in outputs.mermaidflow_mmd
