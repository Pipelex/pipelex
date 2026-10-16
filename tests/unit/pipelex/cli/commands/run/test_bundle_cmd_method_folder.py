"""`pipelex run bundle <folder>` runs the method rooted at the folder, from the pipe the protocol's rule selects."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import typer

from pipelex.cli.commands.run.bundle_cmd import run_bundle_cmd

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture

BUNDLE_CMD_MODULE = "pipelex.cli.commands.run.bundle_cmd"


def _bundle(*, domain: str, pipe_code: str, main_pipe: str | None) -> str:
    main_pipe_line = f'main_pipe = "{main_pipe}"\n' if main_pipe else ""
    return f"""domain = "{domain}"
{main_pipe_line}
[pipe.{pipe_code}]
type        = "PipeLLM"
description = "Summarize the text"
inputs      = {{ text = "Text" }}
output      = "Text"
prompt      = "Summarize $text"
"""


class TestBundleCmdMethodFolder:
    def test_a_folder_runs_from_its_manifest_s_main_pipe_and_records_its_tree(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """No `bundle.mthds` is looked for: the manifest names the entry, and the run is handed the tree it reads."""
        mock_execute = mocker.patch(f"{BUNDLE_CMD_MODULE}.execute_run")
        (tmp_path / "METHODS.toml").write_text(
            '[package]\naddress = "github.com/pipelex-tests/folder"\nversion = "1.0.0"\ndescription = "d"\nmain_pipe = "extract"\n\n'
            '[exports.folder_steps]\npipes = ["extract"]\n',
            encoding="utf-8",
        )
        (tmp_path / "bundle.mthds").write_text(_bundle(domain="folder_report", pipe_code="write_report", main_pipe="write_report"), encoding="utf-8")
        (tmp_path / "steps").mkdir()
        (tmp_path / "steps" / "extract.mthds").write_text(_bundle(domain="folder_steps", pipe_code="extract", main_pipe=None), encoding="utf-8")

        run_bundle_cmd(path=str(tmp_path))

        kwargs = mock_execute.call_args.kwargs
        assert kwargs["pipe_code"] == "folder_steps.extract"
        assert kwargs["bundle_path"] == str((tmp_path / "steps" / "extract.mthds").resolve())
        assert kwargs["library_dir"] == [str(tmp_path)]
        assert kwargs["method_tree"].tree_paths == ["METHODS.toml", "bundle.mthds", "steps/extract.mthds"]

    def test_a_named_pipe_needs_no_entry(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """With `--pipe`, bundles declaring several main pipes are no ambiguity: the run starts where it was told."""
        mock_execute = mocker.patch(f"{BUNDLE_CMD_MODULE}.execute_run")
        (tmp_path / "a.mthds").write_text(_bundle(domain="folder_a", pipe_code="first", main_pipe="first"), encoding="utf-8")
        (tmp_path / "b.mthds").write_text(_bundle(domain="folder_b", pipe_code="second", main_pipe="second"), encoding="utf-8")

        run_bundle_cmd(path=str(tmp_path), pipe="folder_b.second")

        kwargs = mock_execute.call_args.kwargs
        assert kwargs["pipe_code"] == "folder_b.second"
        assert kwargs["bundle_path"] is None

    def test_a_folder_with_no_single_entry_is_refused(self, mocker: MockerFixture, tmp_path: Path) -> None:
        mock_execute = mocker.patch(f"{BUNDLE_CMD_MODULE}.execute_run")
        mock_handler = mocker.patch(f"{BUNDLE_CMD_MODULE}.handle_validate_bundle_error", side_effect=typer.Exit(1))
        (tmp_path / "a.mthds").write_text(_bundle(domain="folder_a", pipe_code="first", main_pipe="first"), encoding="utf-8")
        (tmp_path / "b.mthds").write_text(_bundle(domain="folder_b", pipe_code="second", main_pipe="second"), encoding="utf-8")

        with pytest.raises(typer.Exit):
            run_bundle_cmd(path=str(tmp_path))

        verdict = mock_handler.call_args.args[0]
        assert "several of its bundles declare a main_pipe: 'a.mthds' declares 'first', 'b.mthds' declares 'second'" in verdict.message
        mock_execute.assert_not_called()
