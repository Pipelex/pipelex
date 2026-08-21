"""Unit tests for the shared inputs-file loader (extension-discriminated JSON/TOML)."""

from __future__ import annotations

import datetime
import json
from typing import TYPE_CHECKING

import pytest

from pipelex.cli.commands.run._inputs_file_loader import (
    load_inputs_dict_from_path,  # pyright: ignore[reportPrivateUsage]
)
from pipelex.core.stuffs.date_content import DateContent
from pipelex.core.stuffs.time_content import TimeContent
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

    @pytest.mark.parametrize("file_name", ["inputs.TOML", "inputs.Toml"])
    def test_uppercase_toml_suffix_routes_to_toml(self, tmp_path: Path, file_name: str) -> None:
        """The .toml suffix match is case-insensitive, so an uppercase suffix still parses as TOML."""
        inputs_file = tmp_path / file_name
        inputs_file.write_text('topic = "cats"\ncount = 3\n', encoding="utf-8")

        assert load_inputs_dict_from_path(inputs_file) == {"topic": "cats", "count": 3}

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

    def test_top_level_local_date_becomes_date_content(self, tmp_path: Path) -> None:
        """A top-level TOML local date maps to a date-only DateContent."""
        inputs_file = tmp_path / "inputs.toml"
        inputs_file.write_text("hearing = 2026-09-01\n", encoding="utf-8")

        loaded = load_inputs_dict_from_path(inputs_file)

        assert loaded["hearing"] == DateContent(date=datetime.date(2026, 9, 1))
        assert loaded["hearing"].time is None

    def test_top_level_local_datetime_becomes_naive_date_content(self, tmp_path: Path) -> None:
        """A top-level TOML local datetime maps to a DateContent with a naive time (no invented offset)."""
        inputs_file = tmp_path / "inputs.toml"
        inputs_file.write_text("start = 2026-07-07T09:00:00\n", encoding="utf-8")

        loaded = load_inputs_dict_from_path(inputs_file)

        content = loaded["start"]
        assert isinstance(content, DateContent)
        assert content.date == datetime.date(2026, 7, 7)
        assert content.time is not None
        assert content.time == datetime.time(9, 0)
        assert content.time.tzinfo is None

    def test_top_level_offset_datetime_preserves_offset(self, tmp_path: Path) -> None:
        """A top-level TOML offset datetime maps to a DateContent whose time keeps the stated UTC offset."""
        inputs_file = tmp_path / "inputs.toml"
        inputs_file.write_text("departure = 2026-07-07T15:40:00+02:00\n", encoding="utf-8")

        loaded = load_inputs_dict_from_path(inputs_file)

        content = loaded["departure"]
        assert isinstance(content, DateContent)
        assert content.time is not None
        assert content.time.utcoffset() == datetime.timedelta(hours=2)

    def test_top_level_local_time_becomes_time_content(self, tmp_path: Path) -> None:
        """A top-level bare TOML time-of-day maps to a TimeContent (native Time), never a Date."""
        inputs_file = tmp_path / "inputs.toml"
        inputs_file.write_text("opening = 09:00:00\n", encoding="utf-8")

        loaded = load_inputs_dict_from_path(inputs_file)

        assert loaded["opening"] == TimeContent(time=datetime.time(9, 0))
        assert loaded["opening"].time.tzinfo is None

    def test_nested_time_left_in_place(self, tmp_path: Path) -> None:
        """A time-of-day nested in an envelope's content is left for the factory/pydantic to consume."""
        inputs_file = tmp_path / "inputs.toml"
        inputs_file.write_text(
            '[record]\nconcept = "Event"\n[[record.entries]]\nlabel = "kickoff"\nat = 09:00:00\n',
            encoding="utf-8",
        )

        loaded = load_inputs_dict_from_path(inputs_file)

        assert loaded["record"]["entries"][0]["at"] == datetime.time(9, 0)

    def test_nested_datetime_left_in_place(self, tmp_path: Path) -> None:
        """A date/datetime nested in an envelope's content is left for the factory/pydantic to consume."""
        inputs_file = tmp_path / "inputs.toml"
        inputs_file.write_text('[due]\nconcept = "billing.DueDate"\ncontent = 2026-08-06\n', encoding="utf-8")

        loaded = load_inputs_dict_from_path(inputs_file)

        assert loaded["due"]["content"] == datetime.date(2026, 8, 6)
