"""Unit tests for the shared graph rendering utility."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture

from pipelex.graph.graph_rendering import render_graph_from_spec
from pipelex.tools.misc.chart_utils import FlowchartDirection

GRAPH_RENDERING_MODULE = "pipelex.graph.graph_rendering"


@pytest.mark.asyncio(loop_scope="class")
class TestRenderGraphFromSpec:
    """Tests for the render_graph_from_spec utility function."""

    @pytest.mark.parametrize(
        ("include_mermaidflow", "include_reactflow"),
        [
            (True, False),
            (False, True),
            (True, True),
        ],
    )
    async def test_format_selection_sets_correct_inclusion(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
        include_mermaidflow: bool,
        include_reactflow: bool,
    ) -> None:
        """Each format combination should set the correct mermaidflow/reactflow inclusion flags."""
        mock_graph_spec = mocker.MagicMock()
        mock_graph_config = mocker.MagicMock()

        mocker.patch(
            f"{GRAPH_RENDERING_MODULE}.generate_graph_outputs",
            new_callable=mocker.AsyncMock,
            return_value=mocker.MagicMock(),
        )
        mocker.patch(
            f"{GRAPH_RENDERING_MODULE}.save_graph_outputs_to_dir",
            return_value={"reactflow_html": tmp_path / "graph.html"},
        )

        await render_graph_from_spec(
            graph_spec=mock_graph_spec,
            graph_config=mock_graph_config,
            include_mermaidflow=include_mermaidflow,
            include_reactflow=include_reactflow,
            pipe_code="test_pipe",
            output_dir=tmp_path,
        )

        # Verify the config was built with correct inclusion via model_copy chain
        mock_graph_config.model_copy.assert_called_once()
        graphs_inclusion_update = mock_graph_config.graphs_inclusion.model_copy.call_args.kwargs["update"]
        assert graphs_inclusion_update["mermaidflow_html"] is include_mermaidflow
        assert graphs_inclusion_update["reactflow_html"] is include_reactflow

    async def test_returns_saved_files(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """Should return the dict from save_graph_outputs_to_dir."""
        mock_graph_spec = mocker.MagicMock()
        mock_graph_config = mocker.MagicMock()

        mocker.patch(
            f"{GRAPH_RENDERING_MODULE}.generate_graph_outputs",
            new_callable=mocker.AsyncMock,
            return_value=mocker.MagicMock(),
        )

        expected_result = {"reactflow_html": tmp_path / "reactflow.html"}
        mocker.patch(
            f"{GRAPH_RENDERING_MODULE}.save_graph_outputs_to_dir",
            return_value=expected_result,
        )

        result = await render_graph_from_spec(
            graph_spec=mock_graph_spec,
            graph_config=mock_graph_config,
            include_mermaidflow=False,
            include_reactflow=True,
            pipe_code="test_pipe",
            output_dir=tmp_path,
        )

        assert result == expected_result

    async def test_passes_pipe_code_to_generate(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """Should pass pipe_code through to generate_graph_outputs."""
        mock_graph_spec = mocker.MagicMock()
        mock_graph_config = mocker.MagicMock()

        mock_generate = mocker.patch(
            f"{GRAPH_RENDERING_MODULE}.generate_graph_outputs",
            new_callable=mocker.AsyncMock,
            return_value=mocker.MagicMock(),
        )
        mocker.patch(
            f"{GRAPH_RENDERING_MODULE}.save_graph_outputs_to_dir",
            return_value={},
        )

        await render_graph_from_spec(
            graph_spec=mock_graph_spec,
            graph_config=mock_graph_config,
            include_mermaidflow=False,
            include_reactflow=True,
            pipe_code="my_pipeline",
            output_dir=tmp_path,
        )

        assert mock_generate.call_args.kwargs["pipe_code"] == "my_pipeline"

    async def test_saves_to_correct_output_dir(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """Should pass output_dir to save_graph_outputs_to_dir."""
        mock_graph_spec = mocker.MagicMock()
        mock_graph_config = mocker.MagicMock()

        mocker.patch(
            f"{GRAPH_RENDERING_MODULE}.generate_graph_outputs",
            new_callable=mocker.AsyncMock,
            return_value=mocker.MagicMock(),
        )
        mock_save = mocker.patch(
            f"{GRAPH_RENDERING_MODULE}.save_graph_outputs_to_dir",
            return_value={},
        )

        await render_graph_from_spec(
            graph_spec=mock_graph_spec,
            graph_config=mock_graph_config,
            include_mermaidflow=True,
            include_reactflow=True,
            pipe_code="test_pipe",
            output_dir=tmp_path,
        )

        assert mock_save.call_args.kwargs["output_dir"] == tmp_path

    async def test_passes_optional_params_to_generate(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """Should forward title, direction, and include_subgraphs to generate_graph_outputs."""
        mock_graph_spec = mocker.MagicMock()
        mock_graph_config = mocker.MagicMock()

        mock_generate = mocker.patch(
            f"{GRAPH_RENDERING_MODULE}.generate_graph_outputs",
            new_callable=mocker.AsyncMock,
            return_value=mocker.MagicMock(),
        )
        mocker.patch(
            f"{GRAPH_RENDERING_MODULE}.save_graph_outputs_to_dir",
            return_value={},
        )

        await render_graph_from_spec(
            graph_spec=mock_graph_spec,
            graph_config=mock_graph_config,
            include_mermaidflow=True,
            include_reactflow=False,
            output_dir=tmp_path,
            title="My Title",
            direction=FlowchartDirection.TOP_DOWN,
            include_subgraphs=False,
        )

        call_kwargs = mock_generate.call_args.kwargs
        assert call_kwargs["title"] == "My Title"
        assert call_kwargs["direction"] == FlowchartDirection.TOP_DOWN
        assert call_kwargs["include_subgraphs"] is False
