from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from pipelex.tools.misc.exceptions import TomlError
from pipelex.tools.misc.file_utils import path_label
from pipelex.tools.misc.toml_utils import load_toml_from_path


class TestPathLabel:
    @pytest.mark.parametrize(
        ("working_dir", "target", "expected"),
        [
            # A project's file is named relative to the project the command runs in.
            ("home/project", "home/project/.pipelex/pipelex.toml", ".pipelex/pipelex.toml"),
            # The home configuration, from a project, is named under `~`.
            ("home/project", "home/.pipelex/inference/backends.toml", "~/.pipelex/inference/backends.toml"),
            # From the home directory itself, the home configuration still reads as the home's, never as a project's.
            ("home", "home/.pipelex/pipelex.toml", "~/.pipelex/pipelex.toml"),
            # From above the home directory too.
            (".", "home/.pipelex/pipelex.toml", "~/.pipelex/pipelex.toml"),
            # A relative path is read against the working directory.
            ("home/project", ".pipelex/pipelex.toml", ".pipelex/pipelex.toml"),
        ],
    )
    def test_a_path_is_named_without_the_home_directory(
        self, mocker: MockerFixture, tmp_path: Path, working_dir: str, target: str, expected: str
    ) -> None:
        mocker.patch.object(Path, "home", return_value=tmp_path / "home")
        mocker.patch.object(Path, "cwd", return_value=tmp_path / working_dir)
        target_path = Path(target) if not target.startswith("home") else tmp_path / target

        assert path_label(path=target_path) == expected

    def test_a_path_under_neither_is_named_whole(self, mocker: MockerFixture, tmp_path: Path) -> None:
        mocker.patch.object(Path, "home", return_value=tmp_path / "home")
        mocker.patch.object(Path, "cwd", return_value=tmp_path / "home" / "project")
        elsewhere = tmp_path / "etc" / "pipelex" / "pipelex.toml"

        assert path_label(path=elsewhere) == str(elsewhere)

    def test_without_a_home_directory_a_path_outside_the_working_directory_is_named_whole(self, mocker: MockerFixture, tmp_path: Path) -> None:
        mocker.patch.object(Path, "home", side_effect=RuntimeError("Could not determine home directory."))
        mocker.patch.object(Path, "cwd", return_value=tmp_path / "project")

        assert path_label(path=tmp_path / "project" / "a.toml") == "a.toml"
        assert path_label(path=tmp_path / "other" / "a.toml") == str(tmp_path / "other" / "a.toml")

    def test_a_toml_syntax_error_carries_the_file_it_was_read_from(self, tmp_path: Path) -> None:
        broken = tmp_path / "broken.toml"
        broken.write_text("[table\n", encoding="utf-8")

        with pytest.raises(TomlError) as exc_info:
            load_toml_from_path(broken)

        assert exc_info.value.path == broken
        assert exc_info.value.lineno == 1
