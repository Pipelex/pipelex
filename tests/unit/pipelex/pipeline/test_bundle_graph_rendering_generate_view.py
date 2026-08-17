"""Unit tests for bundle-level graph view (GraphSpec JSON) generation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from pipelex.pipeline.bundle_graph_rendering import generate_view_for_bundle
from pipelex.tools.misc.chart_utils import FlowchartDirection

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture

BUNDLE_GRAPH_RENDERING_MODULE = "pipelex.pipeline.bundle_graph_rendering"

BUNDLE_CONTENT = 'domain = "test_domain"\nmain_pipe = "test_pipe"\n'


@pytest.mark.asyncio(loop_scope="class")
class TestGenerateViewForBundle:
    """Tests for generate_view_for_bundle graphspec payload and direction precedence."""

    def _setup_mocks(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
        config_layout_direction: FlowchartDirection | None,
    ) -> tuple[Path, Any, Any]:
        """Create the bundle file, patch collaborators, and return the bundle path and graph spec mock."""
        bundle_path = tmp_path / "bundle.mthds"
        bundle_path.write_text(BUNDLE_CONTENT, encoding="utf-8")

        graph_spec_mock = mocker.MagicMock()
        graph_spec_mock.model_dump.return_value = {"nodes": "node_payload", "edges": "edge_payload"}
        dry_run_mock = mocker.patch(
            f"{BUNDLE_GRAPH_RENDERING_MODULE}.dry_run_pipeline",
            new_callable=mocker.AsyncMock,
            return_value=(graph_spec_mock, "pipe_code"),
        )

        execution_config_mock = mocker.MagicMock()
        execution_config_mock.graph.reactflow.layout_direction = config_layout_direction
        config_mock = mocker.MagicMock()
        config_mock.interpreter.pipeline_execution.with_execution_overrides.return_value = execution_config_mock
        mocker.patch(f"{BUNDLE_GRAPH_RENDERING_MODULE}.get_config", return_value=config_mock)

        return bundle_path, graph_spec_mock, dry_run_mock

    async def test_returns_graphspec_json_dump(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """The graphspec key should carry the by-alias JSON model dump of the dry-run GraphSpec."""
        bundle_path, graph_spec_mock, _dry_run_mock = self._setup_mocks(mocker, tmp_path, config_layout_direction=None)

        result = await generate_view_for_bundle(bundle_path=bundle_path)

        assert result["graphspec"] == {"nodes": "node_payload", "edges": "edge_payload"}
        assert result["pipe_code"] == "pipe_code"
        graph_spec_mock.model_dump.assert_called_once_with(mode="json", by_alias=True)

    @pytest.mark.parametrize(
        ("direction_arg", "config_layout_direction", "expected_direction"),
        [
            (FlowchartDirection.TOP_DOWN, FlowchartDirection.LEFT_TO_RIGHT, str(FlowchartDirection.TOP_DOWN)),
            (None, FlowchartDirection.LEFT_TO_RIGHT, str(FlowchartDirection.LEFT_TO_RIGHT)),
            (None, None, None),
        ],
    )
    async def test_direction_precedence(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
        direction_arg: FlowchartDirection | None,
        config_layout_direction: FlowchartDirection | None,
        expected_direction: str | None,
    ) -> None:
        """An explicit direction wins, else the reactflow config layout direction, else None."""
        bundle_path, _graph_spec_mock, _dry_run_mock = self._setup_mocks(mocker, tmp_path, config_layout_direction=config_layout_direction)

        result = await generate_view_for_bundle(bundle_path=bundle_path, direction=direction_arg)

        assert result["direction"] == expected_direction

    async def test_pipe_code_override_passed_to_dry_run(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """An explicit graph target should be passed to the pipeline dry-run helper."""
        bundle_path, _graph_spec_mock, dry_run_mock = self._setup_mocks(mocker, tmp_path, config_layout_direction=None)

        await generate_view_for_bundle(bundle_path=bundle_path, pipe_code="other_pipe")

        dry_run_mock.assert_awaited_once()
        assert dry_run_mock.call_args.kwargs["pipe_code"] == "other_pipe"
