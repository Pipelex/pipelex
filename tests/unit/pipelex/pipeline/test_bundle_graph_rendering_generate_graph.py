"""Unit tests for bundle-level graph generation dispatch."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from pipelex.graph.graph_rendering import GraphFormat
from pipelex.pipeline.bundle_graph_rendering import generate_graph_for_bundle
from pipelex.tools.misc.chart_utils import FlowchartDirection

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture

BUNDLE_GRAPH_RENDERING_MODULE = "pipelex.pipeline.bundle_graph_rendering"

BUNDLE_CONTENT = 'domain = "test_domain"\nmain_pipe = "test_pipe"\n'


@pytest.mark.asyncio(loop_scope="class")
class TestGenerateGraphForBundle:
    """Tests for generate_graph_for_bundle format dispatch, rename branch, and return shape."""

    def _setup_mocks(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
        saved_files: dict[str, Path],
    ) -> dict[str, Any]:
        """Create the bundle file and patch the bundle_graph_rendering collaborators.

        The renderer is patched as a whole: since the split, `render_graph_from_spec` lives in the
        kernel-layer `pipelex.graph.graph_rendering` and is this module's collaborator, not its
        internals. How it maps the inclusion flags onto the graph config is its own test's business
        (`tests/unit/pipelex/graph/test_graph_rendering.py`); what belongs here is the dispatch.
        """
        bundle_path = tmp_path / "bundle.mthds"
        bundle_path.write_text(BUNDLE_CONTENT, encoding="utf-8")

        graph_spec_mock = mocker.MagicMock()
        mock_dry_run = mocker.patch(
            f"{BUNDLE_GRAPH_RENDERING_MODULE}.dry_run_pipeline",
            new_callable=mocker.AsyncMock,
            return_value=(graph_spec_mock, "pipe_code"),
        )

        execution_config_mock = mocker.MagicMock()
        config_mock = mocker.MagicMock()
        config_mock.pipelex.pipeline_execution_config.with_execution_overrides.return_value = execution_config_mock
        mocker.patch(f"{BUNDLE_GRAPH_RENDERING_MODULE}.get_config", return_value=config_mock)

        mock_render = mocker.patch(
            f"{BUNDLE_GRAPH_RENDERING_MODULE}.render_graph_from_spec",
            new_callable=mocker.AsyncMock,
            return_value=saved_files,
        )

        return {
            "bundle_path": bundle_path,
            "graph_spec_mock": graph_spec_mock,
            "mock_dry_run": mock_dry_run,
            "config_mock": config_mock,
            "execution_config_mock": execution_config_mock,
            "mock_render": mock_render,
        }

    @pytest.mark.parametrize(
        ("graph_format", "expected_mermaidflow", "expected_reactflow"),
        [
            (GraphFormat.MERMAIDFLOW, True, False),
            (GraphFormat.REACTFLOW, False, True),
            (GraphFormat.BOTH, True, True),
        ],
    )
    async def test_format_dispatch_sets_inclusion_flags(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
        graph_format: GraphFormat,
        expected_mermaidflow: bool,
        expected_reactflow: bool,
    ) -> None:
        """Each graph format should map to the matching mermaidflow/reactflow inclusion flags."""
        mocks = self._setup_mocks(mocker, tmp_path, saved_files={})

        await generate_graph_for_bundle(
            bundle_path=mocks["bundle_path"],
            graph_format=graph_format,
        )

        render_kwargs = mocks["mock_render"].call_args.kwargs
        assert render_kwargs["include_mermaidflow"] is expected_mermaidflow
        assert render_kwargs["include_reactflow"] is expected_reactflow
        assert render_kwargs["graph_config"] is mocks["execution_config_mock"].graph_config
        overrides_kwargs = mocks["config_mock"].pipelex.pipeline_execution_config.with_execution_overrides.call_args.kwargs
        assert overrides_kwargs == {"generate_graph": True, "mock_inputs": True}

    async def test_rename_branch_sanitizes_traversal_name(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """A traversal-laden graph_name should be renamed to a safe filename in the same dir."""
        original_path = tmp_path / "reactflow.html"
        original_path.write_text("<html></html>", encoding="utf-8")
        mocks = self._setup_mocks(mocker, tmp_path, saved_files={"reactflow_html": original_path})

        result = await generate_graph_for_bundle(
            bundle_path=mocks["bundle_path"],
            graph_format=GraphFormat.REACTFLOW,
            graph_name="../../evil.html",
        )

        renamed_path = tmp_path / "evil.html"
        assert renamed_path.is_file()
        assert not original_path.exists()
        assert result["graph_files"] == {"reactflow_html": str(renamed_path)}

    async def test_no_reactflow_key_skips_rename(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """Without a reactflow_html entry, saved files pass through as strings with no rename."""
        mermaid_path = tmp_path / "mermaid.html"
        mermaid_path.write_text("<html></html>", encoding="utf-8")
        mocks = self._setup_mocks(mocker, tmp_path, saved_files={"mermaidflow_html": mermaid_path})

        result = await generate_graph_for_bundle(
            bundle_path=mocks["bundle_path"],
            graph_format=GraphFormat.MERMAIDFLOW,
            graph_name="renamed.html",
        )

        assert mermaid_path.is_file()
        assert not (tmp_path / "renamed.html").exists()
        assert result["graph_files"] == {"mermaidflow_html": str(mermaid_path)}

    @pytest.mark.parametrize(
        ("direction", "expected_direction"),
        [
            (None, None),
            (FlowchartDirection.LEFT_TO_RIGHT, str(FlowchartDirection.LEFT_TO_RIGHT)),
        ],
    )
    async def test_return_shape(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
        direction: FlowchartDirection | None,
        expected_direction: str | None,
    ) -> None:
        """The result should carry the bundle parent dir, dry-run pipe_code, and stringified direction."""
        mocks = self._setup_mocks(mocker, tmp_path, saved_files={})

        result = await generate_graph_for_bundle(
            bundle_path=mocks["bundle_path"],
            graph_format=GraphFormat.BOTH,
            direction=direction,
        )

        assert result["graph_output_dir"] == str(tmp_path)
        assert result["pipe_code"] == "pipe_code"
        assert result["direction"] == expected_direction

    async def test_pipe_code_override_passed_to_dry_run(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """An explicit graph target should be passed to the pipeline dry-run helper."""
        mocks = self._setup_mocks(mocker, tmp_path, saved_files={})

        await generate_graph_for_bundle(
            bundle_path=mocks["bundle_path"],
            graph_format=GraphFormat.REACTFLOW,
            pipe_code="other_pipe",
        )

        mocks["mock_dry_run"].assert_awaited_once()
        assert mocks["mock_dry_run"].call_args.kwargs["pipe_code"] == "other_pipe"
