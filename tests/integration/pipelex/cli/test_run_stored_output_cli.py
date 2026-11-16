"""Pin: the local run commands show and save an output holding a text the run never loaded.

A `from` construct copies a text input given as a URL into the output as it is, a reference never read
(`test_construct_from_fields_load_the_stored_values_whose_value_they_extract`). The commands load it before they print
or save the output, whatever `--no-pretty-print` says; a reference they cannot load, such as a local file that is gone,
is described and saved as its reference, never a crash after a run that succeeded.
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any

import pytest

from pipelex.cli.agent_cli.commands.run._run_core import run_pipeline_core
from pipelex.cli.commands.run._run_core import _execute_run  # pyright: ignore[reportPrivateUsage]

if TYPE_CHECKING:
    from pathlib import Path

_FOLDER_BUNDLE = """
domain      = "stored_output_cli"
description = "Copy a text into a structure as content"
main_pipe   = "make_folder"

[concept.Folder]
description = "Pages kept as they are, beside a heading"

[concept.Folder.structure]
heading = { type = "text", description = "The heading", required = true }
pages   = { type = "concept", concept_ref = "Text", description = "The pages", required = true }

[pipe.make_folder]
type        = "PipeCompose"
description = "Keep the pages beside a heading"
inputs      = { subject = "Text", pages = "Text" }
output      = "Folder"

[pipe.make_folder.construct]
heading = { from = "subject" }
pages   = { from = "pages" }
"""

_NOTES_TEXT = "Notes kept in a local file, which the run never reads.\n" * 3


def _write_method(*, directory: Path, is_notes_file_present: bool) -> tuple[Path, dict[str, Any], Path]:
    """The bundle, its inputs, the pages given as the URL of a local file, and that file's path."""
    bundle_path = directory / "folder.mthds"
    bundle_path.write_text(_FOLDER_BUNDLE, encoding="utf-8")
    notes_path = directory / "notes.txt"
    if is_notes_file_present:
        notes_path.write_text(_NOTES_TEXT, encoding="utf-8")
    inputs: dict[str, Any] = {"subject": "Probe", "pages": {"concept": "Text", "content": {"url": str(notes_path)}}}
    return bundle_path, inputs, notes_path


def _saved_file(*, output_dir: Path, file_name: str) -> str:
    saved_files = list(output_dir.rglob(file_name))
    assert len(saved_files) == 1, f"{file_name}: {saved_files}"
    return saved_files[0].read_text(encoding="utf-8")


class TestRunStoredOutputCli:
    @pytest.mark.parametrize("no_pretty_print", [True, False], ids=["no_pretty_print", "pretty_print"])
    @pytest.mark.parametrize("is_notes_file_present", [True, False], ids=["the_file_is_there", "the_file_is_gone"])
    def test_pipelex_run_saves_every_main_stuff_file_of_an_output_holding_a_url_input(
        self, tmp_path: Path, no_pretty_print: bool, is_notes_file_present: bool
    ) -> None:
        """`pipelex run` loads the copied text before printing and saving it, and saves the reference of one it cannot load."""
        bundle_path, inputs, notes_path = _write_method(directory=tmp_path, is_notes_file_present=is_notes_file_present)
        inputs_path = tmp_path / "inputs.json"
        inputs_path.write_text(json.dumps(inputs), encoding="utf-8")
        output_dir = tmp_path / "outputs"

        asyncio.run(
            _execute_run(
                pipe_code=None,
                bundle_path=str(bundle_path),
                inputs=str(inputs_path),
                save_working_memory=False,
                working_memory_path=None,
                save_main_stuff=True,
                no_pretty_print=no_pretty_print,
                graph=False,
                graph_full_data=None,
                output_dir=str(output_dir),
                dry_run=False,
                mock_usage=False,
                mock_inputs=False,
                library_dir=None,
                costs=False,
            )
        )

        main_stuff_md = _saved_file(output_dir=output_dir, file_name="main_stuff.md")
        main_stuff_json = _saved_file(output_dir=output_dir, file_name="main_stuff.json")
        for file_name in ("main_stuff.html", "main_stuff_viewer.html"):
            assert _saved_file(output_dir=output_dir, file_name=file_name)
        # A structure's JSON carries the text it holds as its reference, whether it was loaded or not.
        assert json.loads(main_stuff_json)["pages"]["url"] == str(notes_path)
        if is_notes_file_present:
            assert "Notes kept in a local file" in main_stuff_md
        else:
            assert "not loaded" in main_stuff_md

    @pytest.mark.parametrize("is_notes_file_present", [True, False], ids=["the_file_is_there", "the_file_is_gone"])
    def test_pipelex_agent_run_renders_an_output_holding_a_url_input(self, tmp_path: Path, is_notes_file_present: bool) -> None:
        """`pipelex-agent run` loads the copied text before rendering it, and renders the reference of one it cannot load."""
        bundle_path, inputs, notes_path = _write_method(directory=tmp_path, is_notes_file_present=is_notes_file_present)

        result = asyncio.run(
            run_pipeline_core(
                "make_folder",
                mthds_contents=[_FOLDER_BUNDLE],
                bundle_uris=[str(bundle_path)],
                inputs=inputs,
                costs=False,
                with_memory=True,
                output_dir_override=tmp_path / "outputs",
            )
        )

        main_stuff = result["main_stuff"]
        assert json.loads(main_stuff["json"])["pages"]["url"] == str(notes_path)
        if is_notes_file_present:
            assert "Notes kept in a local file" in main_stuff["markdown"]
            assert "Notes kept in a local file" in main_stuff["html"]
        else:
            assert "not loaded" in main_stuff["markdown"]
            assert "not loaded" in main_stuff["html"]
