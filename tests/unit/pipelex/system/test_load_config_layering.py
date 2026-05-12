"""Tests for layered override loading in ConfigLoader.load_config().

Validates that global and project override files are both layered, with project
on top, instead of project shadowing global entirely.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from pipelex.system.configuration.config_loader import ConfigLoader
from pipelex.system.runtime import RunEnvironment, RunMode, RuntimeManager

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


class TestLoadConfigLayering:
    """Cover the four-layer merge: package → global base → global override → project base → project override."""

    @pytest.fixture
    def fake_dirs(self, tmp_path: Path, mocker: MockerFixture) -> tuple[Path, Path]:
        """Set up a fake home + project tree and patch Path.home / Path.cwd.

        Returns:
            Tuple of (global_pipelex_dir, project_pipelex_dir). Caller writes
            override files into either dir as needed.
        """
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        global_dir = fake_home / ".pipelex"
        global_dir.mkdir()

        project_root = tmp_path / "project"
        (project_root / ".git").mkdir(parents=True)
        project_dir = project_root / ".pipelex"
        project_dir.mkdir()

        mocker.patch.object(Path, "home", return_value=fake_home)
        mocker.patch.object(Path, "cwd", return_value=project_root)

        # Force non-unit-testing run_mode and a fixed environment so the test
        # exercises the standard override sequence rather than the hermetic
        # ./tests/ branch.
        mocker.patch.object(RuntimeManager, "run_mode", new=RunMode.NORMAL)
        mocker.patch.object(RuntimeManager, "environment", new=RunEnvironment.DEV)

        return global_dir, project_dir

    def test_global_override_survives_when_project_base_does_not_set_key(self, fake_dirs: tuple[Path, Path]) -> None:
        """A leaf key set only in the global override is preserved under the project base."""
        global_dir, project_dir = fake_dirs
        (global_dir / "pipelex_override.toml").write_text('[section]\nkey_only_in_global = "from_global_override"\n')
        (project_dir / "pipelex.toml").write_text('[section]\nkey_only_in_project = "from_project_base"\n')

        merged = ConfigLoader().load_config()

        assert merged["section"]["key_only_in_global"] == "from_global_override"
        assert merged["section"]["key_only_in_project"] == "from_project_base"

    def test_project_override_wins_over_global_override(self, fake_dirs: tuple[Path, Path]) -> None:
        """Project override is the last loaded layer for a colliding key."""
        global_dir, project_dir = fake_dirs
        (global_dir / "pipelex_override.toml").write_text('[section]\nshared_key = "from_global_override"\n')
        (project_dir / "pipelex_override.toml").write_text('[section]\nshared_key = "from_project_override"\n')

        merged = ConfigLoader().load_config()

        assert merged["section"]["shared_key"] == "from_project_override"

    def test_project_base_wins_over_global_override(self, fake_dirs: tuple[Path, Path]) -> None:
        """Project base is layered AFTER global overrides, so it wins on collisions."""
        global_dir, project_dir = fake_dirs
        (global_dir / "pipelex_override.toml").write_text('[section]\nshared_key = "from_global_override"\n')
        (project_dir / "pipelex.toml").write_text('[section]\nshared_key = "from_project_base"\n')

        merged = ConfigLoader().load_config()

        assert merged["section"]["shared_key"] == "from_project_base"

    def test_env_override_layered_at_both_levels(self, fake_dirs: tuple[Path, Path]) -> None:
        """Env-specific override files are picked up at both global and project layers."""
        global_dir, project_dir = fake_dirs
        (global_dir / "pipelex_dev.toml").write_text('[section]\nfrom_global_env = "yes"\nshared = "global"\n')
        (project_dir / "pipelex_dev.toml").write_text('[section]\nfrom_project_env = "yes"\nshared = "project"\n')

        merged = ConfigLoader().load_config()

        assert merged["section"]["from_global_env"] == "yes"
        assert merged["section"]["from_project_env"] == "yes"
        assert merged["section"]["shared"] == "project"

    def test_no_project_dir_only_global_layers_load(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """When no project .pipelex/ exists, only the global stack is loaded."""
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        global_dir = fake_home / ".pipelex"
        global_dir.mkdir()
        (global_dir / "pipelex_override.toml").write_text('[section]\nkey = "from_global"\n')

        project_root = tmp_path / "project"
        (project_root / ".git").mkdir(parents=True)
        # Deliberately no .pipelex/ in project.

        mocker.patch.object(Path, "home", return_value=fake_home)
        mocker.patch.object(Path, "cwd", return_value=project_root)
        mocker.patch.object(RuntimeManager, "run_mode", new=RunMode.NORMAL)
        mocker.patch.object(RuntimeManager, "environment", new=RunEnvironment.DEV)

        merged = ConfigLoader().load_config()

        assert merged["section"]["key"] == "from_global"

    def test_unit_testing_run_mode_replaces_both_layers(self, fake_dirs: tuple[Path, Path], tmp_path: Path, mocker: MockerFixture) -> None:
        """Under unit testing, only ./tests/pipelex_unit_test.toml feeds the run_mode slot.

        Global and project pipelex_unit_test.toml files must be ignored to keep
        test runs hermetic regardless of machine-wide overrides.
        """
        global_dir, project_dir = fake_dirs
        # Override the fixture's RunMode patch — we want unit testing here.
        mocker.patch.object(RuntimeManager, "run_mode", new=RunMode.UNIT_TEST)

        (global_dir / "pipelex_unit_test.toml").write_text('[section]\nfrom_layer = "global"\n')
        (project_dir / "pipelex_unit_test.toml").write_text('[section]\nfrom_layer = "project"\n')

        tests_dir = tmp_path / "project" / "tests"
        tests_dir.mkdir()
        (tests_dir / "pipelex_unit_test.toml").write_text('[section]\nfrom_layer = "tests_dir"\n')

        merged = ConfigLoader().load_config()

        assert merged["section"]["from_layer"] == "tests_dir"

    def test_extra_overrides_win_last(self, fake_dirs: tuple[Path, Path]) -> None:
        """Programmatic extra_overrides override every file layer."""
        _, project_dir = fake_dirs
        (project_dir / "pipelex_override.toml").write_text('[section]\nkey = "from_project_override"\n')

        merged = ConfigLoader().load_config(extra_overrides={"section": {"key": "from_extra"}})

        assert merged["section"]["key"] == "from_extra"

    def test_temporary_override_wins_within_each_layer(self, fake_dirs: tuple[Path, Path]) -> None:
        """`pipelex_temporary_override.toml` is the last file in each layer's sequence.

        Within the global layer it beats `pipelex_override.toml`. The project's
        temporary_override then beats everything from the global layer.
        """
        global_dir, project_dir = fake_dirs
        (global_dir / "pipelex_override.toml").write_text('[section]\nglobal_key = "from_global_override"\n')
        (global_dir / "pipelex_temporary_override.toml").write_text(
            '[section]\nglobal_key = "from_global_temp"\nshared = "global_temp"\n',
        )
        (project_dir / "pipelex_temporary_override.toml").write_text('[section]\nshared = "project_temp"\n')

        merged = ConfigLoader().load_config()

        assert merged["section"]["global_key"] == "from_global_temp"
        assert merged["section"]["shared"] == "project_temp"
