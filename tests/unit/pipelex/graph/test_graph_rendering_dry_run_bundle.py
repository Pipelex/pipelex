"""Unit tests for the bundle dry-run helper in graph rendering."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from pipelex.graph.graph_rendering import (
    _dry_run_bundle,  # noqa: PLC2701 # pyright: ignore[reportPrivateUsage]
)

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture

GRAPH_RENDERING_MODULE = "pipelex.graph.graph_rendering"

BUNDLE_CONTENT = 'domain = "test_domain"\nmain_pipe = "test_pipe"\n'


@pytest.mark.asyncio(loop_scope="class")
class TestDryRunBundle:
    """Tests for _dry_run_bundle library-dirs handling and dry_run_pipeline delegation."""

    async def test_library_dirs_none_uses_bundle_parent(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """With no library_dirs, the resolved bundle parent dir should be the only library dir."""
        bundle_path = tmp_path / "bundle.mthds"
        bundle_path.write_text(BUNDLE_CONTENT, encoding="utf-8")

        graph_spec_mock = mocker.MagicMock()
        mock_dry_run = mocker.patch(
            f"{GRAPH_RENDERING_MODULE}.dry_run_pipeline",
            new_callable=mocker.AsyncMock,
            return_value=(graph_spec_mock, "pipe_code"),
        )

        result = await _dry_run_bundle(bundle_path, library_dirs=None)

        assert result == (graph_spec_mock, "pipe_code")
        call_kwargs = mock_dry_run.call_args.kwargs
        assert call_kwargs["mthds_contents"] == [BUNDLE_CONTENT]
        assert call_kwargs["bundle_uris"] == [str(bundle_path)]
        assert call_kwargs["library_dirs"] == [str(tmp_path.resolve())]

    async def test_library_dirs_missing_parent_gets_parent_appended(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """When the bundle parent is missing from library_dirs, it is appended without mutating the original list."""
        bundle_path = tmp_path / "bundle.mthds"
        bundle_path.write_text(BUNDLE_CONTENT, encoding="utf-8")

        mock_dry_run = mocker.patch(
            f"{GRAPH_RENDERING_MODULE}.dry_run_pipeline",
            new_callable=mocker.AsyncMock,
            return_value=(mocker.MagicMock(), "pipe_code"),
        )

        provided_dirs = ["/somewhere/else"]
        await _dry_run_bundle(bundle_path, library_dirs=provided_dirs)

        call_kwargs = mock_dry_run.call_args.kwargs
        assert call_kwargs["library_dirs"] == ["/somewhere/else", str(tmp_path.resolve())]
        assert provided_dirs == ["/somewhere/else"]

    async def test_library_dirs_already_containing_parent_passed_through(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """When the resolved bundle parent is already present, library_dirs pass through unchanged."""
        bundle_path = tmp_path / "bundle.mthds"
        bundle_path.write_text(BUNDLE_CONTENT, encoding="utf-8")

        mock_dry_run = mocker.patch(
            f"{GRAPH_RENDERING_MODULE}.dry_run_pipeline",
            new_callable=mocker.AsyncMock,
            return_value=(mocker.MagicMock(), "pipe_code"),
        )

        provided_dirs = ["/somewhere/else", str(tmp_path.resolve())]
        await _dry_run_bundle(bundle_path, library_dirs=provided_dirs)

        call_kwargs = mock_dry_run.call_args.kwargs
        assert call_kwargs["library_dirs"] == provided_dirs
