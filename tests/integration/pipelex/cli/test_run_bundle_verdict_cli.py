"""Pin: the local run commands report an invalid bundle the way ``validate`` does.

A run refuses an invalid bundle while loading it, before any pipe runs, with the ``ValidateBundleError``
verdict. These tests drive the real run cores on a bundle whose pipe names a misspelled concept:

- ``pipelex run bundle`` prints the grouped invalid-bundle panel ``validate`` prints, with the located
  item, and exits 1 — whether the bundle is run from its directory (loaded as a library directory) or as
  a file, and whether the parse or the load refuses it. It used to print one line, ``Failed to execute
  pipeline '<pipe>': Could not load blueprints from [...] because of: …``.
- ``pipelex-agent run bundle`` reports the verdict's problem, its items the problem's ``errors``, and its
  markdown error renders them as the same grouped prose ``validate`` prints.
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any

import pytest
import typer
from rich.console import Console

from pipelex.cli.agent_cli.commands.agent_output import CliOutputFormat, set_agent_cli_error_format
from pipelex.cli.agent_cli.commands.run.bundle_cmd import run_bundle_cmd as agent_run_bundle_cmd
from pipelex.cli.commands.run._run_core import _execute_run  # pyright: ignore[reportPrivateUsage]

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture

_MISSPELLED_CONCEPT_BUNDLE = """
domain      = "harbour_notices"
description = "Write notices for the harbour board"
main_pipe   = "write_tide_notice"

[concept.TideNotice]
description = "A notice telling harbour users when the tide turns"

[pipe.write_tide_notice]
type        = "PipeLLM"
description = "Write the tide notice for the harbour board"
inputs      = { tide_times = "Text" }
output      = "TideNotise"
prompt      = "Write a short notice for the harbour board from these tide times: $tide_times"
"""

_TOML_SYNTAX_ERROR_BUNDLE = """
domain      = "harbour_notices
main_pipe   = "write_tide_notice"
"""


@pytest.fixture
def console(mocker: MockerFixture) -> Console:
    """A recording console patched into the error handlers, so the panel can be read back."""
    recorded_console = Console(width=200, record=True, color_system=None)
    mocker.patch("pipelex.cli.error_handlers.get_console", return_value=recorded_console)
    return recorded_console


def _write_bundle(*, directory: Path, content: str) -> Path:
    bundle_path = directory / "bundle.mthds"
    bundle_path.write_text(content, encoding="utf-8")
    return bundle_path


def _run_bundle(*, bundle_path: Path, library_dir: list[str] | None) -> None:
    asyncio.run(
        _execute_run(
            pipe_code=None,
            bundle_path=str(bundle_path),
            inputs=None,
            save_working_memory=False,
            working_memory_path=None,
            save_main_stuff=False,
            no_pretty_print=True,
            graph=False,
            graph_full_data=None,
            output_dir=str(bundle_path.parent / "outputs"),
            dry_run=True,
            mock_usage=False,
            mock_inputs=True,
            library_dir=library_dir,
            costs=False,
        )
    )


def _run_agent_bundle(*, bundle_path: Path, output_format: CliOutputFormat) -> None:
    try:
        agent_run_bundle_cmd(
            path=str(bundle_path.parent),
            pipe=None,
            inputs=None,
            dry_run=True,
            mock_inputs=True,
            graph=False,
            costs=False,
            library_dir=None,
            with_memory=False,
            output_format=output_format,
            error_format=None,
        )
    finally:
        set_agent_cli_error_format(CliOutputFormat.JSON)


class TestRunBundleVerdictCli:
    @pytest.mark.parametrize("from_directory", [True, False], ids=["directory", "file"])
    def test_run_bundle_renders_the_invalid_bundle_panel(self, console: Console, tmp_path: Path, from_directory: bool) -> None:
        bundle_path = _write_bundle(directory=tmp_path, content=_MISSPELLED_CONCEPT_BUNDLE)

        with pytest.raises(typer.Exit) as exc_info:
            _run_bundle(bundle_path=bundle_path, library_dir=[str(tmp_path)] if from_directory else None)

        assert exc_info.value.exit_code == 1
        output = console.export_text()
        assert "Bundle validation failed" in output
        assert "Pipe Validation Errors:" in output
        assert "Concept 'TideNotise' in pipe.write_tide_notice.output is not declared" in output
        assert "Could not load blueprints from" not in output
        assert "Traceback" not in output

    def test_run_bundle_renders_a_bundle_that_does_not_parse_as_an_invalid_bundle(self, console: Console, tmp_path: Path) -> None:
        bundle_path = _write_bundle(directory=tmp_path, content=_TOML_SYNTAX_ERROR_BUNDLE)

        with pytest.raises(typer.Exit) as exc_info:
            _run_bundle(bundle_path=bundle_path, library_dir=None)

        assert exc_info.value.exit_code == 1
        output = console.export_text()
        assert "Bundle validation failed" in output
        assert "TOML syntax error at line 2" in output

    def test_agent_run_bundle_carries_the_verdict_s_items(self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
        mocker.patch("pipelex.cli.agent_cli.commands.run.bundle_cmd.make_pipelex_for_agent_cli")
        mocker.patch("pipelex.cli.agent_cli.commands.run.bundle_cmd.Pipelex.teardown_if_needed")
        bundle_path = _write_bundle(directory=tmp_path, content=_MISSPELLED_CONCEPT_BUNDLE)

        with pytest.raises(typer.Exit) as exc_info:
            _run_agent_bundle(bundle_path=bundle_path, output_format=CliOutputFormat.JSON)

        assert exc_info.value.exit_code == 1
        problem: dict[str, Any] = json.loads(capsys.readouterr().err)
        assert problem["code"] == "method.invalid"
        assert problem["domain"] == "method"
        concept_items = [item for item in problem["errors"] if item["code"] == "method.concept_unresolved"]
        assert concept_items, f"expected a method.concept_unresolved item, got {problem['errors']!r}"
        (item,) = concept_items
        assert item["params"]["concept"] == "TideNotise"
        assert item["location"]["pipe"] == "write_tide_notice"
        assert item["location"]["field"] == "output"
        assert item["location"]["file"] == str(bundle_path)

    def test_agent_run_bundle_markdown_renders_the_items_as_prose(
        self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        mocker.patch("pipelex.cli.agent_cli.commands.run.bundle_cmd.make_pipelex_for_agent_cli")
        mocker.patch("pipelex.cli.agent_cli.commands.run.bundle_cmd.Pipelex.teardown_if_needed")
        bundle_path = _write_bundle(directory=tmp_path, content=_MISSPELLED_CONCEPT_BUNDLE)

        with pytest.raises(typer.Exit) as exc_info:
            _run_agent_bundle(bundle_path=bundle_path, output_format=CliOutputFormat.MARKDOWN)

        assert exc_info.value.exit_code == 1
        markdown = capsys.readouterr().err
        assert markdown.startswith("## The method does not validate")
        assert "## Pipe validation errors" in markdown
        assert "Concept 'TideNotise' in pipe.write_tide_notice.output is not declared" in markdown
        assert '"validation_errors"' not in markdown
