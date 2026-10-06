"""`get_pipelex_home_dir` is `~/.pipelex` unless `PIPELEX_HOME` names another directory, and `global_config_dir` agrees."""

from pathlib import Path

import pytest

from pipelex.system.configuration.config_loader import ConfigLoader
from pipelex.system.environment import PIPELEX_HOME_ENV_KEY, get_pipelex_home_dir


class TestTheResolver:
    def test_unset_is_the_dot_pipelex_directory_in_the_home_directory(self, decoy_home: Path) -> None:
        assert get_pipelex_home_dir() == decoy_home / ".pipelex"
        assert ConfigLoader().global_config_dir == decoy_home / ".pipelex"

    def test_empty_counts_as_unset(self, decoy_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(PIPELEX_HOME_ENV_KEY, "")

        assert get_pipelex_home_dir() == decoy_home / ".pipelex"
        assert ConfigLoader().global_config_dir == decoy_home / ".pipelex"

    @pytest.mark.usefixtures("decoy_home")
    def test_an_absolute_value_names_the_directory_itself(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        relocated = tmp_path / "anywhere" / "my-home"
        monkeypatch.setenv(PIPELEX_HOME_ENV_KEY, str(relocated))

        assert get_pipelex_home_dir() == relocated.resolve()
        assert ConfigLoader().global_config_dir == relocated.resolve()

    def test_a_tilde_value_expands_against_the_home_directory(self, decoy_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(PIPELEX_HOME_ENV_KEY, "~/elsewhere/pipelex-home")

        assert get_pipelex_home_dir() == (decoy_home / "elsewhere" / "pipelex-home").resolve()

    @pytest.mark.usefixtures("decoy_home")
    def test_a_relative_value_resolves_against_the_working_directory(self, project_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(PIPELEX_HOME_ENV_KEY, "config/home")

        assert get_pipelex_home_dir() == (project_dir / "config" / "home").resolve()
        assert get_pipelex_home_dir().is_absolute()
