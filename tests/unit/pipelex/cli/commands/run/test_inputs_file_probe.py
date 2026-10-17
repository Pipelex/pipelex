"""Unit tests for the shared inputs.json / inputs.toml auto-detect probe."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from pipelex.cli.commands.run._inputs_file_loader import (
    find_default_inputs_file,  # pyright: ignore[reportPrivateUsage]
)
from pipelex.cli.commands.run.exceptions import AmbiguousInputsFilesError, AutoDetectedInputsFileError

if TYPE_CHECKING:
    from pathlib import Path


class TestFindDefaultInputsFile:
    def test_json_only_is_found(self, tmp_path: Path) -> None:
        """With only inputs.json present, the probe returns it."""
        json_file = tmp_path / "inputs.json"
        json_file.write_text("{}", encoding="utf-8")

        assert find_default_inputs_file(directory=tmp_path) == json_file

    def test_toml_only_is_found(self, tmp_path: Path) -> None:
        """With only inputs.toml present, the probe returns it."""
        toml_file = tmp_path / "inputs.toml"
        toml_file.write_text("", encoding="utf-8")

        assert find_default_inputs_file(directory=tmp_path) == toml_file

    def test_neither_returns_none(self, tmp_path: Path) -> None:
        """With neither default file present, the probe returns None."""
        assert find_default_inputs_file(directory=tmp_path) is None

    def test_both_present_raises_ambiguity_error(self, tmp_path: Path) -> None:
        """With both default files present, the probe hard-errors telling the user to pass --inputs."""
        (tmp_path / "inputs.json").write_text("{}", encoding="utf-8")
        (tmp_path / "inputs.toml").write_text("", encoding="utf-8")

        with pytest.raises(AmbiguousInputsFilesError) as exc_info:
            find_default_inputs_file(directory=tmp_path)
        assert "--inputs" in exc_info.value.message
        assert "inputs.json" in exc_info.value.message
        assert "inputs.toml" in exc_info.value.message

    @pytest.mark.parametrize("name", ["inputs.json", "inputs.toml"])
    @pytest.mark.parametrize(
        ("entry", "described_as"),
        [
            ("link_outside", "a symbolic link"),
            ("dangling_link", "a symbolic link"),
            ("directory", "a directory"),
        ],
    )
    def test_an_entry_that_is_not_a_regular_file_is_refused(self, tmp_path: Path, name: str, entry: str, described_as: str) -> None:
        """A link is never followed, so a method's folder cannot point its inputs at data outside it; a directory is refused too."""
        method_dir = tmp_path / "method"
        method_dir.mkdir()
        candidate = method_dir / name
        if entry == "link_outside":
            outside = tmp_path / "secrets.json"
            outside.write_text('{"token": "not-for-the-run"}', encoding="utf-8")
            candidate.symlink_to(outside)
        elif entry == "dangling_link":
            candidate.symlink_to(tmp_path / "nowhere.json")
        else:
            candidate.mkdir()

        with pytest.raises(AutoDetectedInputsFileError) as exc_info:
            find_default_inputs_file(directory=method_dir)

        message = exc_info.value.message
        assert str(candidate) in message
        assert described_as in message
        assert "--inputs" in message
        assert "not-for-the-run" not in message

    def test_a_link_beside_a_regular_file_of_the_other_name_is_ambiguous(self, tmp_path: Path) -> None:
        """Both names are present whatever each entry is, so the ambiguity rule answers first and asks for --inputs."""
        (tmp_path / "inputs.json").write_text("{}", encoding="utf-8")
        (tmp_path / "inputs.toml").symlink_to(tmp_path / "inputs.json")

        with pytest.raises(AmbiguousInputsFilesError):
            find_default_inputs_file(directory=tmp_path)
