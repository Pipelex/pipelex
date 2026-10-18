"""Unit tests for the shared inputs.json / inputs.toml auto-detect probe."""

from __future__ import annotations

import os
import stat
import sys
from typing import TYPE_CHECKING

import pytest

from pipelex.cli.commands.run._inputs_file_loader import DetectedInputsFile, read_default_inputs_file
from pipelex.cli.commands.run.exceptions import AmbiguousInputsFilesError, AutoDetectedInputsFileError

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture

LOADER_MODULE = "pipelex.cli.commands.run._inputs_file_loader"
_NO_SYMLINKS_ON_WINDOWS = pytest.mark.skipif(
    sys.platform == "win32", reason="creating a symbolic link takes a privilege Windows does not grant by default"
)


class TestReadDefaultInputsFile:
    def test_json_only_is_found_and_read(self, tmp_path: Path) -> None:
        """With only inputs.json present, the probe returns it with its bytes."""
        json_file = tmp_path / "inputs.json"
        json_file.write_text('{"topic": "cats"}', encoding="utf-8")

        assert read_default_inputs_file(directory=tmp_path) == DetectedInputsFile(path=json_file, data=b'{"topic": "cats"}')

    def test_toml_only_is_found_and_read(self, tmp_path: Path) -> None:
        """With only inputs.toml present, the probe returns it with its bytes."""
        toml_file = tmp_path / "inputs.toml"
        toml_file.write_text('topic = "cats"\n', encoding="utf-8")

        assert read_default_inputs_file(directory=tmp_path) == DetectedInputsFile(path=toml_file, data=b'topic = "cats"\n')

    def test_neither_returns_none(self, tmp_path: Path) -> None:
        """With neither default file present, the probe returns None."""
        assert read_default_inputs_file(directory=tmp_path) is None

    def test_both_present_raises_ambiguity_error(self, tmp_path: Path) -> None:
        """With both default files present, the probe hard-errors telling the user to pass --inputs."""
        (tmp_path / "inputs.json").write_text("{}", encoding="utf-8")
        (tmp_path / "inputs.toml").write_text("", encoding="utf-8")

        with pytest.raises(AmbiguousInputsFilesError) as exc_info:
            read_default_inputs_file(directory=tmp_path)
        assert "--inputs" in exc_info.value.message
        assert "inputs.json" in exc_info.value.message
        assert "inputs.toml" in exc_info.value.message

    @_NO_SYMLINKS_ON_WINDOWS
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
            read_default_inputs_file(directory=method_dir)

        message = exc_info.value.message
        assert str(candidate) in message
        assert described_as in message
        assert "--inputs" in message
        assert "not-for-the-run" not in message

    @_NO_SYMLINKS_ON_WINDOWS
    def test_a_link_beside_a_regular_file_of_the_other_name_is_ambiguous(self, tmp_path: Path) -> None:
        """Both names are present whatever each entry is, so the ambiguity rule answers first and asks for --inputs."""
        (tmp_path / "inputs.json").write_text("{}", encoding="utf-8")
        (tmp_path / "inputs.toml").symlink_to(tmp_path / "inputs.json")

        with pytest.raises(AmbiguousInputsFilesError):
            read_default_inputs_file(directory=tmp_path)

    @_NO_SYMLINKS_ON_WINDOWS
    @pytest.mark.parametrize(
        ("swapped_in", "described_as"),
        [
            ("link", "a symbolic link"),
            ("directory", "a directory"),
            ("named_pipe", "not a regular file"),
        ],
    )
    def test_an_entry_swapped_after_the_lookup_is_refused_when_opened(
        self, mocker: MockerFixture, tmp_path: Path, swapped_in: str, described_as: str
    ) -> None:
        """The lookup saw a regular file, then the entry changed: the open never follows a link nor blocks, and the descriptor is judged."""
        if swapped_in == "named_pipe" and not hasattr(os, "mkfifo"):
            pytest.skip("this platform has no named pipes")
        method_dir = tmp_path / "method"
        method_dir.mkdir()
        candidate = method_dir / "inputs.json"
        if swapped_in == "link":
            outside = tmp_path / "secrets.json"
            outside.write_text('{"token": "not-for-the-run"}', encoding="utf-8")
            candidate.symlink_to(outside)
        elif swapped_in == "directory":
            candidate.mkdir()
        else:
            os.mkfifo(candidate)

        def mode_seen_before_the_swap(*, path: Path) -> int | None:
            """What the lookup saw before the swap: a regular file named inputs.json, and no inputs.toml."""
            return stat.S_IFREG | 0o644 if path == candidate else None

        mocker.patch(f"{LOADER_MODULE}._entry_mode", side_effect=mode_seen_before_the_swap)

        with pytest.raises(AutoDetectedInputsFileError) as exc_info:
            read_default_inputs_file(directory=method_dir)

        assert described_as in exc_info.value.message
        assert "not-for-the-run" not in exc_info.value.message
