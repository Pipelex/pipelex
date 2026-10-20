from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from mthds.method_tree.lister import list_method_tree

from pipelex.cli.agent_cli.commands.agent_output import CliOutputFormat, set_agent_cli_error_format
from pipelex.cli.agent_cli.commands.validate.bundle_cmd import validate_bundle_cmd

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

VALIDATE_BUNDLE_CMD_MODULE = "pipelex.cli.agent_cli.commands.validate.bundle_cmd"

_BUNDLE = """domain = "graph_folder_probe"
main_pipe = "greet"

[pipe.greet]
type = "PipeCompose"
description = "Greet the reader"
inputs = { name = "Text" }
output = "Text"
template = "Hello, $name"
"""

# A second bundle of the same method, nested in a sub-folder, defining a pipe a `--pipe` can name.
_NESTED_BUNDLE = """domain = "graph_folder_probe"

[pipe.wave]
type = "PipeCompose"
description = "Wave at the reader"
inputs = { name = "Text" }
output = "Text"
template = "Bye, $name"
"""


def _write_method(*, tmp_path: Path) -> Path:
    """A method's folder: `bundle.mthds` declaring the main pipe, and `parts/extra.mthds` defining another pipe."""
    method_dir = (tmp_path / "method").resolve()
    (method_dir / "parts").mkdir(parents=True)
    (method_dir / "bundle.mthds").write_text(_BUNDLE, encoding="utf-8")
    (method_dir / "parts" / "extra.mthds").write_text(_NESTED_BUNDLE, encoding="utf-8")
    return method_dir


@pytest.fixture(autouse=True)
def no_boot(mocker: MockerFixture) -> None:
    """The suite's session boot owns the runtime, so the command's own boot and teardown are patched out."""
    mocker.patch(f"{VALIDATE_BUNDLE_CMD_MODULE}.make_pipelex_for_agent_cli")
    mocker.patch(f"{VALIDATE_BUNDLE_CMD_MODULE}.Pipelex.teardown_if_needed")


@pytest.mark.usefixtures("restore_current_library")
class TestAgentValidateGraphFolder:
    def test_two_validations_with_a_graph_leave_the_method_tree_unchanged(
        self,
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        """The real validation and dry-run graph, twice on a method's folder: each draws into its own ignored folder, whose path both formats name."""
        method_dir = _write_method(tmp_path=tmp_path)
        tree_before = list_method_tree(method_dir)

        try:
            validate_bundle_cmd(path=str(method_dir), graph=True, output_format=CliOutputFormat.JSON)
            envelope = json.loads(capsys.readouterr().out)
            validate_bundle_cmd(path=str(method_dir), graph=True, output_format=CliOutputFormat.MARKDOWN)
            markdown = capsys.readouterr().out
        finally:
            set_agent_cli_error_format(CliOutputFormat.JSON)

        first_folder = method_dir / "results" / "greet_output_01"
        first_viewer = Path(envelope["graph_files"]["reactflow_html"])
        assert first_viewer.resolve() == first_folder / "dry_run.html"
        assert first_viewer.is_file()
        assert Path(envelope["graph_output_dir"]).resolve() == first_folder
        assert (first_folder / ".gitignore").read_text(encoding="utf-8").splitlines()[-1] == "*"

        second_viewer = method_dir / "results" / "greet_output_02" / "dry_run.html"
        assert second_viewer.is_file()
        assert "## Graph files" in markdown
        assert "dry_run.html" in markdown
        assert "greet_output_02" in markdown

        assert not (method_dir / "dry_run.html").exists()
        tree_after = list_method_tree(method_dir)
        assert tree_after.tree_paths == ["bundle.mthds", "parts/extra.mthds"]
        assert tree_after.digest == tree_before.digest

    def test_a_named_pipe_of_a_nested_bundle_draws_into_the_folder_s_own_results(
        self,
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        """`--pipe` naming a pipe of `parts/extra.mthds` draws where `run bundle <folder> --pipe` writes: the folder's `results/`."""
        method_dir = _write_method(tmp_path=tmp_path)
        tree_before = list_method_tree(method_dir)

        try:
            validate_bundle_cmd(path=str(method_dir), pipe="graph_folder_probe.wave", graph=True, output_format=CliOutputFormat.JSON)
            envelope = json.loads(capsys.readouterr().out)
        finally:
            set_agent_cli_error_format(CliOutputFormat.JSON)

        viewer = Path(envelope["graph_files"]["reactflow_html"])
        assert viewer.resolve() == method_dir / "results" / "wave_output_01" / "dry_run.html"
        assert viewer.is_file()
        assert not (method_dir / "parts" / "results").exists()
        assert list_method_tree(method_dir).digest == tree_before.digest
