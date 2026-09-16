"""`pipelex graph render` on a spec this version refuses: the diagnosis names the file exactly as the user wrote it.

Boot, teardown and telemetry are mocked out so no real Pipelex is made; the console is swapped for one
writing to a buffer so the printed diagnosis can be read back.
"""

from __future__ import annotations

import contextlib
import io
from typing import TYPE_CHECKING

import pytest
import typer
from rich.console import Console

from pipelex.cli.commands.graph_cmd import graph_render_cmd

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture

GRAPH_CMD = "pipelex.cli.commands.graph_cmd"


class TestGraphRenderRefusedSpec:
    @pytest.mark.parametrize("bracketed_dir", ["[draft]", "[/old]"])
    def test_a_bracketed_path_prints_as_written(self, mocker: MockerFixture, tmp_path: Path, bracketed_dir: str) -> None:
        """A path is the user's text, not Rich markup: `[draft]` used to be swallowed as a style tag, naming a
        file that does not exist, and `[/old]` raised a `MarkupError` in place of the diagnosis.
        """
        mocker.patch(f"{GRAPH_CMD}.make_pipelex_for_cli")
        mocker.patch(f"{GRAPH_CMD}.Pipelex.teardown_if_needed")
        mocker.patch(f"{GRAPH_CMD}.tag")
        telemetry_manager = mocker.patch(f"{GRAPH_CMD}.get_telemetry_manager").return_value
        telemetry_manager.telemetry_context.return_value = contextlib.nullcontext()
        printed = io.StringIO()
        mocker.patch(f"{GRAPH_CMD}.get_console", return_value=Console(file=printed, width=1000))

        spec_dir = tmp_path / bracketed_dir
        spec_dir.mkdir(parents=True)
        spec_file = spec_dir / "graph.json"
        spec_file.write_text("{}", encoding="utf-8")

        with pytest.raises(typer.Exit) as exit_info:
            graph_render_cmd(input_file=spec_file)

        assert exit_info.value.exit_code == 1
        assert "Failed to render graph" in printed.getvalue()
        assert str(spec_file) in printed.getvalue()
