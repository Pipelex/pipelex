"""Tests for hierarchical config resolution: package defaults -> global -> project."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

from pipelex.system.configuration.config_loader import ConfigLoader


class TestConfigResolution:
    """Test the hierarchical config resolution in ConfigLoader."""

    def test_find_project_root_with_git(self, tmp_path: Path) -> None:
        """Walking up from a deep subdirectory finds the .git marker."""
        project_dir = tmp_path / "project"
        (project_dir / ".git").mkdir(parents=True)
        deep_dir = project_dir / "sub" / "deep"
        deep_dir.mkdir(parents=True)

        result = ConfigLoader.find_project_root(deep_dir)

        assert result == project_dir.resolve()

    def test_find_project_root_with_pyproject_toml(self, tmp_path: Path) -> None:
        """Walking up from a subdirectory finds pyproject.toml marker."""
        project_dir = tmp_path / "project"
        project_dir.mkdir(parents=True)
        (project_dir / "pyproject.toml").write_text("[project]\nname = 'test'")
        sub_dir = project_dir / "src" / "app"
        sub_dir.mkdir(parents=True)

        result = ConfigLoader.find_project_root(sub_dir)

        assert result == project_dir.resolve()

    def test_find_project_root_with_setup_py(self, tmp_path: Path) -> None:
        """Walking up finds setup.py marker."""
        project_dir = tmp_path / "project"
        project_dir.mkdir(parents=True)
        (project_dir / "setup.py").write_text("")
        sub_dir = project_dir / "src"
        sub_dir.mkdir(parents=True)

        result = ConfigLoader.find_project_root(sub_dir)

        assert result == project_dir.resolve()

    def test_find_project_root_with_package_json(self, tmp_path: Path) -> None:
        """Walking up finds package.json marker."""
        project_dir = tmp_path / "project"
        project_dir.mkdir(parents=True)
        (project_dir / "package.json").write_text("{}")
        sub_dir = project_dir / "src" / "components"
        sub_dir.mkdir(parents=True)

        result = ConfigLoader.find_project_root(sub_dir)

        assert result == project_dir.resolve()

    def test_find_project_root_no_markers(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """A directory tree with no markers returns None when home is reached."""
        deep_dir = tmp_path / "no_project" / "a" / "b" / "c"
        deep_dir.mkdir(parents=True)

        # Mock home to be tmp_path so the walk stops there instead of finding real markers
        mocker.patch.object(Path, "home", return_value=tmp_path)

        result = ConfigLoader.find_project_root(deep_dir)

        assert result is None

    def test_find_project_root_stops_at_nearest_marker(self, tmp_path: Path) -> None:
        """When multiple markers exist in the tree, the nearest one wins."""
        outer = tmp_path / "outer"
        (outer / ".git").mkdir(parents=True)
        inner = outer / "inner"
        inner.mkdir(parents=True)
        (inner / "pyproject.toml").write_text("[project]\nname = 'inner'")
        deep_dir = inner / "src"
        deep_dir.mkdir(parents=True)

        result = ConfigLoader.find_project_root(deep_dir)

        assert result == inner.resolve()

    def test_global_config_dir_is_home(self, mocker: MockerFixture) -> None:
        """global_config_dir always points to ~/.pipelex."""
        fake_home = Path("/fake/home")
        mocker.patch.object(Path, "home", return_value=fake_home)

        loader = ConfigLoader()

        assert loader.global_config_dir == fake_home / ".pipelex"

    def test_project_config_dir_when_exists(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """project_config_dir returns the path when .pipelex exists at the project root."""
        project_dir = tmp_path / "project"
        (project_dir / ".git").mkdir(parents=True)
        (project_dir / ".pipelex").mkdir(parents=True)

        mocker.patch.object(Path, "cwd", return_value=project_dir)

        loader = ConfigLoader()

        assert loader.project_config_dir == (project_dir / ".pipelex").resolve()

    def test_project_config_dir_none_when_no_pipelex_dir(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """project_config_dir returns None when project root has no .pipelex directory."""
        project_dir = tmp_path / "project"
        (project_dir / ".git").mkdir(parents=True)

        mocker.patch.object(Path, "cwd", return_value=project_dir)

        loader = ConfigLoader()

        assert loader.project_config_dir is None

    def test_effective_config_dir_is_project_when_exists(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """pipelex_config_dir returns project path when project .pipelex exists."""
        project_dir = tmp_path / "project"
        (project_dir / ".git").mkdir(parents=True)
        (project_dir / ".pipelex").mkdir(parents=True)

        mocker.patch.object(Path, "cwd", return_value=project_dir)
        mocker.patch.object(Path, "home", return_value=tmp_path / "home")

        loader = ConfigLoader()

        assert loader.pipelex_config_dir == (project_dir / ".pipelex").resolve()

    def test_effective_config_dir_falls_back_to_global(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """pipelex_config_dir returns global path when no project .pipelex exists."""
        project_dir = tmp_path / "project"
        (project_dir / ".git").mkdir(parents=True)
        # No .pipelex dir in project

        fake_home = tmp_path / "home"
        fake_home.mkdir(parents=True)

        mocker.patch.object(Path, "cwd", return_value=project_dir)
        mocker.patch.object(Path, "home", return_value=fake_home)

        loader = ConfigLoader()

        assert loader.pipelex_config_dir == fake_home / ".pipelex"

    def test_project_root_returns_str_when_found(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """project_root returns the project root as a string."""
        project_dir = tmp_path / "project"
        (project_dir / ".git").mkdir(parents=True)
        sub_dir = project_dir / "sub"
        sub_dir.mkdir(parents=True)

        mocker.patch.object(Path, "cwd", return_value=sub_dir)

        loader = ConfigLoader()

        assert loader.project_root == project_dir.resolve()

    def test_project_root_returns_none_without_markers(self, mocker: MockerFixture) -> None:
        """project_root returns None when no project root markers are found.

        We mock find_project_root to avoid walking real filesystem.
        """
        mocker.patch.object(ConfigLoader, "find_project_root", return_value=None)

        loader = ConfigLoader()

        assert loader.project_root is None

    def test_inference_files_from_project(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Inference file paths resolve to project dir when it has the files."""
        project_dir = tmp_path / "project"
        (project_dir / ".git").mkdir(parents=True)
        pipelex_dir = project_dir / ".pipelex"
        inference_dir = pipelex_dir / "inference"
        inference_dir.mkdir(parents=True)
        (inference_dir / "backends.toml").write_text("[backends]")
        backends_dir = inference_dir / "backends"
        backends_dir.mkdir()
        (inference_dir / "routing_profiles.toml").write_text("[routing]")
        deck_dir = inference_dir / "deck"
        deck_dir.mkdir()

        mocker.patch.object(Path, "cwd", return_value=project_dir)
        mocker.patch.object(Path, "home", return_value=tmp_path / "home")

        loader = ConfigLoader()

        assert loader.backends_file_path == inference_dir / "backends.toml"
        assert loader.backends_dir_path == backends_dir
        assert loader.routing_profiles_file_path == inference_dir / "routing_profiles.toml"
        assert loader.model_decks_dir_path == deck_dir

    def test_inference_files_fallback_to_global(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Inference file paths fall back to global dir when project dir has no files."""
        project_dir = tmp_path / "project"
        (project_dir / ".git").mkdir(parents=True)
        # Project .pipelex exists but has no inference files
        (project_dir / ".pipelex").mkdir(parents=True)

        global_home = tmp_path / "home"
        global_config = global_home / ".pipelex" / "inference"
        global_config.mkdir(parents=True)
        (global_config / "backends.toml").write_text("[backends]")

        mocker.patch.object(Path, "cwd", return_value=project_dir)
        mocker.patch.object(Path, "home", return_value=global_home)

        loader = ConfigLoader()

        # backends.toml exists in global, so it should resolve there
        assert loader.backends_file_path == global_config / "backends.toml"

    def test_ensure_global_config_created_on_first_run(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """ensure_global_config_exists creates ~/.pipelex/ with template files when it doesn't exist."""
        fake_home = tmp_path / "home"
        fake_home.mkdir(parents=True)

        mocker.patch.object(Path, "home", return_value=fake_home)

        loader = ConfigLoader()

        # Verify global dir does not exist yet
        global_dir = fake_home / ".pipelex"
        assert not global_dir.exists()

        loader.ensure_global_config_exists()

        # Verify global dir was created with content
        assert global_dir.is_dir()
        assert (global_dir / "pipelex.toml").exists()
        assert (global_dir / "inference").is_dir()

    def test_global_config_not_recreated_if_exists(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """ensure_global_config_exists does not overwrite existing ~/.pipelex/."""
        fake_home = tmp_path / "home"
        global_dir = fake_home / ".pipelex"
        global_dir.mkdir(parents=True)
        marker_file = global_dir / "custom_marker.txt"
        marker_file.write_text("do not delete")

        mocker.patch.object(Path, "home", return_value=fake_home)

        loader = ConfigLoader()
        loader.ensure_global_config_exists()

        # Custom file should still be there
        assert marker_file.exists()
        assert marker_file.read_text() == "do not delete"

    @pytest.mark.parametrize(
        "marker",
        [".pipelex", ".git", "pyproject.toml", "setup.py", "setup.cfg", "package.json", ".hg"],
    )
    def test_find_project_root_all_markers(self, tmp_path: Path, marker: str) -> None:
        """All supported markers are recognized."""
        project_dir = tmp_path / "project"
        project_dir.mkdir(parents=True)
        marker_path = project_dir / marker
        if marker in {".pipelex", ".git", ".hg"}:
            marker_path.mkdir()
        else:
            marker_path.write_text("")
        sub_dir = project_dir / "src"
        sub_dir.mkdir(parents=True)

        result = ConfigLoader.find_project_root(sub_dir)

        assert result == project_dir.resolve()

    def test_project_config_dir_found_via_pipelex_marker_only(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """A folder containing only a .pipelex/ directory (no .git, no pyproject.toml) is a project root.

        Regression: without .pipelex as a project root marker, such a folder fell through to the
        global ~/.pipelex/ config, silently ignoring the project's own .pipelex/ overrides.
        """
        project_dir = tmp_path / "project"
        (project_dir / ".pipelex").mkdir(parents=True)

        mocker.patch.object(Path, "cwd", return_value=project_dir)
        mocker.patch.object(Path, "home", return_value=tmp_path / "home")

        loader = ConfigLoader()

        assert loader.project_config_dir == (project_dir / ".pipelex").resolve()

    def test_cross_platform_paths(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Config paths use Path throughout, no hardcoded separators."""
        fake_home = tmp_path / "home"
        fake_home.mkdir(parents=True)
        mocker.patch.object(Path, "home", return_value=fake_home)

        loader = ConfigLoader()
        global_dir = loader.global_config_dir

        # Verify the path is valid and uses the correct separator for the platform
        assert global_dir.name == ".pipelex"
        assert global_dir.parent == fake_home
