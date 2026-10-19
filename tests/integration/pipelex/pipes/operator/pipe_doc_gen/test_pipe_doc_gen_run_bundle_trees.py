"""`pipelex-agent run bundle` reads a method only through its tree: a bundle named alone is a one-file tree, a folder its own."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest
import typer
from mthds.protocol.problem.registry import CoreCode

from pipelex.cli.agent_cli.commands.agent_output import CliOutputFormat, set_agent_cli_error_format
from pipelex.cli.agent_cli.commands.run.bundle_cmd import run_bundle_cmd as agent_run_bundle_cmd
from tests.integration.pipelex.pipes.operator.pipe_doc_gen.doc_gen_helpers import write_bundle

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture

_STEP_FIELDS = 'format = "docx"\ntemplate_file = "letter.docx"'


def _run_agent_bundle(*, path: Path, pipe: str | None = None) -> dict[str, Any]:
    """Run `run bundle` on `path` as a dry run with JSON errors, which exits with the problem on stderr."""
    try:
        agent_run_bundle_cmd(
            path=str(path),
            pipe=pipe,
            inputs=None,
            dry_run=True,
            mock_inputs=True,
            graph=False,
            costs=False,
            library_dir=None,
            with_memory=False,
            output_format=CliOutputFormat.JSON,
            error_format=None,
        )
    finally:
        set_agent_cli_error_format(CliOutputFormat.JSON)
    msg = "The run was expected to be refused"
    raise AssertionError(msg)


@pytest.mark.usefixtures("stub_engines")
class TestPipeDocGenRunBundleTrees:
    @pytest.fixture(autouse=True)
    def _no_boot(self, mocker: MockerFixture) -> None:
        mocker.patch("pipelex.cli.agent_cli.commands.run.bundle_cmd.make_pipelex_for_agent_cli")
        mocker.patch("pipelex.cli.agent_cli.commands.run.bundle_cmd.Pipelex.teardown_if_needed")

    def test_a_bundle_named_alone_is_refused_the_file_beside_it(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """With no METHODS.toml at or above it, the bundle's method is that one file, and the run refuses the file beside it, naming it."""
        (tmp_path / "letter.docx").write_bytes(b"docx")
        bundle_path = write_bundle(directory=tmp_path, step_fields=_STEP_FIELDS, as_method=False)

        with pytest.raises(typer.Exit) as exc_info:
            _run_agent_bundle(path=bundle_path)

        assert exc_info.value.exit_code == 1
        problem: dict[str, Any] = json.loads(capsys.readouterr().err)
        assert problem["code"] == CoreCode.METHOD_INVALID
        assert problem["domain"] == "method"
        # The item reads the sentence of the refusal's code, which names the file the step could not read.
        (item,) = problem["errors"]
        assert "'letter.docx'" in item["detail"]

    def test_a_folder_whose_bundles_declare_several_main_pipes_is_refused_naming_them(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        (tmp_path / "letter.docx").write_bytes(b"docx")
        write_bundle(directory=tmp_path, step_fields=_STEP_FIELDS, as_method=False)
        (tmp_path / "other").mkdir()
        write_bundle(directory=tmp_path / "other", step_fields=_STEP_FIELDS, as_method=False)

        with pytest.raises(typer.Exit):
            _run_agent_bundle(path=tmp_path)

        problem: dict[str, Any] = json.loads(capsys.readouterr().err)
        assert problem["domain"] == "input"
        rendered = json.dumps(problem)
        assert "several of its bundles declare a main_pipe" in rendered
        assert "'invoice.mthds' declares 'print_invoice'" in rendered
        assert "'other/invoice.mthds' declares 'print_invoice'" in rendered
