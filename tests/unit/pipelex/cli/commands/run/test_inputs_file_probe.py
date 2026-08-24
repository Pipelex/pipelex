"""Unit tests for the shared inputs.json / inputs.toml auto-detect probe."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from pipelex.cli.commands.run._inputs_file_loader import (
    find_default_inputs_file,  # pyright: ignore[reportPrivateUsage]
)
from pipelex.cli.commands.run.exceptions import AmbiguousInputsFilesError

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
