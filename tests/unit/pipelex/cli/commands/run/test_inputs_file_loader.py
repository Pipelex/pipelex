"""Unit tests for the shared inputs-file loader (extension-discriminated JSON/TOML)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from pipelex.cli.commands.run._inputs_file_loader import load_inputs_dict_from_path  # noqa: PLC2701  # pyright: ignore[reportPrivateUsage]
from pipelex.cli.commands.run.exceptions import InputsDatetimeNotSupportedError
from pipelex.tools.misc.exceptions import JsonTypeError, TomlError

if TYPE_CHECKING:
    from pathlib import Path


class TestInputsFileLoader:
    def test_toml_file_loads(self, tmp_path: Path) -> None:
        """A .toml suffix routes through the TOML parser."""
        inputs_file = tmp_path / "inputs.toml"
        inputs_file.write_text('topic = "cats"\ncount = 3\n', encoding="utf-8")

        assert load_inputs_dict_from_path(inputs_file) == {"topic": "cats", "count": 3}

    def test_toml_multiline_string_round_trips(self, tmp_path: Path) -> None:
        """A TOML multi-line string lands verbatim (newlines preserved) in the input value."""
        inputs_file = tmp_path / "inputs.toml"
        inputs_file.write_text(
            '[contract_text]\nconcept = "Text"\ncontent = """\nFirst line.\nSecond line.\n"""\n',
            encoding="utf-8",
        )

        loaded = load_inputs_dict_from_path(inputs_file)

        assert loaded["contract_text"]["content"] == "First line.\nSecond line.\n"

    def test_json_file_loads(self, tmp_path: Path) -> None:
        """A .json suffix keeps today's JSON behavior."""
        inputs_file = tmp_path / "inputs.json"
        inputs_file.write_text(json.dumps({"topic": "dogs"}), encoding="utf-8")

        assert load_inputs_dict_from_path(inputs_file) == {"topic": "dogs"}

    def test_extensionless_file_treated_as_json(self, tmp_path: Path) -> None:
        """Only the .toml suffix selects TOML; an extensionless file is parsed as JSON."""
        inputs_file = tmp_path / "inputs"
        inputs_file.write_text(json.dumps({"key": "value"}), encoding="utf-8")

        assert load_inputs_dict_from_path(inputs_file) == {"key": "value"}

    def test_toml_syntax_error_raises_toml_error(self, tmp_path: Path) -> None:
        """Invalid TOML surfaces a TomlError naming the file."""
        inputs_file = tmp_path / "inputs.toml"
        inputs_file.write_text("topic = \n", encoding="utf-8")

        with pytest.raises(TomlError) as exc_info:
            load_inputs_dict_from_path(inputs_file)
        assert str(inputs_file) in exc_info.value.message

    def test_non_dict_json_raises_json_type_error(self, tmp_path: Path) -> None:
        """A JSON file holding a list (not a dict) still raises JsonTypeError."""
        inputs_file = tmp_path / "inputs.json"
        inputs_file.write_text('["not", "a", "dict"]', encoding="utf-8")

        with pytest.raises(JsonTypeError):
            load_inputs_dict_from_path(inputs_file)

    def test_missing_file_raises_file_not_found(self, tmp_path: Path) -> None:
        """A missing file raises FileNotFoundError for both formats."""
        with pytest.raises(FileNotFoundError):
            load_inputs_dict_from_path(tmp_path / "absent.toml")
        with pytest.raises(FileNotFoundError):
            load_inputs_dict_from_path(tmp_path / "absent.json")

    @pytest.mark.parametrize(
        "toml_value",
        [
            "2026-07-06T12:30:00Z",
            "2026-07-06T12:30:00",
            "2026-07-06",
            "12:30:00",
        ],
        ids=["offset_datetime", "local_datetime", "local_date", "local_time"],
    )
    def test_datetime_rejected_at_top_level(self, tmp_path: Path, toml_value: str) -> None:
        """Every TOML datetime flavor is rejected with the not-supported error."""
        inputs_file = tmp_path / "inputs.toml"
        inputs_file.write_text(f"deadline = {toml_value}\n", encoding="utf-8")

        with pytest.raises(InputsDatetimeNotSupportedError) as exc_info:
            load_inputs_dict_from_path(inputs_file)
        assert "not supported yet" in exc_info.value.message
        assert "deadline" in exc_info.value.message

    def test_datetime_rejected_nested(self, tmp_path: Path) -> None:
        """A datetime nested dict-in-list-in-dict is rejected, with its key path in the message."""
        inputs_file = tmp_path / "inputs.toml"
        inputs_file.write_text(
            '[record]\nconcept = "Event"\n[[record.entries]]\nlabel = "kickoff"\nwhen = 2026-07-06T09:00:00Z\n',
            encoding="utf-8",
        )

        with pytest.raises(InputsDatetimeNotSupportedError) as exc_info:
            load_inputs_dict_from_path(inputs_file)
        assert "record.entries[0].when" in exc_info.value.message

    def test_datetime_message_suggests_quoting(self, tmp_path: Path) -> None:
        """The rejection message tells the user to quote the value as a string meanwhile."""
        inputs_file = tmp_path / "inputs.toml"
        inputs_file.write_text("deadline = 2026-07-06\n", encoding="utf-8")

        with pytest.raises(InputsDatetimeNotSupportedError) as exc_info:
            load_inputs_dict_from_path(inputs_file)
        assert "quote the value as a string" in exc_info.value.message
