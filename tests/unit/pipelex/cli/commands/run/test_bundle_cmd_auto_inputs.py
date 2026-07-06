"""Unit tests for `pipelex run bundle <dir>` inputs auto-detection (inputs.json / inputs.toml)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import typer

from pipelex.cli.commands.run.bundle_cmd import run_bundle_cmd

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture

BUNDLE_CMD_MODULE = "pipelex.cli.commands.run.bundle_cmd"


class TestBundleCmdAutoInputs:
    @pytest.fixture
    def bundle_dir(self, tmp_path: Path) -> Path:
        """A pipeline directory holding a default bundle file (contents never parsed: execute_run is mocked)."""
        (tmp_path / "bundle.mthds").write_text("# bundle\n", encoding="utf-8")
        return tmp_path

    def test_auto_detects_inputs_toml(self, mocker: MockerFixture, bundle_dir: Path) -> None:
        """With only inputs.toml in the directory, it is auto-detected and forwarded."""
        mock_execute = mocker.patch(f"{BUNDLE_CMD_MODULE}.execute_run")
        (bundle_dir / "inputs.toml").write_text('topic = "cats"\n', encoding="utf-8")

        run_bundle_cmd(path=str(bundle_dir))

        assert mock_execute.call_args.kwargs["inputs"] == str(bundle_dir / "inputs.toml")

    def test_auto_detects_inputs_json(self, mocker: MockerFixture, bundle_dir: Path) -> None:
        """With only inputs.json in the directory, today's auto-detection is unchanged."""
        mock_execute = mocker.patch(f"{BUNDLE_CMD_MODULE}.execute_run")
        (bundle_dir / "inputs.json").write_text('{"topic": "cats"}', encoding="utf-8")

        run_bundle_cmd(path=str(bundle_dir))

        assert mock_execute.call_args.kwargs["inputs"] == str(bundle_dir / "inputs.json")

    def test_both_inputs_files_error(self, mocker: MockerFixture, bundle_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """With both inputs.json and inputs.toml present, the command exits telling the user to pass --inputs."""
        mock_execute = mocker.patch(f"{BUNDLE_CMD_MODULE}.execute_run")
        (bundle_dir / "inputs.json").write_text('{"topic": "cats"}', encoding="utf-8")
        (bundle_dir / "inputs.toml").write_text('topic = "cats"\n', encoding="utf-8")

        with pytest.raises(typer.Exit) as exc_info:
            run_bundle_cmd(path=str(bundle_dir))

        assert exc_info.value.exit_code == 1
        assert "--inputs" in capsys.readouterr().err
        mock_execute.assert_not_called()

    def test_explicit_inputs_bypasses_ambiguity(self, mocker: MockerFixture, bundle_dir: Path) -> None:
        """An explicit --inputs skips the probe entirely, even with both default files present."""
        mock_execute = mocker.patch(f"{BUNDLE_CMD_MODULE}.execute_run")
        (bundle_dir / "inputs.json").write_text('{"topic": "cats"}', encoding="utf-8")
        (bundle_dir / "inputs.toml").write_text('topic = "cats"\n', encoding="utf-8")
        explicit = bundle_dir / "inputs.toml"

        run_bundle_cmd(path=str(bundle_dir), inputs=str(explicit))

        assert mock_execute.call_args.kwargs["inputs"] == str(explicit)
