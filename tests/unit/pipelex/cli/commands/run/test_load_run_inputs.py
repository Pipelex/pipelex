"""Unit tests for `load_run_inputs`, the run CLI's reading of `--inputs` or of the inputs file auto-detection found."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pipelex.cli.commands.run._inputs_file_loader import DetectedInputsFile
from pipelex.cli.commands.run._run_core import LoadedRunInputs, load_run_inputs

if TYPE_CHECKING:
    from pathlib import Path


class TestLoadRunInputs:
    def test_an_auto_detected_file_is_parsed_from_the_bytes_read_and_never_reopened(self, tmp_path: Path) -> None:
        """The path now holds other content, as an entry swapped after the read would: the bytes auto-detection read are what loads."""
        inputs_file = tmp_path / "inputs.json"
        inputs_file.write_text('{"topic": "swapped-in-after-the-read"}', encoding="utf-8")

        loaded = load_run_inputs(inputs=DetectedInputsFile(path=inputs_file, data=b'{"topic": "read-without-following-a-link"}'))

        assert loaded == LoadedRunInputs(pipeline_inputs={"topic": "read-without-following-a-link"}, inputs_base_dir=tmp_path.resolve())

    def test_an_explicit_inputs_file_is_read_from_its_path(self, tmp_path: Path) -> None:
        """A file named with --inputs is read as given."""
        inputs_file = tmp_path / "inputs.toml"
        inputs_file.write_text('topic = "cats"\n', encoding="utf-8")

        loaded = load_run_inputs(inputs=str(inputs_file))

        assert loaded == LoadedRunInputs(pipeline_inputs={"topic": "cats"}, inputs_base_dir=tmp_path.resolve())
