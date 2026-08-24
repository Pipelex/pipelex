"""Unit tests for the CLI readiness gate (pipelex/cli/readiness.py)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from rich.console import Console

import pipelex
from pipelex.cli.exceptions import ReadinessCheckError
from pipelex.cli.readiness import (
    _find_venv_directories,  # pyright: ignore[reportPrivateUsage]
    _is_development_install,  # pyright: ignore[reportPrivateUsage]
    _is_in_virtual_environment,  # pyright: ignore[reportPrivateUsage]
    check_readiness,
)

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


def _make_recorded_console() -> Console:
    return Console(width=100, record=True, color_system=None)


class TestReadiness:
    @pytest.fixture
    def no_env_markers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Strip every signal that we are inside a virtual environment."""
        monkeypatch.delenv("CONDA_DEFAULT_ENV", raising=False)
        monkeypatch.delenv("VIRTUAL_ENV", raising=False)
        monkeypatch.setattr(sys, "prefix", "/usr")
        monkeypatch.setattr(sys, "base_prefix", "/usr")

    @pytest.mark.usefixtures("no_env_markers")
    def test_is_in_virtual_environment_via_sys_prefix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A venv is detected when sys.prefix differs from sys.base_prefix."""
        monkeypatch.setattr(sys, "prefix", "/some/project/.venv")
        assert _is_in_virtual_environment() is True

    @pytest.mark.usefixtures("no_env_markers")
    def test_is_in_virtual_environment_via_conda(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A conda env is detected via CONDA_DEFAULT_ENV."""
        monkeypatch.setenv("CONDA_DEFAULT_ENV", "base")
        assert _is_in_virtual_environment() is True

    @pytest.mark.usefixtures("no_env_markers")
    def test_is_in_virtual_environment_via_virtual_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A virtualenv is detected via VIRTUAL_ENV."""
        monkeypatch.setenv("VIRTUAL_ENV", "/some/project/.venv")
        assert _is_in_virtual_environment() is True

    @pytest.mark.usefixtures("no_env_markers")
    def test_is_in_virtual_environment_false_without_markers(self) -> None:
        """No markers at all means no virtual environment."""
        assert _is_in_virtual_environment() is False

    def test_find_venv_directories_in_cwd(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """A .venv with bin/python in the cwd is found."""
        venv_python = tmp_path / ".venv" / "bin" / "python"
        venv_python.parent.mkdir(parents=True)
        venv_python.touch()
        monkeypatch.chdir(tmp_path)
        assert _find_venv_directories() == [".venv"]

    def test_find_venv_directories_in_parent(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """A venv two levels up (within the 3-level walk) is found."""
        venv_python = tmp_path / "venv" / "bin" / "python"
        venv_python.parent.mkdir(parents=True)
        venv_python.touch()
        nested_dir = tmp_path / "sub" / "deeper"
        nested_dir.mkdir(parents=True)
        monkeypatch.chdir(nested_dir)
        assert _find_venv_directories() == ["venv"]

    def test_find_venv_directories_ignores_dir_without_python(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """A venv-named directory without bin/python is not reported."""
        (tmp_path / ".venv").mkdir()
        monkeypatch.chdir(tmp_path)
        assert _find_venv_directories() == []

    def test_find_venv_directories_empty(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """No venv directories at all yields an empty list."""
        monkeypatch.chdir(tmp_path)
        assert _find_venv_directories() == []

    def test_is_development_install_with_git_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """A .git directory above the pipelex package marks a dev install."""
        repo_root = tmp_path / "repo"
        package_init = repo_root / "pipelex" / "__init__.py"
        package_init.parent.mkdir(parents=True)
        package_init.touch()
        (repo_root / ".git").mkdir()
        monkeypatch.setattr(pipelex, "__file__", str(package_init))
        assert _is_development_install() is True

    def test_is_development_install_without_git_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """No .git in the parent chain means a production install."""
        package_init = tmp_path / "site-packages" / "pipelex" / "__init__.py"
        package_init.parent.mkdir(parents=True)
        package_init.touch()
        monkeypatch.setattr(pipelex, "__file__", str(package_init))
        assert _is_development_install() is False

    def test_is_development_install_handles_missing_module_file(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A missing pipelex.__file__ attribute degrades to 'not a dev install'."""
        monkeypatch.delattr(pipelex, "__file__")
        assert _is_development_install() is False

    def test_is_development_install_handles_os_error(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture) -> None:
        """An OSError during path probing degrades to 'not a dev install'."""
        package_init = tmp_path / "pipelex" / "__init__.py"
        package_init.parent.mkdir(parents=True)
        package_init.touch()
        monkeypatch.setattr(pipelex, "__file__", str(package_init))
        mocker.patch.object(Path, "exists", side_effect=OSError("probe failed"))
        assert _is_development_install() is False

    def test_check_readiness_passes_for_dev_install_in_venv(self, mocker: MockerFixture) -> None:
        """Dev install with an active venv passes silently."""
        mocker.patch("pipelex.cli.readiness._is_development_install", return_value=True)
        mocker.patch("pipelex.cli.readiness._is_in_virtual_environment", return_value=True)
        check_readiness()

    def test_check_readiness_passes_for_production_install(self, mocker: MockerFixture) -> None:
        """Production installs are never gated on venv activation."""
        mocker.patch("pipelex.cli.readiness._is_development_install", return_value=False)
        mocker.patch("pipelex.cli.readiness._is_in_virtual_environment", return_value=False)
        check_readiness()

    def test_check_readiness_raises_with_activation_instructions(self, mocker: MockerFixture) -> None:
        """Dev install without venv but with discoverable venvs suggests activation."""
        mocker.patch("pipelex.cli.readiness._is_development_install", return_value=True)
        mocker.patch("pipelex.cli.readiness._is_in_virtual_environment", return_value=False)
        mocker.patch("pipelex.cli.readiness._find_venv_directories", return_value=[".venv", "venv"])
        console = _make_recorded_console()
        mocker.patch("pipelex.cli.readiness.get_console", return_value=console)

        with pytest.raises(ReadinessCheckError, match="no virtual environment is active"):
            check_readiness()

        output = console.export_text()
        assert "Virtual Environment Required" in output
        assert "Found virtual environment(s) in your project:" in output
        assert ".venv" in output
        assert "source .venv/bin/activate" in output

    def test_check_readiness_raises_with_creation_instructions(self, mocker: MockerFixture) -> None:
        """Dev install without venv and none found suggests creating one."""
        mocker.patch("pipelex.cli.readiness._is_development_install", return_value=True)
        mocker.patch("pipelex.cli.readiness._is_in_virtual_environment", return_value=False)
        mocker.patch("pipelex.cli.readiness._find_venv_directories", return_value=[])
        console = _make_recorded_console()
        mocker.patch("pipelex.cli.readiness.get_console", return_value=console)

        with pytest.raises(ReadinessCheckError):
            check_readiness()

        output = console.export_text()
        assert "To create and activate a virtual environment:" in output
        assert "python -m venv .venv" in output
