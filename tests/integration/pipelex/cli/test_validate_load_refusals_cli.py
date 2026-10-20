"""Pin: the local CLIs answer a load-time refusal and a failing dry run as a negative verdict (exit 1).

On the validate surface exit 1 is a produced negative verdict and exit 2 is "no verdict could be
produced". These tests drive the real validation engine through the command cores:

- ``pipelex validate bundle`` on a bundle naming an unknown model prints the grouped invalid-bundle
  panel with the ``unknown_model`` item and exits 1, with no traceback;
- ``pipelex-agent validate bundle`` on the same bundle emits its invalid-verdict envelope
  (``is_valid: false`` and the item) and exits 1, where it used to answer the no-verdict envelope with
  exit 2;
- ``pipelex validate pipe <code>`` on a pipe whose dry run fails, and ``pipelex validate --all`` on the
  same library, print the invalid-bundle panel and exit 1, where they used to print a traceback;
- ``pipelex validate pipe <code>`` on a library naming an unknown model exits 1 with the item.
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

import pytest
import typer
from rich.console import Console

from pipelex.cli.agent_cli.commands.agent_output import CliOutputFormat, set_agent_cli_error_format
from pipelex.cli.agent_cli.commands.validate.bundle_cmd import validate_bundle_cmd as agent_validate_bundle_cmd
from pipelex.cli.commands.validate._validate_core import (
    _validate_pipe_or_bundle,  # pyright: ignore[reportPrivateUsage]
    do_validate_all_libraries_and_dry_run,
)
from pipelex.test_extras.mthds_corpus.loader import get_entry

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture

_UNKNOWN_MODEL_BUNDLE = """
domain      = "tide_tables"
description = "Write the note telling harbour users when the tide turns"
main_pipe   = "write_tide_note"

[pipe.write_tide_note]
type        = "PipeLLM"
description = "Write the tide note for the harbour board"
inputs      = { tide_times = "Text" }
output      = "Text"
model       = "gpt-5.6-lunna"
prompt      = "Write a short note for the harbour board from these tide times: $tide_times"
"""

# The corpus's dry-run residual: a PipeCondition whose rule renders to nothing, so its dry run fails.
_DRY_RUN_FAILURE_ENTRY = "invalid_dry_run_residual"
_DRY_RUN_FAILURE_PIPE = "route_parcel"


@pytest.fixture
def console(mocker: MockerFixture) -> Console:
    """A recording console patched into the error handlers, so the panel can be read back."""
    recorded_console = Console(width=200, record=True, color_system=None)
    mocker.patch("pipelex.cli.error_handlers.get_error_console", return_value=recorded_console)
    return recorded_console


@pytest.fixture
def unknown_model_bundle(tmp_path: Path) -> Path:
    bundle_path = tmp_path / "bundle.mthds"
    bundle_path.write_text(_UNKNOWN_MODEL_BUNDLE, encoding="utf-8")
    return bundle_path


class TestValidateLoadRefusalsCli:
    def test_bare_validate_bundle_renders_the_unknown_model_as_an_invalid_bundle(self, console: Console, unknown_model_bundle: Path) -> None:
        with pytest.raises(typer.Exit) as exc_info:
            asyncio.run(_validate_pipe_or_bundle(bundle_path=unknown_model_bundle, library_dirs=[unknown_model_bundle.parent]))

        assert exc_info.value.exit_code == 1
        output = console.export_text()
        assert "Bundle validation failed" in output
        assert "Pipe Validation Errors:" in output
        assert "Unknown Model" in output
        assert "Model handle 'gpt-5.6-lunna' was not found in the model deck" in output
        assert "Path: pipe.write_tide_note.model" in output
        assert "Traceback" not in output

    def test_agent_validate_bundle_emits_the_invalid_verdict_s_problem(
        self,
        mocker: MockerFixture,
        capsys: pytest.CaptureFixture[str],
        unknown_model_bundle: Path,
    ) -> None:
        mocker.patch("pipelex.cli.agent_cli.commands.validate.bundle_cmd.make_pipelex_for_agent_cli")
        mocker.patch("pipelex.cli.agent_cli.commands.validate.bundle_cmd.Pipelex.teardown_if_needed")
        try:
            with pytest.raises(typer.Exit) as exc_info:
                agent_validate_bundle_cmd(
                    path=str(unknown_model_bundle),
                    library_dir=[str(unknown_model_bundle.parent)],
                    output_format=CliOutputFormat.JSON,
                )
        finally:
            set_agent_cli_error_format(CliOutputFormat.JSON)

        assert exc_info.value.exit_code == 1
        problem = json.loads(capsys.readouterr().err)
        assert problem["is_valid"] is False
        assert problem["code"] == "method.invalid"
        assert problem["domain"] == "method"
        (item,) = problem["errors"]
        assert item["code"] == "model.unknown"
        assert item["location"] == {"pipe": "write_tide_note", "field": "model", "file": str(unknown_model_bundle)}
        assert "gpt-5.6-lunna" in json.dumps(item["params"])
        assert item["suggestions"]

    @pytest.mark.usefixtures("restore_current_library")
    def test_bare_validate_pipe_renders_a_failing_dry_run_as_an_invalid_bundle(self, console: Console) -> None:
        entry = get_entry(name=_DRY_RUN_FAILURE_ENTRY)

        with pytest.raises(typer.Exit) as exc_info:
            asyncio.run(_validate_pipe_or_bundle(pipe_code=_DRY_RUN_FAILURE_PIPE, library_dirs=[entry.directory]))

        assert exc_info.value.exit_code == 1
        output = console.export_text()
        assert "Bundle validation failed" in output
        assert "Dry Run Errors:" in output
        assert f"Pipe: {_DRY_RUN_FAILURE_PIPE}" in output
        assert "Traceback" not in output

    @pytest.mark.usefixtures("restore_current_library")
    def test_bare_validate_all_renders_a_failing_dry_run_as_an_invalid_bundle(self, console: Console) -> None:
        entry = get_entry(name=_DRY_RUN_FAILURE_ENTRY)

        with pytest.raises(typer.Exit) as exc_info:
            do_validate_all_libraries_and_dry_run(library_dirs=[entry.directory])

        assert exc_info.value.exit_code == 1
        output = console.export_text()
        assert "Bundle validation failed" in output
        assert "Dry Run Errors:" in output
        assert f"Pipe: {_DRY_RUN_FAILURE_PIPE}" in output
        assert "Traceback" not in output

    @pytest.mark.usefixtures("restore_current_library")
    def test_bare_validate_pipe_renders_an_unknown_model_in_the_library_as_an_invalid_bundle(
        self, console: Console, unknown_model_bundle: Path
    ) -> None:
        with pytest.raises(typer.Exit) as exc_info:
            asyncio.run(_validate_pipe_or_bundle(pipe_code="write_tide_note", library_dirs=[unknown_model_bundle.parent]))

        assert exc_info.value.exit_code == 1
        output = console.export_text()
        assert "Unknown Model" in output
        assert "Path: pipe.write_tide_note.model" in output
        assert "Traceback" not in output
